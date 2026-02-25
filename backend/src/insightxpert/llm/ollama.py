from __future__ import annotations

import json
import logging
import time
import uuid
import ollama as ollama_sdk

from .base import LLMResponse, ToolCall, log_llm_response

logger = logging.getLogger("insightxpert.llm.ollama")


class OllamaProvider:
    def __init__(self, model: str = "llama3.1", base_url: str = "http://localhost:11434", timeout: float = 120.0) -> None:
        self._model = model
        self._base_url = base_url
        self._client = ollama_sdk.AsyncClient(host=base_url, timeout=timeout)
        logger.debug("OllamaProvider initialized (model=%s, url=%s, timeout=%.0fs)", model, base_url, timeout)

    @property
    def model(self) -> str:
        return self._model

    def _convert_tools(self, tools: list[dict] | None) -> list[dict] | None:
        if not tools:
            return None
        ollama_tools = []
        for t in tools:
            ollama_tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                },
            })
        return ollama_tools

    def _convert_messages(self, messages: list[dict]) -> list[dict]:
        converted = []
        for msg in messages:
            if msg["role"] == "tool":
                converted.append({
                    "role": "tool",
                    "content": msg["content"] if isinstance(msg["content"], str) else json.dumps(msg["content"]),
                })
            elif msg["role"] == "assistant" and msg.get("tool_calls"):
                converted.append({
                    "role": "assistant",
                    "content": msg.get("content", ""),
                    "tool_calls": [
                        {
                            "function": {
                                "name": tc.name,
                                "arguments": tc.arguments,
                            }
                        }
                        for tc in msg["tool_calls"]
                    ],
                })
            else:
                converted.append({"role": msg["role"], "content": msg["content"]})
        return converted

    def _parse_tool_calls(self, message: dict) -> list[ToolCall]:
        tool_calls = []
        for tc in message.get("tool_calls", []):
            fn = tc.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, str):
                args = json.loads(args)
            tool_calls.append(ToolCall(
                id=str(uuid.uuid4())[:8],
                name=fn.get("name", ""),
                arguments=args,
            ))
        return tool_calls

    async def chat(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> LLMResponse:
        msg_count = len(messages)
        tool_count = len(tools) if tools else 0
        logger.debug("chat() messages=%d tools=%d model=%s", msg_count, tool_count, self._model)

        start = time.time()
        response = await self._client.chat(
            model=self._model,
            messages=self._convert_messages(messages),
            tools=self._convert_tools(tools),
        )
        ms = (time.time() - start) * 1000

        msg = response.message
        content = msg.content
        raw_tool_calls = getattr(msg, "tool_calls", None)
        tool_calls = self._parse_tool_calls({"tool_calls": raw_tool_calls}) if raw_tool_calls else []

        result = LLMResponse(content=content or None, tool_calls=tool_calls)
        log_llm_response(logger, ms, result)
        return result
