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
    "organizations",   # must precede users (users.org_id FK)
    "app_settings",
    "users",
    "datasets",
    "prompt_templates",
    "conversations",
    "dataset_columns",
    "example_queries",
    "messages",
    "automations",
    "automation_triggers",
    "trigger_templates",
    "automation_runs",
    "notifications",
    "dataset_stats",
]



# Migration columns: (table, column, column_def).
# Applied idempotently to both local (_migrate_schema) and remote (ensure_remote_schema).
_MIGRATION_COLUMNS = [
    ("users", "is_admin", "BOOLEAN DEFAULT 0 NOT NULL"),
    ("users", "last_active", "DATETIME"),
    ("users", "org_id", "VARCHAR(100)"),
    ("users", "updated_at", "DATETIME"),
    ("conversations", "is_starred", "BOOLEAN DEFAULT 0 NOT NULL"),
    ("conversations", "org_id", "VARCHAR(100)"),
    ("messages", "feedback", "BOOLEAN"),
    ("messages", "feedback_comment", "TEXT"),
    ("messages", "input_tokens", "INTEGER"),
    ("messages", "output_tokens", "INTEGER"),
    ("messages", "generation_time_ms", "INTEGER"),
    ("automations", "workflow_json", "TEXT"),
    ("datasets", "organization_id", "VARCHAR(100)"),
]

# All indexes and unique constraints that must exist on every database.
_SCHEMA_INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_conversations_user_id ON conversations (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_conversations_updated_at ON conversations (updated_at)",
    "CREATE INDEX IF NOT EXISTS ix_conversations_org_id ON conversations (org_id)",
    "CREATE INDEX IF NOT EXISTS ix_messages_conversation_id ON messages (conversation_id)",
    "CREATE INDEX IF NOT EXISTS ix_messages_created_at ON messages (created_at)",
    "CREATE INDEX IF NOT EXISTS ix_messages_conv_created ON messages (conversation_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_automation_runs_automation_id ON automation_runs (automation_id)",
    "CREATE INDEX IF NOT EXISTS ix_automation_runs_auto_created ON automation_runs (automation_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_automations_active_next_run ON automations (is_active, next_run_at)",
    "CREATE INDEX IF NOT EXISTS ix_notifications_user_id ON notifications (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_notifications_user_read ON notifications (user_id, is_read, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_dataset_stats_stat_group ON dataset_stats (stat_group)",
    "CREATE INDEX IF NOT EXISTS ix_dataset_stats_group_dim ON dataset_stats (stat_group, dimension)",
    "CREATE INDEX IF NOT EXISTS ix_datasets_organization_id ON datasets (organization_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_dataset_columns_ds_col ON dataset_columns (dataset_id, column_name)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_example_queries_ds_question ON example_queries (dataset_id, question)",
    "CREATE INDEX IF NOT EXISTS ix_automation_triggers_auto_id ON automation_triggers (automation_id)",
    "CREATE INDEX IF NOT EXISTS ix_trigger_templates_created_by ON trigger_templates (created_by)",
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
    # Schema sync: ensure Turso matches local structure
    # ------------------------------------------------------------------

    def ensure_remote_schema(self) -> None:
        """Ensure Turso has the same tables, columns, indexes, and constraints as local.

        Idempotent — safe to call on every startup.

        1. ``create_all`` creates any *missing* tables with full FK / index /
           unique-constraint definitions from the ORM models.
        2. ``ALTER TABLE ADD COLUMN`` adds columns that were introduced by
           migrations on existing tables.
        3. ``CREATE INDEX IF NOT EXISTS`` ensures every required index exists.
        """
        from insightxpert.auth.models import Base as AuthBase

        # 1. Create missing tables (no-op for tables that already exist)
        try:
            AuthBase.metadata.create_all(self._turso)
            logger.info("Turso schema: tables ensured via create_all")
        except Exception as e:
            logger.error("Turso create_all failed: %s", e)

        with self._turso.begin() as conn:
            # 2. Add migration columns to existing tables
            for table, column, col_def in _MIGRATION_COLUMNS:
                try:
                    conn.execute(text(
                        f"ALTER TABLE {table} ADD COLUMN {column} {col_def}"
                    ))
                    logger.info("Turso migration: added %s.%s", table, column)
                except Exception:
                    pass  # Column already exists

            # 3. Create all indexes and unique constraints
            for idx_sql in _SCHEMA_INDEXES:
                try:
                    conn.execute(text(idx_sql))
                except Exception as e:
                    logger.debug("Turso index skipped: %s", e)

            # 4. Sync delete tracking table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS _sync_deletes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_name TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    deleted_at DATETIME NOT NULL,
                    synced BOOLEAN NOT NULL DEFAULT 0
                )
            """))

        logger.info("Turso schema sync complete")

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

    def _get_remote_columns(self, remote_conn, table: str) -> set[str]:
        """Return the set of column names that exist in the remote Turso table."""
        try:
            rows = remote_conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            return {r[1] for r in rows}
        except Exception:
            return set()

    def push_to_turso(self) -> dict[str, int]:
        """Push changed rows (since last sync) from local SQLite to Turso.

        Uses created_at/updated_at timestamps for change detection.
        Only pushes columns that exist in both local and Turso so that
        schema-lagging remote tables don't cause hard failures.
        Returns {table_name: row_count} for logging.
        """
        stats: dict[str, int] = {}
        cutoff = self._last_sync

        with self._local.connect() as local_conn:
            with self._turso.begin() as remote_conn:
                for table in SYNC_TABLES:
                    try:
                        # Determine which timestamp columns exist locally
                        cols_info = local_conn.execute(
                            text(f"PRAGMA table_info({table})")
                        ).fetchall()
                        local_cols = {r[1] for r in cols_info}

                        if cutoff is None:
                            # First push: sync everything
                            rows = local_conn.execute(text(f"SELECT * FROM {table}")).fetchall()
                        else:
                            # Incremental: find rows changed since last sync
                            conditions = []
                            if "updated_at" in local_cols:
                                conditions.append("updated_at > :cutoff")
                            if "created_at" in local_cols:
                                conditions.append("created_at > :cutoff")

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

                        # Intersect with columns that actually exist in Turso
                        # to handle cases where the remote schema is behind.
                        all_local_cols = list(rows[0]._mapping.keys())
                        remote_cols = self._get_remote_columns(remote_conn, table)
                        if remote_cols:
                            push_cols = [c for c in all_local_cols if c in remote_cols]
                        else:
                            push_cols = all_local_cols

                        if not push_cols:
                            stats[table] = 0
                            continue

                        col_names = ", ".join(push_cols)
                        placeholders = ", ".join(f":{c}" for c in push_cols)
                        upsert_sql = f"INSERT OR REPLACE INTO {table} ({col_names}) VALUES ({placeholders})"

                        for row in rows:
                            row_dict = dict(row._mapping)
                            remote_conn.execute(
                                text(upsert_sql),
                                {c: row_dict[c] for c in push_cols},
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
