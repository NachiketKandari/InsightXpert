from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from insightxpert.db.connector import DatabaseConnector

if TYPE_CHECKING:
    from insightxpert.rag.base import VectorStoreBackend

logger = logging.getLogger("insightxpert.tool_base")


@dataclass
class ToolContext:
    db: DatabaseConnector
    rag: VectorStoreBackend
    row_limit: int = 1000
    analyst_results: list[dict] | None = None
    analyst_sql: str | None = None
    allowed_tables: set[str] | None = None
    dataset_id: str | None = None
    org_id: str | None = None


class Tool(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @abstractmethod
    def get_args_schema(self) -> dict: ...

    @abstractmethod
    async def execute(self, context: ToolContext, args: dict) -> str: ...

    def get_definition(self) -> dict:
        """Build the JSON schema dict for LLM tool calling."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.get_args_schema(),
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        logger.debug("Registered tool: %s", tool.name)

    def get_schemas(self) -> list[dict]:
        return [tool.get_definition() for tool in self._tools.values()]

    async def execute(self, name: str, args: dict, context: ToolContext) -> str:
        tool = self._tools.get(name)
        if tool is None:
            logger.warning("Unknown tool: %s", name)
            return json.dumps({"error": f"Unknown tool: {name}"})
        logger.debug("execute(%s, %s)", name, json.dumps(args, default=str)[:300])
        try:
            return await tool.execute(context, args)
        except Exception as e:
            logger.error("Tool %s failed: %s", name, e, exc_info=True)
            return json.dumps({"error": str(e)})
