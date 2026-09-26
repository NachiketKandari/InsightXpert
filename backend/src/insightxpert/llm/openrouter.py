"""OpenRouter LLM provider — OpenAI-compatible chat completions endpoint.

OpenRouter (https://openrouter.ai/api/v1) exposes 100+ models behind a single
OpenAI-compatible API. Authentication uses a Bearer token (OPENROUTER_API_KEY).

Model is fully env-driven via OPENROUTER_CHAT_MODEL, e.g.
``nvidia/nemotron-3-ultra-550b-a55b:free``.

OpenRouter recommends sending HTTP-Referer / X-Title for attribution; both are
optional and configured via OPENROUTER_SITE_URL / OPENROUTER_APP_NAME.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

import httpx

from .base import LLMResponse, ToolCall, log_llm_response

logger = logging.getLogger("insightxpert.llm.openrouter")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider:
    """LLM provider for any model hosted on OpenRouter.

    Implements the ``LLMProvider`` protocol defined in ``llm/base.py``.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "nvidia/nemotron-3-ultra-550b-a55b:free",
        base_url: str = OPENROUTER_BASE_URL,
        site_url: str = "",
        app_name: str = "InsightXpert",
    ) -> None:
        if not api_key:
            raise ValueError("openrouter_api_key is required for the openrouter provider")

        self._model = model
        self._base_url = (base_url or OPENROUTER_BASE_URL).rstrip("/")
        self._endpoint = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if site_url:
            headers["HTTP-Referer"] = site_url
        if app_name:
            headers["X-Title"] = app_name
        self._http_client = httpx.AsyncClient(timeout=120.0, headers=headers)

        logger.debug("OpenRouterProvider initialized (model=%s, base_url=%s)", model, self._base_url)

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
        """Send a chat request to the OpenRouter chat completions endpoint."""
        msg_count = len(messages)
        tool_count = len(tools) if tools else 0
        logger.debug("chat() messages=%d tools=%d force_tool=%s model=%s",
                      msg_count, tool_count, force_tool_use, self._model)

        body: dict = {
            "model": self._model,
            "messages": self._convert_messages(messages),
            "stream": False,
        }
        if tools:
            body["tools"] = self._convert_tools(tools)
        if force_tool_use and tools:
            body["tool_choice"] = "auto"

        max_retries = 4
        base_delay = 2.0

        start = time.time()
        for attempt in range(max_retries + 1):
            resp = await self._http_client.post(self._endpoint, json=body)

            if resp.status_code == 429 and attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "OpenRouter 429 rate-limited (attempt %d/%d), retrying in %.0fs",
                    attempt + 1, max_retries + 1, delay,
                )
                await asyncio.sleep(delay)
                continue

            break

        ms = (time.time() - start) * 1000

        if resp.status_code != 200:
            error_text = resp.text[:500]
            logger.error("OpenRouter API error %d: %s", resp.status_code, error_text)
            raise RuntimeError(f"OpenRouter API returned {resp.status_code}: {error_text}")

        parsed = self._parse_response(resp.json())
        log_llm_response(logger, ms, parsed)
        return parsed
