from __future__ import annotations

import json
import logging
import time
import uuid
from google import genai
from google.genai import types

from .base import LLMResponse, ToolCall, log_llm_response

logger = logging.getLogger("insightxpert.llm.gemini")


class GeminiProvider:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash") -> None:
        self._model = model
        self._client = genai.Client(api_key=api_key)
        logger.debug("GeminiProvider initialized (model=%s)", model)

    @property
    def model(self) -> str:
        return self._model

    def _convert_tools(self, tools: list[dict] | None) -> list[types.Tool] | None:
        if not tools:
            return None
        declarations = []
        for t in tools:
            declarations.append(types.FunctionDeclaration(
                name=t["name"],
                description=t["description"],
                parameters=t["parameters"],
            ))
        return [types.Tool(function_declarations=declarations)]

    def _convert_messages(self, messages: list[dict]) -> tuple[str | None, list[types.Content]]:
        system_instruction = None
        contents: list[types.Content] = []

        for msg in messages:
            role = msg["role"]
            if role == "system":
                system_instruction = msg["content"]
            elif role == "user":
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=msg["content"])],
                ))
            elif role == "assistant":
                parts: list[types.Part] = []
                if msg.get("content"):
                    parts.append(types.Part.from_text(text=msg["content"]))
                for tc in msg.get("tool_calls", []):
                    parts.append(types.Part.from_function_call(
                        name=tc.name,
                        args=tc.arguments,
                    ))
                if parts:
                    contents.append(types.Content(role="model", parts=parts))
            elif role == "tool":
                content_data = msg["content"]
                if isinstance(content_data, str):
                    try:
                        content_data = json.loads(content_data)
                    except json.JSONDecodeError:
                        content_data = {"result": content_data}
                # Gemini FunctionResponse requires a dict, not a list
                if isinstance(content_data, list):
                    content_data = {"result": content_data}
                elif not isinstance(content_data, dict):
                    content_data = {"result": content_data}
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part.from_function_response(
                        name=msg.get("tool_name", "tool"),
                        response=content_data,
                    )],
                ))

        return system_instruction, contents

    def _parse_response(self, response) -> LLMResponse:
        content = None
        tool_calls: list[ToolCall] = []

        for candidate in response.candidates:
            if not candidate.content or not candidate.content.parts:
                continue
            for part in candidate.content.parts:
                if part.text:
                    content = (content or "") + part.text
                if part.function_call:
                    fc = part.function_call
                    tool_calls.append(ToolCall(
                        id=str(uuid.uuid4())[:8],
                        name=fc.name,
                        arguments=dict(fc.args) if fc.args else {},
                    ))

        return LLMResponse(content=content, tool_calls=tool_calls)

    async def chat(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> LLMResponse:
        msg_count = len(messages)
        tool_count = len(tools) if tools else 0
        logger.debug("chat() messages=%d tools=%d model=%s", msg_count, tool_count, self._model)

        system_instruction, contents = self._convert_messages(messages)
        config = types.GenerateContentConfig(
            tools=self._convert_tools(tools),
            system_instruction=system_instruction,
        )
        start = time.time()
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=contents,
            config=config,
        )
        ms = (time.time() - start) * 1000

        parsed = self._parse_response(response)
        log_llm_response(logger, ms, parsed)
        return parsed
