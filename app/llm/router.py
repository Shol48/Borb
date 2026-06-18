"""LLM router: selects and builds the configured provider."""

from __future__ import annotations

from functools import lru_cache

from app.config import LLMProvider, Settings, get_settings
from app.llm.base import LLMProviderBase
from app.llm.ollama import OllamaProvider
from app.llm.openai_compatible import OpenAICompatibleProvider


def build_provider(settings: Settings) -> LLMProviderBase:
    if settings.llm_provider == LLMProvider.OLLAMA:
        return OllamaProvider(
            model=settings.llm_model,
            base_url=settings.ollama_base_url,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout,
        )
    if settings.llm_provider == LLMProvider.OPENAI:
        return OpenAICompatibleProvider(
            model=settings.llm_model,
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout,
        )
    raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")


@lru_cache(maxsize=1)
def get_llm_provider() -> LLMProviderBase:
    return build_provider(get_settings())
