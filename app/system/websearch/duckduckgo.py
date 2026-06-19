"""DuckDuckGo websearch provider.

Uses the ``ddgs`` package, which scrapes DuckDuckGo and needs no API key — so
web search works out of the box with zero configuration. The ``ddgs`` API is
synchronous, so the blocking call is offloaded to a worker thread (the same
pattern the shell executor uses) to stay async-safe on every event loop.
"""

from __future__ import annotations

import asyncio
from typing import List

from app.system.websearch.base import SearchResult, WebsearchProviderBase


class DuckDuckGoProvider(WebsearchProviderBase):
    name = "duckduckgo"

    def __init__(self, timeout: int = 20) -> None:
        self.timeout = timeout

    async def search(self, query: str, max_results: int = 5) -> List[SearchResult]:
        max_results = max(1, max_results)
        rows = await asyncio.to_thread(self._search_blocking, query, max_results)
        results: List[SearchResult] = []
        for row in rows:
            results.append(
                SearchResult(
                    title=str(row.get("title") or ""),
                    url=str(row.get("href") or row.get("url") or ""),
                    snippet=str(row.get("body") or row.get("snippet") or ""),
                )
            )
        return results

    def _search_blocking(self, query: str, max_results: int) -> list[dict]:
        # Imported lazily so the backend still imports if ``ddgs`` is missing;
        # the error then surfaces as an action result rather than at startup.
        from ddgs import DDGS

        with DDGS(timeout=self.timeout) as ddgs:
            return list(ddgs.text(query, max_results=max_results))
