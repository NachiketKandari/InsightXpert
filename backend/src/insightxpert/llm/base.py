from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


def log_llm_response(logger: logging.Logger, ms: float, response: LLMResponse) -> None:
    if response.tool_calls:
        logger.debug(
            "chat() response (%.0fms): %d tool_calls [%s]",
            ms, len(response.tool_calls), ", ".join(tc.name for tc in response.tool_calls),
        )
    else:
        preview = (response.content or "")[:100]
        logger.debug("chat() response (%.0fms): text=%s...", ms, preview)


@runtime_checkable
class LLMProvider(Protocol):
    @property
    def model(self) -> str: ...

    async def chat(
        self, messages: list[dict], tools: list[dict] | None = None,
        force_tool_use: bool = False,
    ) -> LLMResponse: ...
