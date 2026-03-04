from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import List

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger("insightxpert.db.introspector")

DEFAULT_TIMEOUT = 30


@dataclass
class ColumnInfo:
    name: str
    data_type: str
    is_nullable: bool
    default_value: str | None
    is_primary_key: bool
    is_foreign_key: bool


@dataclass
class TableInfo:
    name: str
    row_count: int | None
    columns: List[ColumnInfo] = field(default_factory=list)


@dataclass
class ForeignKeyInfo:
    column_name: str
    referenced_table: str
    referenced_column: str


@dataclass
class SchemaInfo:
    tables: List[TableInfo]
    foreign_keys: List[ForeignKeyInfo]
    database_name: str


class SchemaIntrospector:
    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        *,
        connection_type: str = "postgresql",
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.host = host
        self.port = port
        self.database = database
        self.username = username
        self.password = password
        self.connection_type = connection_type
        self.timeout = timeout
        self._engine: Engine | None = None

    def _build_url(self) -> str:
        raise NotImplementedError

    def _connect(self) -> Engine:
        if self._engine is not None:
            return self._engine

        url = self._build_url()
        self._engine = create_engine(
            url,
            pool_size=2,
            max_overflow=5,
            pool_pre_ping=True,
            connect_args={"connect_timeout": self.timeout},
        )
        return self._engine

    def _get_inspector(self) -> inspect:
        return inspect(self._connect())

    def get_tables(self) -> List[TableInfo]:
        inspector = self._get_inspector()
        table_names = inspector.get_table_names()
        return [
            TableInfo(
                name=name,
                row_count=None,
                columns=self.get_columns(name),
            )
            for name in table_names
        ]

    def get_columns(self, table_name: str) -> List[ColumnInfo]:
        inspector = self._get_inspector()
        columns = inspector.get_columns(table_name)
        primary_keys = set(
            inspector.get_pk_constraint(table_name).get("constrained_columns", [])
        )
        foreign_keys = {fk["column"] for fk in inspector.get_foreign_keys(table_name)}

        return [
            ColumnInfo(
                name=col["name"],
                data_type=str(col["type"]),
                is_nullable=col.get("nullable", True),
                default_value=col.get("default"),
                is_primary_key=col["name"] in primary_keys,
                is_foreign_key=col["name"] in foreign_keys,
            )
            for col in columns
        ]

    def get_foreign_keys(self, table_name: str) -> List[ForeignKeyInfo]:
        inspector = self._get_inspector()
        fks = inspector.get_foreign_keys(table_name)
        return [
            ForeignKeyInfo(
                column_name=fk["constrained_columns"][0],
                referenced_table=fk["referred_table"],
                referenced_column=fk["referred_columns"][0],
            )
            for fk in fks
        ]

    def get_schema(self) -> SchemaInfo:
        tables = self.get_tables()
        all_fks: List[ForeignKeyInfo] = []
        for table in tables:
            all_fks.extend(self.get_foreign_keys(table.name))

        return SchemaInfo(
            tables=tables,
            foreign_keys=all_fks,
            database_name=self.database,
        )

    def test_connection(self) -> bool:
        try:
            engine = self._connect()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.warning("Connection test failed: %s", e)
            return False

    def disconnect(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None


class PostgresIntrospector(SchemaIntrospector):
    def _build_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.username}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )


class MySQLIntrospector(SchemaIntrospector):
    def _build_url(self) -> str:
        return (
            f"mysql+pymysql://{self.username}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )


async def get_introspector(
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
    *,
    connection_type: str = "postgresql",
    timeout: int = DEFAULT_TIMEOUT,
) -> SchemaIntrospector:
    if connection_type == "postgresql":
        return PostgresIntrospector(
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
            timeout=timeout,
        )
    elif connection_type == "mysql":
        return MySQLIntrospector(
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
            timeout=timeout,
        )
    else:
        raise ValueError(f"Unsupported connection type: {connection_type}")


async def async_test_connection(
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
    *,
    connection_type: str = "postgresql",
    timeout: int = DEFAULT_TIMEOUT,
) -> bool:
    introspector = await get_introspector(
        host=host,
        port=port,
        database=database,
        username=username,
        password=password,
        connection_type=connection_type,
        timeout=timeout,
    )
    return await asyncio.to_thread(introspector.test_connection)
