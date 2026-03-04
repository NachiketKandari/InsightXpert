from __future__ import annotations

import asyncio
import json
import logging

from insightxpert.agents.sql_guard import FORBIDDEN_SQL_RE
from insightxpert.agents.tool_base import Tool, ToolContext, ToolRegistry
from insightxpert.db.connector import ExternalDatabaseConnector

logger = logging.getLogger("insightxpert.external_db_tools")


class ExternalDbRunSqlTool(Tool):
    @property
    def name(self) -> str:
        return "run_sql"

    @property
    def description(self) -> str:
        return "Execute a SQL query against the external database and return the results. Use SELECT queries to retrieve data."

    def get_args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "The SQL query to execute",
                },
                "visualization": {
                    "type": "string",
                    "enum": ["bar", "pie", "line", "grouped-bar", "table"],
                    "description": "Chart type for the results. 'bar' for category comparisons, 'pie' for proportional breakdowns (2-10 categories), 'line' for temporal trends, 'grouped-bar' for cross-tabulations with 2 category dimensions, 'table' when no chart is appropriate.",
                },
                "x_column": {
                    "type": "string",
                    "description": "Column name from the SELECT to use as the x-axis (categories). Must match a column alias in the query.",
                },
                "y_column": {
                    "type": "string",
                    "description": "Column name from the SELECT to use as the y-axis (values). Must match a column alias in the query. Choose the column that best answers the user's question — e.g. a rate or percentage rather than a raw count.",
                },
            },
            "required": ["sql"],
        }

    async def execute(self, context: ToolContext, args: dict) -> str:
        sql = args["sql"]

        if FORBIDDEN_SQL_RE.match(sql):
            return json.dumps(
                {
                    "error": "Write operations (INSERT, UPDATE, DELETE, DROP, etc.) are not allowed."
                }
            )

        if context.external_db_config is None:
            return json.dumps(
                {"error": "No external database configuration available."}
            )

        ext_connector = ExternalDatabaseConnector(
            context.external_db_config,
            timeout=30,
            row_limit=context.row_limit,
            pool_size=2,
        )

        try:
            ext_connector.connect()
            rows = await asyncio.to_thread(
                ext_connector.execute,
                sql,
                row_limit=context.row_limit,
            )
            logger.debug("external_db_run_sql returned %d rows", len(rows))
            return json.dumps({"rows": rows, "row_count": len(rows)}, default=str)
        except Exception as e:
            logger.error("External DB query failed: %s", e, exc_info=True)
            return json.dumps({"error": str(e)})
        finally:
            ext_connector.disconnect()


class ExternalDbGetSchemaTool(Tool):
    @property
    def name(self) -> str:
        return "get_schema"

    @property
    def description(self) -> str:
        return "Get the CREATE TABLE DDL statements for external database tables. Call with no arguments to get all tables, or specify table names."

    def get_args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "tables": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of specific table names. If empty, returns all tables.",
                }
            },
        }

    async def execute(self, context: ToolContext, args: dict) -> str:
        from insightxpert.db.schema import get_table_info

        tables = args.get("tables", [])

        if context.external_db_config is None:
            return json.dumps(
                {"error": "No external database configuration available."}
            )

        ext_connector = ExternalDatabaseConnector(
            context.external_db_config,
            timeout=30,
            row_limit=1000,
            pool_size=2,
        )

        try:
            ext_connector.connect()

            if not tables:
                tables = ext_connector.get_tables()
                logger.debug("get_schema returned tables: %s", tables)

            results = []
            for table in tables:
                info = await asyncio.to_thread(ext_connector.get_columns, table)
                ddl_parts = [f'    "{col["name"]}" {col["type"]}' for col in info]
                ddl = f'CREATE TABLE "{table}" (\n' + ",\n".join(ddl_parts) + "\n);"
                results.append(ddl)

            return json.dumps(results, default=str)
        except Exception as e:
            logger.error("External DB get_schema failed: %s", e, exc_info=True)
            return json.dumps({"error": str(e)})
        finally:
            ext_connector.disconnect()


def external_db_registry() -> "ToolRegistry":
    """Create and return a ToolRegistry configured for external database access."""
    from insightxpert.agents.tool_base import ToolRegistry

    registry = ToolRegistry()
    registry.register(ExternalDbRunSqlTool())
    registry.register(ExternalDbGetSchemaTool())
    return registry


class ExternalDbToolRegistry:
    """Wrapper class to distinguish external DB tool registry."""

    def __init__(self) -> None:
        from insightxpert.agents.tool_base import ToolRegistry

        self._registry = ToolRegistry()
        self._registry.register(ExternalDbRunSqlTool())
        self._registry.register(ExternalDbGetSchemaTool())

    @property
    def registry(self) -> "ToolRegistry":
        return self._registry

    def get_schemas(self) -> list[dict]:
        return self._registry.get_schemas()

    async def execute(self, name: str, args: dict, context: ToolContext) -> str:
        return await self._registry.execute(name, args, context)
