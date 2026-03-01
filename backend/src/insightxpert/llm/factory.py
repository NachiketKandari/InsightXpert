from __future__ import annotations

import logging

from insightxpert.config import Settings
from insightxpert.llm.base import LLMProvider

logger = logging.getLogger("insightxpert.llm.factory")


def create_llm(provider: str, settings: Settings) -> LLMProvider:
    """Create an LLM provider instance by name.

    Raises ValueError if the provider is not supported.
    """
    if provider == "gemini":
        from insightxpert.llm.gemini import GeminiProvider
        return GeminiProvider(api_key=settings.gemini_api_key, model=settings.gemini_model)
    elif provider == "ollama":
        from insightxpert.llm.ollama import OllamaProvider
        return OllamaProvider(model=settings.ollama_model, base_url=settings.ollama_base_url)
    elif provider == "vertex_ai":
        from insightxpert.llm.vertex import VertexAIProvider
        return VertexAIProvider(
            project_id=settings.gcp_project_id,
            region=settings.vertex_ai_region,
            model=settings.vertex_ai_model,
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider!r}. Supported: gemini, ollama, vertex_ai")
