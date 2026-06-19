"""OpenAI-compatible LLM provider.

Works with the official OpenAI API as well as any server that implements the
``/chat/completions`` endpoint, such as vLLM or LM Studio.
"""

from __future__ import annotations

import json
from typing import AsyncIterator, List, Optional

import httpx

from app.llm.base import LLMProviderBase, Message, StreamChunk


class OpenAICompatibleProvider(LLMProviderBase):
    name = "openai"

    def __init__(
        self,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        api_key: Optional[str] = None,
        temperature: float = 0.2,
        timeout: int = 120,
    ) -> None:
        super().__init__(model=model, temperature=temperature, timeout=timeout)
        self.base_url = base_url.rstrip("/")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            base_url=self.base_url, timeout=timeout, headers=headers
        )

    def _payload(self, messages: List[Message], temperature: Optional[float], stream: bool) -> dict:
        return {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "stream": stream,
        }

    async def chat(
        self,
        messages: List[Message],
        *,
        temperature: Optional[float] = None,
    ) -> str:
        resp = await self._client.post(
            "/chat/completions", json=self._payload(messages, temperature, stream=False)
        )
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            return ""
        return choices[0].get("message", {}).get("content", "")

    async def stream(
        self,
        messages: List[Message],
        *,
        temperature: Optional[float] = None,
    ) -> AsyncIterator[StreamChunk]:
        payload = self._payload(messages, temperature, stream=True)
        async with self._client.stream(
            "POST", "/chat/completions", json=payload
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line or not line.startswith("data:"):
                    continue
                data_str = line[len("data:") :].strip()
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                choices = data.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                # Reasoning models expose their thinking on a separate field
                # (naming varies across servers).
                reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                if reasoning:
                    yield StreamChunk(kind="thinking", text=reasoning)
                content = delta.get("content")
                if content:
                    yield StreamChunk(kind="content", text=content)

    async def aclose(self) -> None:
        await self._client.aclose()
