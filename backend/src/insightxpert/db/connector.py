from __future__ import annotations

import logging
import re
import time

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine

logger = logging.getLogger("insightxpert.db")

FORBIDDEN_SQL_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|MERGE|GRANT|REVOKE|ATTACH|DETACH|PRAGMA\s+\w+\s*=)\b",
    re.IGNORECASE,
)

# Module-level holder for libSQL sync-owner connections. These connections
# spawn the background thread that syncs the local replica from the remote
# Turso primary. We never close them and never use them for queries — they
# exist solely to keep the sync thread alive. List, not single global, so
# multiple engines (e.g. tests + app) can coexist without clobbering.
_SYNC_OWNERS: list = []


def _is_libsql_url(url: str) -> bool:
    return url.startswith("libsql://") or url.startswith("sqlite+libsql://")


def _enable_sqlite_pragmas(dbapi_conn, connection_record):
    """Enable foreign keys + WAL on local-file SQLite connections only."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.close()


def _enable_libsql_pragmas(dbapi_conn, connection_record):
    """Enable foreign keys on libSQL connections (skip WAL — protocol-owned)."""
    cursor = dbapi_conn.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys = ON")
    except Exception as exc:  # noqa: BLE001
        logger.debug("PRAGMA foreign_keys = ON not applied on libSQL connection: %s", exc)
    finally:
        cursor.close()


def _build_libsql_engine(
    url: str,
    *,
    auth_token: str,
    local_replica_path: str,
    sync_interval_seconds: int,
) -> Engine:
    """Build a SQLAlchemy engine for Turso/libSQL.

    If `local_replica_path` is set, use an embedded replica (local SQLite file
    that syncs from remote). Otherwise connect pure-remote (every query is a
    network round-trip).
    """
    if not auth_token:
        raise ValueError(
            "TURSO_AUTH_TOKEN is required when DATABASE_URL is libsql://. "
            "Set the env var (or .env.local entry) and retry."
        )

    sync_url = url
    if sync_url.startswith("sqlite+libsql://"):
        sync_url = "libsql://" + sync_url[len("sqlite+libsql://"):]

    if local_replica_path:
        import libsql_experimental as libsql  # type: ignore[import-untyped]

        # Embedded replica with a single long-lived sync owner. Only ONE
        # connection has sync_interval set — that connection's libsql client
        # spawns the background sync thread that pulls remote changes into
        # the local replica file. Per-checkout SQLAlchemy connections open
        # WITHOUT sync_interval; otherwise each pool slot would spawn its
        # own background sync thread and they race on WAL writes
        # (`wal_insert_begin failed`).
        _connect_kwargs: dict = {
            "database": local_replica_path,
            "sync_url": sync_url,
            "auth_token": auth_token,
        }
        _sync_owner_kwargs: dict = dict(_connect_kwargs)
        if sync_interval_seconds > 0:
            _sync_owner_kwargs["sync_interval"] = sync_interval_seconds

        try:
            # Hold a module-level reference so the sync owner's background
            # thread isn't GC'd. We never close this connection.
            _SYNC_OWNERS.append(libsql.connect(**_sync_owner_kwargs))
            _SYNC_OWNERS[-1].sync()
            logger.info(
                "libSQL initial sync complete (replica=%s, sync_owner_interval=%ds)",
                local_replica_path, sync_interval_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Initial libSQL sync failed (will retry in background): %s", exc
            )

        def _creator():
            return libsql.connect(**_connect_kwargs)

        engine = create_engine(
            "sqlite+libsql://",
            creator=_creator,
            pool_pre_ping=True,
        )
        logger.info(
            "libSQL embedded-replica engine ready (local=%s, sync_url=%s, interval=%ds)",
            local_replica_path, sync_url, sync_interval_seconds,
        )
        event.listen(engine, "connect", _enable_libsql_pragmas)
        return engine

    # Pure remote (no local replica). Every query is a network call.
    engine_url = url if url.startswith("sqlite+libsql://") else "sqlite+libsql://" + url[len("libsql://"):]
    if "?" in engine_url:
        if "secure=true" not in engine_url:
            engine_url += "&secure=true"
    else:
        engine_url += "?secure=true"

    engine = create_engine(
        engine_url,
        connect_args={"auth_token": auth_token},
        pool_pre_ping=True,
    )
    logger.info("libSQL pure-remote engine ready (url=%s)", engine_url)
    event.listen(engine, "connect", _enable_libsql_pragmas)
    return engine


class DatabaseConnector:
    def __init__(self) -> None:
        self._engine: Engine | None = None
        self._is_libsql: bool = False

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._engine

    @property
    def dialect(self) -> str:
        return self.engine.dialect.name

    @property
    def is_libsql(self) -> bool:
        return self._is_libsql

    def connect(
        self,
        url: str,
        *,
        turso_auth_token: str = "",
        turso_local_replica_path: str = "",
        turso_sync_interval_seconds: int = 60,
    ) -> None:
        if _is_libsql_url(url):
            self._engine = _build_libsql_engine(
                url,
                auth_token=turso_auth_token,
                local_replica_path=turso_local_replica_path,
                sync_interval_seconds=turso_sync_interval_seconds,
            )
            self._is_libsql = True
        else:
            self._engine = create_engine(url, pool_pre_ping=True)
            event.listen(self._engine, "connect", _enable_sqlite_pragmas)
            self._is_libsql = False

        safe_url = self._engine.url.render_as_string(hide_password=True)
        logger.debug("Engine created for %s (dialect=%s)", safe_url, self._engine.dialect.name)

    def disconnect(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            logger.debug("Engine disposed")

    def execute(
        self, sql: str, *, row_limit: int = 1000, timeout: int = 30, read_only: bool = False
    ) -> list[dict]:
        start = time.time()
        # PRAGMA query_only is unsupported on libSQL/Turso — read-only enforcement
        # for libSQL relies entirely on FORBIDDEN_SQL_RE at the validation layer.
        use_query_only_pragma = read_only and self.dialect == "sqlite" and not self._is_libsql
        with self.engine.connect() as conn:
            if use_query_only_pragma:
                conn.execute(text("PRAGMA query_only = ON"))
            try:
                result = conn.execute(text(sql))
                if result.returns_rows:
                    columns = list(result.keys())
                    rows = [dict(zip(columns, row)) for row in result.fetchmany(row_limit)]
                    ms = (time.time() - start) * 1000
                    logger.debug("SQL (%.0fms, %d rows): %s", ms, len(rows), sql[:200])
                    return rows
                conn.commit()
                ms = (time.time() - start) * 1000
                logger.debug("SQL (%.0fms, %d affected): %s", ms, result.rowcount, sql[:200])
                return [{"affected_rows": result.rowcount}]
            finally:
                if use_query_only_pragma:
                    conn.execute(text("PRAGMA query_only = OFF"))

    def get_tables(self) -> list[str]:
        from sqlalchemy import inspect

        inspector = inspect(self.engine)
        tables = inspector.get_table_names()
        logger.debug("Tables: %s", tables)
        return tables
