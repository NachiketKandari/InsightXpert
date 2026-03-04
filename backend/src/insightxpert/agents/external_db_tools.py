"""External database tool registry.

The actual tool implementations (RunSqlTool, GetSchemaTool) live in
``insightxpert.agents.tools`` and already handle external DB routing via
their ``_execute_external`` helper methods.  This module provides registry
factories that re-use those tools for callers that need a dedicated
external-DB tool registry.
"""

from __future__ import annotations

from insightxpert.agents.tool_base import ToolContext, ToolRegistry
from insightxpert.agents.tools import GetSchemaTool, RunSqlTool


def external_db_registry() -> ToolRegistry:
    """Create and return a ToolRegistry configured for external database access."""
    registry = ToolRegistry()
    registry.register(RunSqlTool())
    registry.register(GetSchemaTool())
    return registry


class ExternalDbToolRegistry:
    """Wrapper class to distinguish external DB tool registry."""

    def __init__(self) -> None:
        self._registry = ToolRegistry()
        self._registry.register(RunSqlTool())
        self._registry.register(GetSchemaTool())

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    def get_schemas(self) -> list[dict]:
        return self._registry.get_schemas()

    async def execute(self, name: str, args: dict, context: ToolContext) -> str:
        return await self._registry.execute(name, args, context)
