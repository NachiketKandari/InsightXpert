"""Vertex AI LLM provider -- calls the OpenAI-compatible chat completions endpoint.

Supports non-Google models served via Vertex AI Model Garden (e.g. GLM-5,
Claude, Mistral) through the unified ``/chat/completions`` endpoint.

Authentication uses Google Application Default Credentials (ADC) which
automatically picks up:
  - ``GOOGLE_APPLICATION_CREDENTIALS`` env var (service account JSON)
  - ``gcloud auth application-default login`` (local dev)
  - Metadata server (Cloud Run, GCE, GKE)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

import google.auth
import google.auth.transport.requests
import httpx

from .base import LLMResponse, ToolCall, log_llm_response

logger = logging.getLogger("insightxpert.llm.vertex")

# Vertex AI endpoint template
_ENDPOINT_TPL = (
    "https://aiplatform.googleapis.com/v1/projects/{project_id}"
    "/locations/{region}/endpoints/openapi/chat/completions"
)


class VertexAIProvider:
    """LLM provider for Vertex AI Model Garden (OpenAI-compatible endpoint).

    Implements the ``LLMProvider`` protocol defined in ``llm/base.py``.
    """

    def __init__(
        self,
        project_id: str,
        region: str = "global",
        model: str = "zai-org/glm-5-maas",
    ) -> None:
        if not project_id:
            raise ValueError("gcp_project_id is required for the vertex_ai provider")

        self._model = model
        self._project_id = project_id
        self._region = region
        self._endpoint = _ENDPOINT_TPL.format(project_id=project_id, region=region)

        # Google ADC — picks up gcloud auth application-default login,
        # service account JSON, or metadata server (Cloud Run/GCE/GKE)
        self._credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        self._http_client = httpx.AsyncClient(timeout=120.0)

        logger.debug(
            "VertexAIProvider initialized (model=%s, project=%s, region=%s)",
            model, project_id, region,
        )

    @property
    def model(self) -> str:
        return self._model

    def _get_auth_headers(self) -> dict[str, str]:
        """Get authorization headers via ADC access token."""
        self._credentials.refresh(google.auth.transport.requests.Request())
        return {
            "Authorization": f"Bearer {self._credentials.token}",
            "Content-Type": "application/json",
        }

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
                converted.append({
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
                })
            else:
                converted.append({"role": role, "content": msg["content"]})
        return converted

    def _parse_response(self, data: dict) -> LLMResponse:
        """Parse an OpenAI-format chat completion response."""
        content = None
        tool_calls: list[ToolCall] = []

        choices = data.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            content = message.get("content")

            for tc in (message.get("tool_calls") or []):
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
        )

    async def chat(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> LLMResponse:
        """Send a chat request to the Vertex AI OpenAI-compatible endpoint."""
        msg_count = len(messages)
        tool_count = len(tools) if tools else 0
        logger.debug("chat() messages=%d tools=%d model=%s", msg_count, tool_count, self._model)

        body: dict = {
            "model": self._model,
            "messages": self._convert_messages(messages),
            "stream": False,
        }
        if tools:
            body["tools"] = self._convert_tools(tools)

        max_retries = 4
        base_delay = 2.0  # seconds

        start = time.time()
        for attempt in range(max_retries + 1):
            headers = self._get_auth_headers()
            resp = await self._http_client.post(self._endpoint, json=body, headers=headers)

            if resp.status_code == 429 and attempt < max_retries:
                delay = base_delay * (2 ** attempt)  # 2s, 4s, 8s, 16s
                logger.warning(
                    "Vertex AI 429 rate-limited (attempt %d/%d), retrying in %.0fs",
                    attempt + 1, max_retries + 1, delay,
                )
                await asyncio.sleep(delay)
                continue

            break

        ms = (time.time() - start) * 1000

        if resp.status_code != 200:
            error_text = resp.text[:500]
            logger.error("Vertex AI API error %d: %s", resp.status_code, error_text)
            raise RuntimeError(f"Vertex AI API returned {resp.status_code}: {error_text}")

        parsed = self._parse_response(resp.json())
        log_llm_response(logger, ms, parsed)
        return parsed
