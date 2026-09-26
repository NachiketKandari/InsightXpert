from __future__ import annotations

import logging

from insightxpert.config import Settings
from insightxpert.llm.base import LLMProvider

logger = logging.getLogger("insightxpert.llm.factory")


def create_llm(provider: str, settings: Settings) -> LLMProvider:
    """Create an LLM provider instance by name.

    Supported providers: deepseek, openrouter, ollama.
    Raises ValueError if the provider is not supported.
    """
    if provider == "deepseek":
        from insightxpert.llm.deepseek import DeepSeekProvider
        return DeepSeekProvider(api_key=settings.deepseek_api_key, model=settings.deepseek_model)
    elif provider == "openrouter":
        from insightxpert.llm.openrouter import OpenRouterProvider
        return OpenRouterProvider(
            api_key=settings.openrouter_api_key,
            model=settings.openrouter_chat_model,
            base_url=settings.openrouter_base_url,
            site_url=settings.openrouter_site_url,
            app_name=settings.openrouter_app_name,
        )
    elif provider == "ollama":
        from insightxpert.llm.ollama import OllamaProvider
        return OllamaProvider(model=settings.ollama_model, base_url=settings.ollama_base_url)
    else:
        raise ValueError(f"Unknown LLM provider: {provider!r}. Supported: deepseek, openrouter, ollama")
