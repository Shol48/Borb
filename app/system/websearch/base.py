"""Abstract base class and result model for websearch providers."""

from __future__ import annotations

import abc
from typing import List

from pydantic import BaseModel


class SearchResult(BaseModel):
    """A single web search hit in a provider-neutral format."""

    title: str = ""
    url: str = ""
    snippet: str = ""


class WebsearchProviderBase(abc.ABC):
    """Common interface every websearch backend must implement.

    Providers are intentionally thin: they take a query string and return a list
    of :class:`SearchResult`. Higher-level concerns (policy gating, audit
    logging, formatting results back to the model) live in the system/agent
    layers.
    """

    name: str = "base"

    @abc.abstractmethod
    async def search(self, query: str, max_results: int = 5) -> List[SearchResult]:
        """Run ``query`` and return up to ``max_results`` results."""
