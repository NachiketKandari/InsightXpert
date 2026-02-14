from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncGenerator, Protocol, runtime_checkable


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class LLMChunk:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    done: bool = False


@runtime_checkable
class LLMProvider(Protocol):
    async def chat(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> LLMResponse: ...

    async def chat_stream(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> AsyncGenerator[LLMChunk, None]: ...
