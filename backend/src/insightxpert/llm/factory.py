from __future__ import annotations

import logging
from typing import Callable

from insightxpert.config import Settings
from insightxpert.llm.base import LLMProvider

logger = logging.getLogger("insightxpert.llm.factory")

_REGISTRY: dict[str, Callable[[Settings], LLMProvider]] = {}


def _create_gemini(settings: Settings) -> LLMProvider:
    from insightxpert.llm.gemini import GeminiProvider

    return GeminiProvider(api_key=settings.gemini_api_key, model=settings.gemini_model)


def _create_ollama(settings: Settings) -> LLMProvider:
    from insightxpert.llm.ollama import OllamaProvider

    return OllamaProvider(model=settings.ollama_model, base_url=settings.ollama_base_url)


_REGISTRY["gemini"] = _create_gemini
_REGISTRY["ollama"] = _create_ollama


def create_llm(provider: str, settings: Settings) -> LLMProvider:
    """Create an LLM provider instance by name.

    Raises ValueError if the provider is not registered.
    """
    factory = _REGISTRY.get(provider)
    if factory is None:
        available = ", ".join(sorted(_REGISTRY))
        raise ValueError(
            f"Unknown LLM provider: {provider!r}. Available: {available}"
        )
    llm = factory(settings)
    logger.info("Created LLM provider: %s", provider)
    return llm
