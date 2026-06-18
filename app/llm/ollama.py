"""Ollama LLM provider (local server)."""

from __future__ import annotations

from typing import List, Optional

import httpx

from app.llm.base import LLMProviderBase, Message


class OllamaProvider(LLMProviderBase):
    """Talks to a local Ollama server via its ``/api/chat`` endpoint."""

    name = "ollama"

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
        temperature: float = 0.2,
        timeout: int = 120,
    ) -> None:
        super().__init__(model=model, temperature=temperature, timeout=timeout)
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    async def chat(
        self,
        messages: List[Message],
        *,
        temperature: Optional[float] = None,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.temperature if temperature is None else temperature,
            },
        }
        resp = await self._client.post("/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return (data.get("message") or {}).get("content", "")

    async def aclose(self) -> None:
        await self._client.aclose()
