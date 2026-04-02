"""Unified LLM client — talks to any supported provider via OpenAI-compatible API."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from .models import ProviderConfig, resolve_provider


@dataclass
class LLMResponse:
    """Normalised response from any LLM provider."""

    content: str
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


class LLMClient:
    """Lightweight async client that routes to any registered provider.

    Usage::

        client = LLMClient(provider="deepseek")
        resp = await client.chat([{"role": "user", "content": "Hello"}])
        print(resp.content)

    For local models::

        client = LLMClient(provider="local", base_url="http://localhost:8000/v1")
    """

    def __init__(
        self,
        provider: str = "openai",
        *,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        timeout: float = 120.0,
    ) -> None:
        cfg: ProviderConfig = resolve_provider(provider)
        self.provider_name = cfg.name
        self.model = model or cfg.default_model
        self.temperature = temperature
        self.max_tokens = max_tokens

        # Resolve base URL (allow env override for local)
        if base_url:
            self._base_url = base_url.rstrip("/")
        elif cfg.name == "local":
            self._base_url = os.getenv("LOCAL_LLM_BASE_URL", cfg.base_url).rstrip("/")
        else:
            self._base_url = cfg.base_url

        # Resolve API key
        if api_key:
            self._api_key = api_key
        elif cfg.env_key:
            self._api_key = os.getenv(cfg.env_key, "")
        else:
            self._api_key = ""

        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            headers=self._build_headers(),
        )

    # -- public API ----------------------------------------------------------

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send a chat completion request and return a normalised response."""
        if self.provider_name == "anthropic":
            return await self._chat_anthropic(messages, temperature=temperature,
                                              max_tokens=max_tokens, **kwargs)

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            **kwargs,
        }
        resp = await self._http.post("/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()

        choice = data["choices"][0]["message"]
        return LLMResponse(
            content=choice.get("content", ""),
            model=data.get("model", self.model),
            provider=self.provider_name,
            usage=data.get("usage", {}),
            raw=data,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "LLMClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    # -- Anthropic (Messages API, not OpenAI-compatible) ---------------------

    async def _chat_anthropic(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Anthropic uses its own Messages API format."""
        # Separate system message from conversation turns
        system_text = ""
        turns = []
        for msg in messages:
            if msg["role"] == "system":
                system_text = msg["content"]
            else:
                turns.append(msg)

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": turns,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
            **kwargs,
        }
        if system_text:
            payload["system"] = system_text

        resp = await self._http.post("/messages", json=payload)
        resp.raise_for_status()
        data = resp.json()

        content_blocks = data.get("content", [])
        text = "".join(b["text"] for b in content_blocks if b["type"] == "text")
        return LLMResponse(
            content=text,
            model=data.get("model", self.model),
            provider=self.provider_name,
            usage=data.get("usage", {}),
            raw=data,
        )

    # -- internal ------------------------------------------------------------

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.provider_name == "anthropic":
            headers["x-api-key"] = self._api_key
            headers["anthropic-version"] = "2023-06-01"
        elif self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers
