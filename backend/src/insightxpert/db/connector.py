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
        from sqlalchemy.pool import StaticPool

        # Embedded replica WITHOUT background sync_interval. Background sync
        # races with active SQLAlchemy queries: libSQL's sync thread calls
        # `wal_insert_begin` to apply remote frames into the local WAL while
        # SQLAlchemy holds the file via concurrent connections, producing
        # "wal_insert_begin failed" errors that propagate as ValueError and
        # block writes (e.g. user registration).
        #
        # Trade-off: without periodic sync, the replica only refreshes on
        # explicit `conn.sync()` calls. The libSQL client syncs on connection
        # open, so each new connection sees the latest committed state.
        # Combined with StaticPool (one connection for the whole engine),
        # all queries serialize through a single libSQL connection that
        # writes-through to the remote primary and reads from local file.
        # For this app's traffic profile this is plenty fast and avoids the
        # WAL contention entirely.
        _connect_kwargs: dict = {
            "database": local_replica_path,
            "sync_url": sync_url,
            "auth_token": auth_token,
        }

        try:
            _bootstrap = libsql.connect(**_connect_kwargs)
            _bootstrap.sync()
            _bootstrap.close()
            logger.info("libSQL initial sync complete (replica=%s)", local_replica_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Initial libSQL sync failed (will retry on first query): %s", exc)

        def _creator():
            return libsql.connect(**_connect_kwargs)

        engine = create_engine(
            "sqlite+libsql://",
            creator=_creator,
            poolclass=StaticPool,
            pool_pre_ping=False,  # StaticPool: single conn, ping is meaningless
        )
        logger.info(
            "libSQL embedded-replica engine ready (local=%s, sync_url=%s, pool=Static)",
            local_replica_path, sync_url,
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
