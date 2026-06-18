"""OpenAI-compatible LLM provider.

Works with the official OpenAI API as well as any server that implements the
``/chat/completions`` endpoint, such as vLLM or LM Studio.
"""

from __future__ import annotations

from typing import List, Optional

import httpx

from app.llm.base import LLMProviderBase, Message


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

    async def chat(
        self,
        messages: List[Message],
        *,
        temperature: Optional[float] = None,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "stream": False,
        }
        resp = await self._client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            return ""
        return choices[0].get("message", {}).get("content", "")

    async def aclose(self) -> None:
        await self._client.aclose()
