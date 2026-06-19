"""Ollama LLM provider (local server)."""

from __future__ import annotations

import json
from typing import AsyncIterator, List, Optional

import httpx

from app.llm.base import LLMProviderBase, Message, StreamChunk


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

    def _payload(self, messages: List[Message], temperature: Optional[float], stream: bool) -> dict:
        return {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            # Ask reasoning-capable models (deepseek-r1, qwen3, ...) to expose
            # their thinking on a separate channel; ignored by other models.
            "think": True,
            "options": {
                "temperature": self.temperature if temperature is None else temperature,
            },
        }

    async def chat(
        self,
        messages: List[Message],
        *,
        temperature: Optional[float] = None,
    ) -> str:
        resp = await self._client.post(
            "/api/chat", json=self._payload(messages, temperature, stream=False)
        )
        resp.raise_for_status()
        data = resp.json()
        return (data.get("message") or {}).get("content", "")

    async def stream(
        self,
        messages: List[Message],
        *,
        temperature: Optional[float] = None,
    ) -> AsyncIterator[StreamChunk]:
        payload = self._payload(messages, temperature, stream=True)
        async with self._client.stream("POST", "/api/chat", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                message = data.get("message") or {}
                thinking = message.get("thinking")
                if thinking:
                    yield StreamChunk(kind="thinking", text=thinking)
                content = message.get("content")
                if content:
                    yield StreamChunk(kind="content", text=content)

    async def aclose(self) -> None:
        await self._client.aclose()
