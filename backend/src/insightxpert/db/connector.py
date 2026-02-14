from __future__ import annotations

import logging
import time

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger("insightxpert.db")


class DatabaseConnector:
    def __init__(self) -> None:
        self._engine: Engine | None = None

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._engine

    def connect(self, url: str) -> None:
        self._engine = create_engine(url, pool_pre_ping=True)
        logger.debug("Engine created for %s", url)

    def disconnect(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            logger.debug("Engine disposed")

    def execute(
        self, sql: str, *, row_limit: int = 1000, timeout: int = 30
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
