from __future__ import annotations

import json
import logging
import traceback

from insightxpert.db.connector import DatabaseConnector
from insightxpert.rag.store import VectorStore

logger = logging.getLogger("insightxpert.tools")

TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "run_sql",
        "description": "Execute a SQL query against the connected database and return the results. Use SELECT queries to retrieve data.",
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "The SQL query to execute",
                }
            },
            "required": ["sql"],
        },
    },
    {
        "name": "get_schema",
        "description": "Get the CREATE TABLE DDL statements for database tables. Call with no arguments to get all tables, or specify table names.",
        "parameters": {
            "type": "object",
            "properties": {
                "tables": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of specific table names. If empty, returns all tables.",
                }
            },
        },
    },
    {
        "name": "search_similar",
        "description": "Search the knowledge base for similar past queries, relevant DDL, or documentation that might help answer the question.",
        "parameters": {
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
        },
    },
]


async def execute_tool(
    tool_name: str, arguments: dict, db: DatabaseConnector, rag: VectorStore,
    *, row_limit: int = 1000,
) -> str:
    logger.debug("execute_tool(%s, %s)", tool_name, json.dumps(arguments, default=str)[:300])
    try:
        if tool_name == "run_sql":
            rows = db.execute(arguments["sql"], row_limit=row_limit)
            logger.debug("run_sql returned %d rows", len(rows))
            return json.dumps({"rows": rows, "row_count": len(rows)}, default=str)

        elif tool_name == "get_schema":
            from insightxpert.db.schema import get_schema_ddl, get_table_info
            tables = arguments.get("tables", [])
            if tables:
                results = []
                for t in tables:
                    info = get_table_info(db.engine, t)
                    results.append(info)
                logger.debug("get_schema returned info for tables: %s", tables)
                return json.dumps(results, default=str)
            else:
                ddl = get_schema_ddl(db.engine)
                logger.debug("get_schema returned full DDL (%d chars)", len(ddl))
                return ddl

        elif tool_name == "search_similar":
            query = arguments["query"]
            collection = arguments["collection"]
            if collection == "qa_pairs":
                items = rag.search_qa(query)
            elif collection == "ddl":
                items = rag.search_ddl(query)
            elif collection == "docs":
                items = rag.search_docs(query)
            else:
                logger.warning("Unknown collection: %s", collection)
                return json.dumps({"error": f"Unknown collection: {collection}"})
            logger.debug("search_similar(%s, %s) returned %d items", collection, query[:50], len(items))
            return json.dumps(items, default=str)

        else:
            logger.warning("Unknown tool: %s", tool_name)
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    except Exception as e:
        logger.error("Tool %s failed: %s", tool_name, e, exc_info=True)
        return json.dumps({"error": str(e), "traceback": traceback.format_exc()})
