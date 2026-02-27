from __future__ import annotations

import logging
import time

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

logger = logging.getLogger("insightxpert.db")


def _enable_sqlite_fks(dbapi_conn, connection_record):
    """Enable foreign key enforcement for every new SQLite connection."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.close()


class DatabaseConnector:
    def __init__(self) -> None:
        self._engine: Engine | None = None
        self._is_libsql_remote: bool = False

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._engine

    @property
    def dialect(self) -> str:
        return self.engine.dialect.name

    def connect(self, url: str, *, auth_token: str = "") -> None:
        connect_args: dict = {}
        kwargs: dict = {"pool_pre_ping": True}

        # Normalize libsql:// → sqlite+libsql:// for SQLAlchemy dialect resolution
        # and add ?secure=true for remote Turso connections (required for HTTPS)
        if url.startswith("libsql://"):
            host_part = url[len("libsql://"):]
            url = f"sqlite+libsql://{host_part}?secure=true"
            self._is_libsql_remote = True
        elif "libsql" in url and "://" in url and "///" not in url:
            # Already sqlite+libsql:// with remote host
            self._is_libsql_remote = True

        if self._is_libsql_remote:
            # Turso streams expire server-side; the libSQL driver raises ValueError
            # (not a DBAPI error) so pool_pre_ping can't recover stale connections.
            # NullPool gives each Session a fresh HTTP stream with zero reuse.
            kwargs["poolclass"] = NullPool
            kwargs.pop("pool_pre_ping", None)

        if "libsql" in url and auth_token:
            connect_args = {"auth_token": auth_token}
        elif url.startswith("postgresql"):
            kwargs.update(pool_size=5, max_overflow=10)
        elif url.startswith("mysql"):
            connect_args = {"charset": "utf8mb4"}
            kwargs.update(pool_size=5, max_overflow=10)

        self._engine = create_engine(url, connect_args=connect_args, **kwargs)

        # Only enable PRAGMA foreign_keys for local SQLite (PRAGMAs fail on remote Turso)
        if url.startswith("sqlite") and not self._is_libsql_remote:
            event.listen(self._engine, "connect", _enable_sqlite_fks)

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
        with self.engine.connect() as conn:
            if read_only and self.dialect in ("sqlite",) and not self._is_libsql_remote:
                conn.execute(text("PRAGMA query_only = ON"))
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

    def get_tables(self) -> list[str]:
        from sqlalchemy import inspect

        inspector = inspect(self.engine)
        tables = inspector.get_table_names()
        logger.debug("Tables: %s", tables)
        return tables
