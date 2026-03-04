from __future__ import annotations

import asyncio
import json
import logging

from insightxpert.agents.sql_guard import FORBIDDEN_SQL_RE, validate_tables
from insightxpert.agents.tool_base import Tool, ToolContext, ToolRegistry
from insightxpert.db.connector import ExternalDatabaseConnector

logger = logging.getLogger("insightxpert.tools")


class RunSqlTool(Tool):
    @property
    def name(self) -> str:
        return "run_sql"

    @property
    def description(self) -> str:
        return "Execute a SQL query against the connected database and return the results. Use SELECT queries to retrieve data."

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

        if context.allowed_tables is not None:
            error = validate_tables(sql, context.allowed_tables)
            if error:
                return json.dumps({"error": error})

        if context.use_external_db and context.external_db_config is not None:
            return await self._execute_external(context, args)

        rows = await asyncio.to_thread(
            context.db.execute,
            sql,
            row_limit=context.row_limit,
        )
        logger.debug("run_sql returned %d rows", len(rows))
        return json.dumps({"rows": rows, "row_count": len(rows)}, default=str)

    async def _execute_external(self, context: ToolContext, args: dict) -> str:
        sql = args["sql"]
        assert context.external_db_config is not None

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


class GetSchemaTool(Tool):
    @property
    def name(self) -> str:
        return "get_schema"

    @property
    def description(self) -> str:
        return "Get the CREATE TABLE DDL statements for database tables. Call with no arguments to get all tables, or specify table names."

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
        from insightxpert.db.schema import get_schema_ddl, get_table_info

        tables = args.get("tables", [])

        if context.use_external_db and context.external_db_config is not None:
            return await self._execute_external(context, args)

        # Filter to allowed tables when dataset isolation is active
        if context.allowed_tables is not None:
            allowed_lower = {t.lower() for t in context.allowed_tables}
            if tables:
                tables = [t for t in tables if t.lower() in allowed_lower]
                if not tables:
                    return json.dumps(
                        {
                            "error": "None of the requested tables are in the active dataset."
                        }
                    )
            else:
                # No specific tables requested — return only allowed tables
                tables = sorted(context.allowed_tables)

        if tables:
            results = await asyncio.gather(
                *(
                    asyncio.to_thread(get_table_info, context.db.engine, t)
                    for t in tables
                )
            )
            logger.debug("get_schema returned info for tables: %s", tables)
            return json.dumps(list(results), default=str)
        else:
            ddl = await asyncio.to_thread(get_schema_ddl, context.db.engine)
            logger.debug("get_schema returned full DDL (%d chars)", len(ddl))
            return ddl

    async def _execute_external(self, context: ToolContext, args: dict) -> str:
        tables = args.get("tables", [])
        assert context.external_db_config is not None

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
                info = ext_connector.get_columns(table)
                ddl_parts = [f'    "{col["name"]}" {col["type"]}' for col in info]
                ddl = f'CREATE TABLE "{table}" (\n' + ",\n".join(ddl_parts) + "\n);"
                results.append(ddl)

            return json.dumps(results, default=str)
        except Exception as e:
            logger.error("External DB get_schema failed: %s", e, exc_info=True)
            return json.dumps({"error": str(e)})
        finally:
            ext_connector.disconnect()


class ClarifyTool(Tool):
    """Ask the user a clarifying question when their request is ambiguous."""

    @property
    def name(self) -> str:
        return "clarify"

    @property
    def description(self) -> str:
        return (
            "Ask the user a clarifying question when their request references "
            "data that doesn't exist in the schema or is ambiguous. Suggest "
            "the closest available column as an option."
        )

    def get_args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The clarifying question to ask the user",
                },
            },
            "required": ["question"],
        }

    async def execute(self, context: ToolContext, args: dict) -> str:
        return json.dumps({"clarification": args["question"]})


class SearchSimilarTool(Tool):
    @property
    def name(self) -> str:
        return "search_similar"

    @property
    def description(self) -> str:
        return "Search the knowledge base for similar past queries, relevant DDL, or documentation that might help answer the question."

    def get_args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                },
                "collection": {
                    "type": "string",
                    "enum": ["qa_pairs", "ddl", "docs"],
                    "description": "Which collection to search: qa_pairs, ddl, or docs",
                },
            },
            "required": ["query", "collection"],
        }

    async def execute(self, context: ToolContext, args: dict) -> str:
        query = args["query"]
        collection = args["collection"]
        if collection == "qa_pairs":
            items = await asyncio.to_thread(
                context.rag.search_qa,
                query,
                max_distance=1.0,
                sql_valid_only=True,
                dataset_id=context.dataset_id,
                org_id=context.org_id,
            )
        elif collection == "ddl":
            items = await asyncio.to_thread(
                context.rag.search_ddl,
                query,
                dataset_id=context.dataset_id,
                org_id=context.org_id,
            )
        elif collection == "docs":
            items = await asyncio.to_thread(
                context.rag.search_docs,
                query,
                dataset_id=context.dataset_id,
                org_id=context.org_id,
            )
        else:
            logger.warning("Unknown collection: %s", collection)
            return json.dumps({"error": f"Unknown collection: {collection}"})
        logger.debug(
            "search_similar(%s, %s) returned %d items",
            collection,
            query[:50],
            len(items),
        )
        return json.dumps(items, default=str)


def default_registry(*, clarification_enabled: bool = False) -> ToolRegistry:
    """Create and return a ToolRegistry pre-loaded with all built-in tools."""
    registry = ToolRegistry()
    registry.register(RunSqlTool())
    registry.register(GetSchemaTool())
    registry.register(SearchSimilarTool())
    if clarification_enabled:
        registry.register(ClarifyTool())
    return registry
