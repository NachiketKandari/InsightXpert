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


def _enable_sqlite_pragmas(dbapi_conn, connection_record):
    """Enable foreign key enforcement and WAL mode for every new SQLite connection."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.close()


class DatabaseConnector:
    def __init__(self) -> None:
        self._engine: Engine | None = None

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._engine

    @property
    def dialect(self) -> str:
        return self.engine.dialect.name

    def connect(self, url: str) -> None:
        self._engine = create_engine(url, pool_pre_ping=True)
        event.listen(self._engine, "connect", _enable_sqlite_pragmas)

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
        _sqlite_local = self.dialect == "sqlite"
        with self.engine.connect() as conn:
            if read_only and _sqlite_local:
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
                # Reset query_only so the connection isn't returned to the pool in
                # read-only state, which would cause writes from other callers sharing
                # the same engine (e.g. PersistentConversationStore) to fail with
                # "attempt to write a readonly database".
                if read_only and _sqlite_local:
                    conn.execute(text("PRAGMA query_only = OFF"))

    def get_tables(self) -> list[str]:
        from sqlalchemy import inspect

        inspector = inspect(self.engine)
        tables = inspector.get_table_names()
        logger.debug("Tables: %s", tables)
        return tables
