"""Unified LLM client — talks to any supported provider via OpenAI-compatible API.

Includes retry with exponential backoff, error classification, token/latency
accounting, and optional prompt caching for reproducibility and cost control.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from .models import ProviderConfig, resolve_provider

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

class LLMError(Exception):
    """Base class for LLM client errors."""

    def __init__(self, message: str, *, retryable: bool = False, status_code: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


class LLMTransientError(LLMError):
    """Transient error — safe to retry (rate limit, server error, timeout)."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message, retryable=True, status_code=status_code)


class LLMPermanentError(LLMError):
    """Permanent error — should not retry (bad request, auth failure)."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message, retryable=False, status_code=status_code)


class LLMConfigurationError(LLMPermanentError):
    """Permanent configuration error detected before or during a request."""


def _classify_http_error(status_code: int, body: str) -> LLMError:
    """Classify an HTTP error into transient or permanent."""
    if status_code == 429:
        return LLMTransientError(f"Rate limited (429): {body[:200]}", status_code=429)
    if status_code >= 500:
        return LLMTransientError(f"Server error ({status_code}): {body[:200]}", status_code=status_code)
    if status_code == 401:
        return LLMPermanentError(f"Authentication failed (401): {body[:200]}", status_code=401)
    if status_code == 403:
        return LLMPermanentError(f"Forbidden (403): {body[:200]}", status_code=403)
    return LLMPermanentError(f"HTTP {status_code}: {body[:200]}", status_code=status_code)


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------

@dataclass
class LLMResponse:
    """Normalised response from any LLM provider."""

    content: str
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    latency_ms: float = 0.0
    cached: bool = False

    @property
    def prompt_tokens(self) -> int:
        return self.usage.get("input_tokens", self.usage.get("prompt_tokens", 0))

    @property
    def completion_tokens(self) -> int:
        return self.usage.get("output_tokens", self.usage.get("completion_tokens", 0))

    @property
    def total_tokens(self) -> int:
        total = self.usage.get("total_tokens", 0)
        return total if total else self.prompt_tokens + self.completion_tokens


# ---------------------------------------------------------------------------
# Prompt cache
# ---------------------------------------------------------------------------

class PromptCache:
    """File-based cache keyed by a SHA-256 hash of the full prompt context.

    Used for reproducibility (same prompt → same cached output) and cost
    control (skip redundant LLM calls within or across runs).
    """

    def __init__(self, cache_dir: Path) -> None:
        self._dir = cache_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _key(
        messages: list[dict[str, str]],
        *,
        provider: str,
        model: str,
        settings: dict[str, Any],
    ) -> str:
        material = json.dumps(
            {
                "provider": provider,
                "model": model,
                "messages": messages,
                "settings": settings,
            },
            sort_keys=True,
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def get(
        self,
        messages: list[dict[str, str]],
        *,
        provider: str,
        model: str,
        settings: dict[str, Any],
    ) -> LLMResponse | None:
        path = self._dir / f"{self._key(messages, provider=provider, model=model, settings=settings)}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return LLMResponse(
                content=data["content"],
                model=data["model"],
                provider=data["provider"],
                usage=data.get("usage", {}),
                latency_ms=0.0,
                cached=True,
            )
        except (json.JSONDecodeError, KeyError):
            return None

    def put(
        self,
        messages: list[dict[str, str]],
        *,
        provider: str,
        model: str,
        settings: dict[str, Any],
        response: LLMResponse,
    ) -> None:
        path = self._dir / f"{self._key(messages, provider=provider, model=model, settings=settings)}.json"
        data = {
            "content": response.content,
            "model": response.model,
            "provider": response.provider,
            "usage": response.usage,
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class LLMClient:
    """Lightweight async client that routes to any registered provider.

    Features:
      - Retry with exponential backoff for transient errors
      - Error classification (transient vs permanent)
      - Token and latency accounting on every response
      - Optional file-based prompt cache

    Usage::

        async with LLMClient(provider="openai") as client:
            resp = await client.chat([{"role": "user", "content": "Hello"}])
            print(resp.content, resp.total_tokens, resp.latency_ms)
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
        max_retries: int = 3,
        cache_dir: Path | None = None,
    ) -> None:
        cfg: ProviderConfig = resolve_provider(provider)
        self.provider_name = cfg.name
        self.model = model or cfg.default_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.timeout_seconds = timeout

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

        # Optional prompt cache
        self._cache = PromptCache(cache_dir) if cache_dir else None

        # Cumulative accounting
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.total_requests: int = 0
        self.total_cached: int = 0
        self.total_latency_ms: float = 0.0

    # -- public API ----------------------------------------------------------

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
        ) -> LLMResponse:
        """Send a chat completion request and return a normalised response.

        Retries transient errors with exponential backoff.
        """
        request_settings = self.get_request_settings(
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        # Check cache first
        if self._cache is not None:
            cached = self._cache.get(
                messages,
                provider=self.provider_name,
                model=self.model,
                settings=request_settings,
            )
            if cached is not None:
                self.total_cached += 1
                self.total_requests += 1
                logger.debug("Cache hit for model=%s", self.model)
                return cached

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = await self._do_request(
                    messages, temperature=temperature, max_tokens=max_tokens, **kwargs
                )
                # Update accounting
                self.total_requests += 1
                self.total_prompt_tokens += resp.prompt_tokens
                self.total_completion_tokens += resp.completion_tokens
                self.total_latency_ms += resp.latency_ms

                # Write to cache
                if self._cache is not None:
                    self._cache.put(
                        messages,
                        provider=self.provider_name,
                        model=self.model,
                        settings=request_settings,
                        response=resp,
                    )

                return resp

            except LLMTransientError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    delay = min(2 ** attempt, 30)  # 1s, 2s, 4s … cap 30s
                    logger.warning(
                        "Transient LLM error (attempt %d/%d), retrying in %ds: %s",
                        attempt + 1, self.max_retries + 1, delay, exc,
                    )
                    import asyncio
                    await asyncio.sleep(delay)
                else:
                    logger.error("LLM request failed after %d attempts: %s", self.max_retries + 1, exc)

            except LLMPermanentError:
                raise

            except httpx.TimeoutException as exc:
                last_error = LLMTransientError(f"Request timed out: {exc}")
                if attempt < self.max_retries:
                    delay = min(2 ** attempt, 30)
                    logger.warning(
                        "Timeout (attempt %d/%d), retrying in %ds",
                        attempt + 1, self.max_retries + 1, delay,
                    )
                    import asyncio
                    await asyncio.sleep(delay)
                else:
                    logger.error("LLM request timed out after %d attempts", self.max_retries + 1)

        raise last_error or LLMTransientError("LLM request failed after retries")

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "LLMClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    def get_accounting(self) -> dict[str, Any]:
        """Return cumulative token/latency/cost accounting for this client."""
        return {
            "total_requests": self.total_requests,
            "total_cached": self.total_cached,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
            "total_latency_ms": round(self.total_latency_ms, 1),
            "provider": self.provider_name,
            "model": self.model,
        }

    def get_request_settings(
        self,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Return the normalized request settings used for one chat call."""
        settings: dict[str, Any] = {
            "provider": self.provider_name,
            "model": self.model,
            "base_url": self._base_url,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "cache_enabled": self._cache is not None,
        }
        if kwargs:
            settings["extra"] = kwargs
        return settings

    # -- internal request dispatch -------------------------------------------

    async def _do_request(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Execute a single request (no retry) and return the response."""
        t0 = time.monotonic()

        if self.provider_name == "anthropic":
            resp = await self._chat_anthropic(
                messages, temperature=temperature, max_tokens=max_tokens, **kwargs
            )
        else:
            resp = await self._chat_openai(
                messages, temperature=temperature, max_tokens=max_tokens, **kwargs
            )

        resp.latency_ms = round((time.monotonic() - t0) * 1000, 1)
        return resp

    async def _chat_openai(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """OpenAI-compatible chat completion."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            **kwargs,
        }

        try:
            resp = await self._http.post("/chat/completions", json=payload)
        except httpx.TimeoutException:
            raise
        except httpx.HTTPError as exc:
            raise LLMTransientError(f"HTTP transport error: {exc}") from exc

        if resp.status_code != 200:
            raise _classify_http_error(resp.status_code, resp.text)

        try:
            data = resp.json()
        except ValueError as exc:
            raise LLMPermanentError(f"Provider returned invalid JSON: {exc}") from exc

        try:
            choice = data["choices"][0]["message"]
            content = _extract_openai_content(choice)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMPermanentError(
                f"Provider returned malformed chat completion payload: {exc}"
            ) from exc

        return LLMResponse(
            content=content,
            model=data.get("model", self.model),
            provider=self.provider_name,
            usage=data.get("usage", {}),
            raw=data,
        )

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

        try:
            resp = await self._http.post("/messages", json=payload)
        except httpx.TimeoutException:
            raise
        except httpx.HTTPError as exc:
            raise LLMTransientError(f"HTTP transport error: {exc}") from exc

        if resp.status_code != 200:
            raise _classify_http_error(resp.status_code, resp.text)

        try:
            data = resp.json()
        except ValueError as exc:
            raise LLMPermanentError(f"Provider returned invalid JSON: {exc}") from exc

        try:
            content_blocks = data.get("content", [])
            text = _extract_anthropic_text(content_blocks)
        except (KeyError, TypeError, ValueError) as exc:
            raise LLMPermanentError(
                f"Provider returned malformed messages payload: {exc}"
            ) from exc

        # Anthropic uses input_tokens / output_tokens
        usage = data.get("usage", {})

        return LLMResponse(
            content=text,
            model=data.get("model", self.model),
            provider=self.provider_name,
            usage=usage,
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


def _extract_openai_content(message: dict[str, Any]) -> str:
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                raise ValueError("non-dict content block")
            if block.get("type") == "text" and isinstance(block.get("text"), str):
                parts.append(block["text"])
        if parts:
            return "".join(parts)
    raise ValueError("missing text content")


def _extract_anthropic_text(content_blocks: Any) -> str:
    if not isinstance(content_blocks, list):
        raise ValueError("content is not a list")
    parts: list[str] = []
    for block in content_blocks:
        if not isinstance(block, dict):
            raise ValueError("non-dict content block")
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
    if not parts:
        raise ValueError("missing text content")
    return "".join(parts)
