"""Abstract base class for LLM providers."""

from __future__ import annotations

import abc
from typing import List, Optional, TypedDict


class Message(TypedDict):
    """A single chat message in the provider-neutral format."""

    role: str  # "system" | "user" | "assistant"
    content: str


class LLMProviderBase(abc.ABC):
    """Common interface every LLM backend must implement.

    Providers are intentionally thin: they take a list of chat messages and
    return the assistant's text reply. Higher-level concerns (system prompt
    construction, action planning, execution) live in the agent layer.
    """

    name: str = "base"

    def __init__(self, model: str, temperature: float = 0.2, timeout: int = 120) -> None:
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

    @abc.abstractmethod
    async def chat(
        self,
        messages: List[Message],
        *,
        temperature: Optional[float] = None,
    ) -> str:
        """Send chat messages to the model and return the text reply."""

    async def aclose(self) -> None:  # pragma: no cover - optional cleanup hook
        """Release any underlying resources (e.g. HTTP clients)."""
