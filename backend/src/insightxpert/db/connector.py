from __future__ import annotations

import logging
import re
import time

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger("insightxpert.db")

FORBIDDEN_SQL_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|MERGE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)


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

    def connect(self, url: str, *, cloud_sql_connection_name: str = "") -> None:
        if cloud_sql_connection_name:
            # Cloud SQL Unix socket: override host portion of the URL
            # Expected format: postgresql://user:pass@/dbname?host=/cloudsql/<connection-name>
            from urllib.parse import urlparse, urlunparse, urlencode, parse_qs

            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            qs["host"] = [f"/cloudsql/{cloud_sql_connection_name}"]
            new_query = urlencode(qs, doseq=True)
            url = urlunparse(parsed._replace(query=new_query, netloc=f"{parsed.username}:{parsed.password}@"))

        self._engine = create_engine(
            url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )

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
