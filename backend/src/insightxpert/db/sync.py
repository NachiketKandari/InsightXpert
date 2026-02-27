"""Turso background sync: local SQLite <-> remote Turso.

Startup: pull auth data from Turso into local SQLite (hydrate).
Runtime: periodically push local changes to Turso (backup).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine

from insightxpert.db.connector import create_turso_engine

logger = logging.getLogger("insightxpert.sync")

# Auth tables in FK-safe insertion order (parents before children).
# `transactions` is CSV-loaded locally and never synced.
SYNC_TABLES = [
    "users",
    "datasets",
    "prompt_templates",
    "conversations",
    "dataset_columns",
    "example_queries",
    "messages",
]


class TursoSyncManager:
    """Bidirectional sync between local SQLite and remote Turso."""

    def __init__(
        self,
        local_engine: Engine,
        turso_url: str,
        turso_auth_token: str,
    ) -> None:
        self._local = local_engine
        self._turso = create_turso_engine(turso_url, turso_auth_token)
        self._last_sync: datetime | None = None
        self._bg_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Startup pull: Turso -> Local
    # ------------------------------------------------------------------

    def pull_from_turso(self) -> dict[str, int]:
        """Bulk-read all rows from Turso auth tables and INSERT OR REPLACE locally.

        Returns {table_name: row_count} for logging.
        """
        stats: dict[str, int] = {}

        with self._turso.connect() as remote_conn:
            # Check which tables exist in Turso
            remote_tables = set()
            try:
                rows = remote_conn.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table'")
                ).fetchall()
                remote_tables = {r[0] for r in rows}
            except Exception as e:
                logger.warning("Could not list Turso tables: %s", e)
                return stats

            with self._local.begin() as local_conn:
                # Disable FK checks during bulk load
                local_conn.execute(text("PRAGMA foreign_keys = OFF"))

                for table in SYNC_TABLES:
                    if table not in remote_tables:
                        logger.debug("Table '%s' not in Turso, skipping pull", table)
                        stats[table] = 0
                        continue

                    try:
                        rows = remote_conn.execute(text(f"SELECT * FROM {table}")).fetchall()
                        if not rows:
                            stats[table] = 0
                            continue

                        columns = rows[0]._fields if hasattr(rows[0], '_fields') else list(rows[0]._mapping.keys())
                        col_names = ", ".join(columns)
                        placeholders = ", ".join(f":{c}" for c in columns)
                        upsert_sql = f"INSERT OR REPLACE INTO {table} ({col_names}) VALUES ({placeholders})"

                        for row in rows:
                            local_conn.execute(
                                text(upsert_sql),
                                dict(row._mapping),
                            )
                        stats[table] = len(rows)
                    except Exception as e:
                        logger.error("Pull failed for table '%s': %s", table, e)
                        stats[table] = 0

                # Re-enable FK checks
                local_conn.execute(text("PRAGMA foreign_keys = ON"))

        logger.info("Startup sync from Turso complete: %s", stats)
        self._last_sync = datetime.now(timezone.utc)
        return stats

    # ------------------------------------------------------------------
    # Background push: Local -> Turso
    # ------------------------------------------------------------------

    def push_to_turso(self) -> dict[str, int]:
        """Push changed rows (since last sync) from local SQLite to Turso.

        Uses created_at/updated_at timestamps for change detection.
        Returns {table_name: row_count} for logging.
        """
        stats: dict[str, int] = {}
        cutoff = self._last_sync

        with self._local.connect() as local_conn:
            with self._turso.begin() as remote_conn:
                for table in SYNC_TABLES:
                    try:
                        # Determine which timestamp columns exist
                        cols_info = local_conn.execute(
                            text(f"PRAGMA table_info({table})")
                        ).fetchall()
                        col_names_set = {r[1] for r in cols_info}

                        if cutoff is None:
                            # First push: sync everything
                            rows = local_conn.execute(text(f"SELECT * FROM {table}")).fetchall()
                        else:
                            # Incremental: find rows changed since last sync
                            conditions = []
                            if "updated_at" in col_names_set:
                                conditions.append(f"updated_at > :cutoff")
                            if "created_at" in col_names_set:
                                conditions.append(f"created_at > :cutoff")

                            if not conditions:
                                stats[table] = 0
                                continue

                            where = " OR ".join(conditions)
                            rows = local_conn.execute(
                                text(f"SELECT * FROM {table} WHERE {where}"),
                                {"cutoff": cutoff.isoformat()},
                            ).fetchall()

                        if not rows:
                            stats[table] = 0
                            continue

                        columns = list(rows[0]._mapping.keys())
                        col_names = ", ".join(columns)
                        placeholders = ", ".join(f":{c}" for c in columns)
                        upsert_sql = f"INSERT OR REPLACE INTO {table} ({col_names}) VALUES ({placeholders})"

                        for row in rows:
                            remote_conn.execute(
                                text(upsert_sql),
                                dict(row._mapping),
                            )
                        stats[table] = len(rows)
                    except Exception as e:
                        logger.error("Push failed for table '%s': %s", table, e)
                        stats[table] = 0

                # Process deletes
                try:
                    self._push_deletes(local_conn, remote_conn)
                except Exception as e:
                    logger.error("Push deletes failed: %s", e)

        self._last_sync = datetime.now(timezone.utc)
        total = sum(stats.values())
        if total > 0:
            logger.info("Background sync pushed %d rows: %s", total, stats)
        else:
            logger.debug("Background sync: no changes to push")
        return stats

    def _push_deletes(self, local_conn, remote_conn) -> None:
        """Process _sync_deletes table: delete matching rows from Turso, mark as synced."""
        rows = local_conn.execute(
            text("SELECT id, table_name, record_id FROM _sync_deletes WHERE synced = 0")
        ).fetchall()

        if not rows:
            return

        for row in rows:
            _, table_name, record_id = row[0], row[1], row[2]
            if table_name not in SYNC_TABLES:
                continue

            try:
                remote_conn.execute(
                    text(f"DELETE FROM {table_name} WHERE id = :rid"),
                    {"rid": record_id},
                )
            except Exception as e:
                logger.warning("Failed to delete %s.%s from Turso: %s", table_name, record_id, e)

        # Mark all as synced in local DB (need a separate connection for local writes)
        synced_ids = [row[0] for row in rows]
        with self._local.begin() as local_write:
            for sid in synced_ids:
                local_write.execute(
                    text("UPDATE _sync_deletes SET synced = 1 WHERE id = :id"),
                    {"id": sid},
                )

        logger.info("Synced %d deletes to Turso", len(synced_ids))

    # ------------------------------------------------------------------
    # Background sync loop
    # ------------------------------------------------------------------

    async def start_background_sync(self, interval_seconds: int) -> None:
        """Start the periodic push loop. Call from lifespan startup."""
        self._bg_task = asyncio.create_task(self._sync_loop(interval_seconds))

    async def _sync_loop(self, interval_seconds: int) -> None:
        logger.info("Background sync started (interval=%ds)", interval_seconds)
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                await asyncio.to_thread(self.push_to_turso)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Background sync error (will retry): %s", e)

    async def shutdown(self) -> None:
        """Final push and cancel background task."""
        if self._bg_task is not None:
            self._bg_task.cancel()
            try:
                await self._bg_task
            except asyncio.CancelledError:
                pass

        # Final push
        try:
            await asyncio.to_thread(self.push_to_turso)
            logger.info("Final sync push completed")
        except Exception as e:
            logger.error("Final sync push failed: %s", e)

        self._turso.dispose()
