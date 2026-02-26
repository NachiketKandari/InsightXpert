"""Google Gemini LLM provider -- converts OpenAI-style messages to Gemini SDK format.

The rest of the codebase (analyst loop, orchestrator) works with an
OpenAI-style message format (``role`` in ``{"system", "user", "assistant",
"tool"}``, with ``tool_calls`` on assistant messages and ``tool_call_id`` on
tool messages).  This module translates that format into the Google GenAI
SDK's ``types.Content`` / ``types.Part`` structure before calling the Gemini
API, and translates the response back into the shared ``LLMResponse`` /
``ToolCall`` dataclasses.
"""

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
    """LLM provider that wraps the Google GenAI (Gemini) SDK.

    Implements the ``LLMProvider`` protocol defined in ``llm/base.py``,
    translating between the application's OpenAI-style message format and
    Gemini's native Content/Part format.
    """

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash") -> None:
        self._model = model
        self._client = genai.Client(api_key=api_key)
        logger.debug("GeminiProvider initialized (model=%s)", model)

    @property
    def model(self) -> str:
        return self._model

    def _convert_tools(self, tools: list[dict] | None) -> list[types.Tool] | None:
        """Convert OpenAI-style tool schemas to Gemini FunctionDeclarations.

        The application defines tools as plain dicts with ``name``,
        ``description``, and ``parameters`` keys (OpenAI function-calling
        format).  This method wraps them into Gemini's
        ``types.FunctionDeclaration`` objects bundled in a single
        ``types.Tool``.

        Args:
            tools: List of tool schema dicts, or ``None`` if no tools.

        Returns:
            A single-element list containing a ``types.Tool`` with all
            function declarations, or ``None`` if no tools were provided.
        """
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
        """Convert OpenAI-style messages to Gemini Content objects.

        Role mapping:
            - ``"system"``    -> extracted as ``system_instruction`` (Gemini
              handles system prompts separately, not as a Content entry).
            - ``"user"``      -> ``Content(role="user", ...)``
            - ``"assistant"`` -> ``Content(role="model", ...)``.  Text and
              tool calls are combined as parts in a single Content.
            - ``"tool"``      -> ``Content(role="user", ...)`` with a
              ``FunctionResponse`` part.  Gemini treats tool results as user
              turns.

        Args:
            messages: The OpenAI-style message list.

        Returns:
            A tuple of (system_instruction, contents) where
            ``system_instruction`` is the extracted system prompt string
            (or ``None``), and ``contents`` is the list of Gemini Content
            objects.
        """
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
                # Normalize tool result content into a dict for FunctionResponse.
                # Gemini's FunctionResponse.response requires a dict, but tool
                # results may arrive as a JSON string, a list, or a raw scalar.
                # We parse JSON strings, then wrap non-dict values in
                # {"result": ...} to satisfy the SDK's type constraint.
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
        """Convert a Gemini SDK response into the shared LLMResponse format.

        Iterates over all candidates and their content parts, extracting
        text and function calls.  Gemini does not provide tool-call IDs, so
        a truncated UUID (8 hex chars) is generated for each function call
        to satisfy the ``ToolCall.id`` field required by the agentic loop.

        Args:
            response: The raw response from ``generate_content``.

        Returns:
            An ``LLMResponse`` with aggregated text content and any tool
            calls.
        """
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
                    # Generate a synthetic ID since Gemini doesn't provide one
                    tool_calls.append(ToolCall(
                        id=str(uuid.uuid4())[:8],
                        name=fc.name,
                        arguments=dict(fc.args) if fc.args else {},
                    ))

        return LLMResponse(content=content, tool_calls=tool_calls)

    async def chat(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> LLMResponse:
        """Send a chat request to the Gemini API and return a parsed response.

        Converts the OpenAI-style messages and tool schemas into Gemini's
        native format, calls the async ``generate_content`` endpoint, and
        parses the response back into the shared ``LLMResponse`` format.

        Args:
            messages: OpenAI-style message list (system/user/assistant/tool).
            tools: Optional list of tool schemas in OpenAI function-calling
                format.

        Returns:
            An ``LLMResponse`` containing the model's text and/or tool calls.
        """
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
