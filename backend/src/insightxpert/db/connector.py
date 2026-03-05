from __future__ import annotations

import logging
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Generator, Protocol

from sqlalchemy import URL, create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool

# Duplicated from agents.sql_guard to avoid circular import
# (agents/__init__.py -> orchestrator -> analyst -> db.connector)
FORBIDDEN_SQL_RE = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|ATTACH|DETACH)\b",
    re.IGNORECASE,
)

logger = logging.getLogger("insightxpert.db")


class ExternalDatabaseConnection(Protocol):
    id: int
    host: str
    port: int
    database: str
    username: str
    password: str
    dialect: str


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
        # Forward sslmode from the URL query string to psycopg2 connect_args
        # so Neon (and other hosted PG) connections work correctly.
        connect_args: dict[str, Any] = {}
        if "sslmode=" in url:
            from urllib.parse import parse_qs, urlparse
            qs = parse_qs(urlparse(url).query)
            if "sslmode" in qs:
                connect_args["sslmode"] = qs["sslmode"][0]

        self._engine = create_engine(
            url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            connect_args=connect_args,
        )

        safe_url = self._engine.url.render_as_string(hide_password=True)
        logger.debug(
            "Engine created for %s (dialect=%s)", safe_url, self._engine.dialect.name
        )

        # Verify the connection is reachable
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Connected to database: %s", safe_url)
        except Exception as exc:
            logger.error("Failed to connect to database %s: %s", safe_url, exc)
            raise

    def disconnect(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            logger.debug("Engine disposed")

    def execute(
        self,
        sql: str,
        *,
        row_limit: int = 1000,
        timeout: int = 30,
        read_only: bool = False,
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
            logger.debug(
                "SQL (%.0fms, %d affected): %s", ms, result.rowcount, sql[:200]
            )
            return [{"affected_rows": result.rowcount}]

    def get_tables(self) -> list[str]:
        from sqlalchemy import inspect

        inspector = inspect(self.engine)
        tables = inspector.get_table_names()
        logger.debug("Tables: %s", tables)
        return tables


@dataclass
class ExternalDatabaseConfig:
    id: int
    host: str
    port: int
    database: str
    username: str
    password: str
    dialect: str = "postgresql"


def build_external_db_url(
    config: ExternalDatabaseConnection | ExternalDatabaseConfig,
) -> URL:
    dialect = getattr(config, "dialect", "postgresql")
    driver_map = {"postgresql": "postgresql+psycopg2", "mysql": "mysql+pymysql"}
    return URL.create(
        drivername=driver_map.get(dialect, dialect),
        username=config.username,
        password=config.password,
        host=config.host,
        port=config.port,
        database=config.database,
    )


class ExternalDatabaseConnector:
    def __init__(
        self,
        config: ExternalDatabaseConnection | ExternalDatabaseConfig,
        *,
        timeout: int = 30,
        row_limit: int = 1000,
        pool_size: int = 3,
    ) -> None:
        self.config = config
        self._timeout = timeout
        self._row_limit = row_limit
        self._engine: Engine | None = None
        self._pool_size = pool_size

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            raise RuntimeError("External database not connected. Call connect() first.")
        return self._engine

    @property
    def dialect(self) -> str:
        return self.engine.dialect.name

    def connect(self) -> None:
        url = build_external_db_url(self.config)
        self._engine = create_engine(
            url,
            poolclass=QueuePool,
            pool_size=self._pool_size,
            max_overflow=2,
            pool_pre_ping=True,
            pool_recycle=3600,
            connect_args={
                "connect_timeout": self._timeout,
            },
        )
        safe_url = self._engine.url.render_as_string(hide_password=True)
        logger.debug(
            "External engine created for %s (dialect=%s)",
            safe_url,
            self._engine.dialect.name,
        )

        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Connected to external database: %s", safe_url)
        except Exception as exc:
            logger.error("Failed to connect to external database %s: %s", safe_url, exc)
            raise

    def disconnect(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            logger.debug("External engine disposed")

    def _validate_read_only(self, sql: str) -> None:
        if FORBIDDEN_SQL_RE.search(sql):
            raise PermissionError(
                f"Write operations are not allowed on external databases. "
                f"Query contains forbidden keyword: {sql[:100]}"
            )

    def execute(
        self, sql: str, *, row_limit: int | None = None, timeout: int | None = None
    ) -> list[dict]:
        self._validate_read_only(sql)
        start = time.time()
        effective_row_limit = row_limit if row_limit is not None else self._row_limit
        effective_timeout = timeout if timeout is not None else self._timeout

        with self.engine.connect() as conn:
            result = conn.execute(text(sql))
            if result.returns_rows:
                columns = list(result.keys())
                rows = [
                    dict(zip(columns, row))
                    for row in result.fetchmany(effective_row_limit)
                ]
                ms = (time.time() - start) * 1000
                logger.debug(
                    "External SQL (%.0fms, %d rows): %s", ms, len(rows), sql[:200]
                )
                return rows
            conn.commit()
            ms = (time.time() - start) * 1000
            logger.debug(
                "External SQL (%.0fms, %d affected): %s", ms, result.rowcount, sql[:200]
            )
            return [{"affected_rows": result.rowcount}]

    def execute_many(self, sql: str, params: list[dict[str, Any]]) -> list[dict]:
        self._validate_read_only(sql)
        start = time.time()
        with self.engine.connect() as conn:
            result = conn.execute(text(sql), params)
            conn.commit()
            ms = (time.time() - start) * 1000
            logger.debug(
                "External execute_many (%.0fms, %d affected): %s",
                ms,
                result.rowcount,
                sql[:200],
            )
            return [{"affected_rows": result.rowcount}]

    def get_tables(self) -> list[str]:
        self._validate_read_only("SELECT 1")
        from sqlalchemy import inspect

        inspector = inspect(self.engine)
        tables = inspector.get_table_names()
        logger.debug("External tables: %s", tables)
        return tables

    def get_columns(self, table_name: str) -> list[dict]:
        self._validate_read_only("SELECT 1")
        from sqlalchemy import inspect

        inspector = inspect(self.engine)
        columns = inspector.get_columns(table_name)
        return [
            {
                "name": col["name"],
                "type": str(col["type"]),
                "nullable": col["nullable"],
                "default": col.get("default"),
            }
            for col in columns
        ]

    @contextmanager
    def connection(self) -> Generator[Engine, None, None]:
        with self.engine.connect() as conn:
            yield conn  # type: ignore[return-value]

    def __enter__(self) -> "ExternalDatabaseConnector":
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.disconnect()


class ExternalDatabasePoolManager:
    _instance: "ExternalDatabasePoolManager | None" = None

    def __init__(self) -> None:
        self._pools: dict[int, ExternalDatabaseConnector] = {}
        self._configs: dict[
            int, ExternalDatabaseConnection | ExternalDatabaseConfig
        ] = {}
        self._pool_size = 3
        self._connection_timeout = 30
        self._idle_timeout = 600

    @classmethod
    def get_instance(cls) -> "ExternalDatabasePoolManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(
        self,
        config: ExternalDatabaseConnection | ExternalDatabaseConfig,
        *,
        pool_size: int = 3,
        connection_timeout: int = 30,
        idle_timeout: int = 600,
    ) -> None:
        self._configs[config.id] = config
        self._pool_size = pool_size
        self._connection_timeout = connection_timeout
        self._idle_timeout = idle_timeout
        logger.debug(
            "Registered external database config id=%d (host=%s, pool_size=%d)",
            config.id,
            config.host,
            pool_size,
        )

    def get(self, external_db_id: int) -> ExternalDatabaseConnector:
        if external_db_id not in self._configs:
            raise KeyError(
                f"External database config with id={external_db_id} not registered"
            )

        if external_db_id not in self._pools:
            config = self._configs[external_db_id]
            connector = ExternalDatabaseConnector(
                config,
                timeout=self._connection_timeout,
                row_limit=1000,
                pool_size=self._pool_size,
            )
            connector.connect()
            self._pools[external_db_id] = connector
            logger.debug(
                "Created new connection pool for external_db_id=%d", external_db_id
            )

        return self._pools[external_db_id]

    def release(self, external_db_id: int) -> None:
        if external_db_id in self._pools:
            connector = self._pools.pop(external_db_id)
            connector.disconnect()
            logger.debug(
                "Released connection pool for external_db_id=%d", external_db_id
            )

    def close_all(self) -> None:
        for external_db_id, connector in list(self._pools.items()):
            connector.disconnect()
            logger.debug("Closed connection pool for external_db_id=%d", external_db_id)
        self._pools.clear()
        self._configs.clear()
        logger.info("Closed all external database connections")

    @contextmanager
    def connection(
        self, external_db_id: int
    ) -> Generator[ExternalDatabaseConnector, None, None]:
        connector = self.get(external_db_id)
        yield connector

    def __enter__(self) -> "ExternalDatabasePoolManager":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close_all()
