"""Websearch router: selects and builds the configured provider."""

from __future__ import annotations

from functools import lru_cache

from app.config import Settings, WebsearchProvider, get_settings
from app.system.websearch.base import WebsearchProviderBase
from app.system.websearch.duckduckgo import DuckDuckGoProvider


def build_websearch_provider(settings: Settings) -> WebsearchProviderBase:
    if settings.websearch_provider == WebsearchProvider.DUCKDUCKGO:
        return DuckDuckGoProvider(timeout=settings.websearch_timeout)
    raise ValueError(f"Unknown websearch provider: {settings.websearch_provider}")


@lru_cache(maxsize=1)
def get_websearch_provider() -> WebsearchProviderBase:
    return build_websearch_provider(get_settings())
