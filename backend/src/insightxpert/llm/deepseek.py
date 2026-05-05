"""DeepSeek LLM provider — calls the OpenAI-compatible chat completions endpoint.

DeepSeek's API (https://api.deepseek.com) is fully OpenAI-compatible, supporting
standard message/tool/streaming formats and the ``tool_choice`` parameter.

Authentication uses a simple Bearer token (API key).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

import httpx

from .base import LLMResponse, ToolCall, log_llm_response

logger = logging.getLogger("insightxpert.llm.deepseek")

DEEPSEEK_BASE_URL = "https://api.deepseek.com"


class DeepSeekProvider:
    """LLM provider for DeepSeek (OpenAI-compatible endpoint).

    Implements the ``LLMProvider`` protocol defined in ``llm/base.py``.
    """

    def __init__(self, api_key: str, model: str = "deepseek-v4-flash") -> None:
        if not api_key:
            raise ValueError("deepseek_api_key is required for the deepseek provider")

        self._model = model
        self._api_key = api_key
        self._endpoint = f"{DEEPSEEK_BASE_URL}/chat/completions"
        self._http_client = httpx.AsyncClient(
            timeout=120.0,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

        logger.debug("DeepSeekProvider initialized (model=%s)", model)

    @property
    def model(self) -> str:
        return self._model

    def _convert_tools(self, tools: list[dict] | None) -> list[dict] | None:
        """Convert internal tool schema list to OpenAI function-calling format."""
        if not tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                },
            }
            for t in tools
        ]

    def _convert_messages(self, messages: list[dict]) -> list[dict]:
        """Convert internal message format to OpenAI chat format."""
        converted = []
        for msg in messages:
            role = msg["role"]
            if role == "tool":
                content = msg["content"]
                if not isinstance(content, str):
                    content = json.dumps(content)
                converted.append({
                    "role": "tool",
                    "content": content,
                    "tool_call_id": msg.get("tool_call_id", ""),
                })
            elif role == "assistant" and msg.get("tool_calls"):
                entry: dict = {
                    "role": "assistant",
                    "content": msg.get("content") or None,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments) if isinstance(tc.arguments, dict) else tc.arguments,
                            },
                        }
                        for tc in msg["tool_calls"]
                    ],
                }
                if msg.get("reasoning_content"):
                    entry["reasoning_content"] = msg["reasoning_content"]
                converted.append(entry)
            else:
                converted.append({"role": role, "content": msg["content"]})
        return converted

    def _parse_response(self, data: dict) -> LLMResponse:
        """Parse an OpenAI-format chat completion response."""
        content = None
        tool_calls: list[ToolCall] = []
        reasoning_content = None

        choices = data.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            content = message.get("content")
            reasoning_content = message.get("reasoning_content")

            for tc in message.get("tool_calls") or []:
                fn = tc.get("function", {})
                args = fn.get("arguments", "{}")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"raw": args}
                tool_calls.append(ToolCall(
                    id=tc.get("id", str(uuid.uuid4())[:8]),
                    name=fn.get("name", ""),
                    arguments=args,
                ))

        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_content=reasoning_content,
        )

    async def chat(
        self, messages: list[dict], tools: list[dict] | None = None,
        force_tool_use: bool = False,
    ) -> LLMResponse:
        """Send a chat request to the DeepSeek OpenAI-compatible endpoint.

        Args:
            messages: OpenAI-style message list (system/user/assistant/tool).
            tools: Optional list of tool schemas in OpenAI function-calling format.
            force_tool_use: When True and tools are provided, sets
                ``tool_choice: "required"`` to force the model to call a tool.
        """
        msg_count = len(messages)
        tool_count = len(tools) if tools else 0
        logger.debug("chat() messages=%d tools=%d force_tool=%s model=%s",
                      msg_count, tool_count, force_tool_use, self._model)

        body: dict = {
            "model": self._model,
            "messages": self._convert_messages(messages),
            "stream": False,
            # deepseek-v4-flash defaults to thinking mode which requires
            # reasoning_content round-trips across tool calls. Disable it
            # for straightforward non-thinking tool use.
            "thinking": {"type": "disabled"},
        }
        if tools:
            body["tools"] = self._convert_tools(tools)
        if force_tool_use and tools:
            # Use "auto" instead of "required" — deepseek-v4-flash routes
            # "required" through the legacy reasoner pipeline which rejects
            # it. The agent guard rail handles cases where the model skips
            # tools, so "auto" is safe.
            body["tool_choice"] = "auto"

        max_retries = 4
        base_delay = 2.0

        start = time.time()
        for attempt in range(max_retries + 1):
            resp = await self._http_client.post(self._endpoint, json=body)

            if resp.status_code == 429 and attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "DeepSeek 429 rate-limited (attempt %d/%d), retrying in %.0fs",
                    attempt + 1, max_retries + 1, delay,
                )
                await asyncio.sleep(delay)
                continue

            break

        ms = (time.time() - start) * 1000

        if resp.status_code != 200:
            error_text = resp.text[:500]
            logger.error("DeepSeek API error %d: %s", resp.status_code, error_text)
            raise RuntimeError(f"DeepSeek API returned {resp.status_code}: {error_text}")

        parsed = self._parse_response(resp.json())
        log_llm_response(logger, ms, parsed)
        return parsed
