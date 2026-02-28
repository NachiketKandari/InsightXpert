from __future__ import annotations

import asyncio
import json
import logging

from insightxpert.agents.tool_base import Tool, ToolContext, ToolRegistry

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
        rows = await asyncio.to_thread(
            context.db.execute, args["sql"], row_limit=context.row_limit,
        )
        logger.debug("run_sql returned %d rows", len(rows))
        return json.dumps({"rows": rows, "row_count": len(rows)}, default=str)


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
        if tables:
            results = await asyncio.gather(
                *(asyncio.to_thread(get_table_info, context.db.engine, t) for t in tables)
            )
            logger.debug("get_schema returned info for tables: %s", tables)
            return json.dumps(list(results), default=str)
        else:
            ddl = await asyncio.to_thread(get_schema_ddl, context.db.engine)
            logger.debug("get_schema returned full DDL (%d chars)", len(ddl))
            return ddl


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
                context.rag.search_qa, query, max_distance=1.0, sql_valid_only=True,
            )
        elif collection == "ddl":
            items = await asyncio.to_thread(context.rag.search_ddl, query)
        elif collection == "docs":
            items = await asyncio.to_thread(context.rag.search_docs, query)
        else:
            logger.warning("Unknown collection: %s", collection)
            return json.dumps({"error": f"Unknown collection: {collection}"})
        logger.debug("search_similar(%s, %s) returned %d items", collection, query[:50], len(items))
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
