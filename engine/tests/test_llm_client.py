"""Tests for the LLM client — error classification, caching, accounting (Phase 4).

These tests do NOT make real API calls. They test the client's error handling,
prompt cache, and accounting logic using mocked HTTP responses.
"""

import asyncio

import httpx
import pytest

from agora.llm.client import (
    LLMClient,
    LLMPermanentError,
    LLMTransientError,
    PromptCache,
    LLMResponse,
    _classify_http_error,
)

_SETTINGS = {
    "provider": "openai",
    "model": "gpt-4o",
    "base_url": "https://api.openai.com/v1",
    "temperature": 0.4,
    "max_tokens": 512,
    "timeout_seconds": 60.0,
    "max_retries": 2,
    "cache_enabled": True,
}


# -- Error classification -----------------------------------------------------

def test_classify_429_is_transient():
    err = _classify_http_error(429, "rate limited")
    assert isinstance(err, LLMTransientError)
    assert err.retryable is True
    assert err.status_code == 429


def test_classify_500_is_transient():
    err = _classify_http_error(500, "internal server error")
    assert isinstance(err, LLMTransientError)
    assert err.status_code == 500


def test_classify_503_is_transient():
    err = _classify_http_error(503, "service unavailable")
    assert isinstance(err, LLMTransientError)


def test_classify_401_is_permanent():
    err = _classify_http_error(401, "unauthorized")
    assert isinstance(err, LLMPermanentError)
    assert err.retryable is False


def test_classify_403_is_permanent():
    err = _classify_http_error(403, "forbidden")
    assert isinstance(err, LLMPermanentError)


def test_classify_400_is_permanent():
    err = _classify_http_error(400, "bad request")
    assert isinstance(err, LLMPermanentError)


# -- LLMResponse accounting properties ----------------------------------------

def test_response_token_properties_openai_style():
    resp = LLMResponse(
        content="hello",
        model="gpt-4o",
        provider="openai",
        usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    )
    assert resp.prompt_tokens == 10
    assert resp.completion_tokens == 20
    assert resp.total_tokens == 30


def test_response_token_properties_anthropic_style():
    resp = LLMResponse(
        content="hello",
        model="claude",
        provider="anthropic",
        usage={"input_tokens": 15, "output_tokens": 25},
    )
    assert resp.prompt_tokens == 15
    assert resp.completion_tokens == 25
    assert resp.total_tokens == 40


def test_response_token_fallback_to_sum():
    resp = LLMResponse(
        content="hello",
        model="test",
        provider="test",
        usage={},
    )
    assert resp.total_tokens == 0


# -- PromptCache ---------------------------------------------------------------

def test_cache_miss_returns_none(tmp_path):
    cache = PromptCache(tmp_path / "cache")
    result = cache.get(
        [{"role": "user", "content": "hi"}],
        provider="openai",
        model="gpt-4o",
        settings=_SETTINGS,
    )
    assert result is None


def test_cache_put_then_get(tmp_path):
    cache = PromptCache(tmp_path / "cache")
    messages = [{"role": "user", "content": "hello"}]
    model = "gpt-4o"
    response = LLMResponse(
        content="Hi there!",
        model=model,
        provider="openai",
        usage={"prompt_tokens": 5, "completion_tokens": 3},
    )
    cache.put(
        messages,
        provider="openai",
        model=model,
        settings=_SETTINGS,
        response=response,
    )
    hit = cache.get(
        messages,
        provider="openai",
        model=model,
        settings=_SETTINGS,
    )
    assert hit is not None
    assert hit.content == "Hi there!"
    assert hit.cached is True
    assert hit.latency_ms == 0.0


def test_cache_different_messages_miss(tmp_path):
    cache = PromptCache(tmp_path / "cache")
    messages_a = [{"role": "user", "content": "hello"}]
    messages_b = [{"role": "user", "content": "goodbye"}]
    model = "gpt-4o"
    response = LLMResponse(content="Hi", model=model, provider="openai")
    cache.put(
        messages_a,
        provider="openai",
        model=model,
        settings=_SETTINGS,
        response=response,
    )
    assert cache.get(
        messages_b,
        provider="openai",
        model=model,
        settings=_SETTINGS,
    ) is None


def test_cache_different_model_miss(tmp_path):
    cache = PromptCache(tmp_path / "cache")
    messages = [{"role": "user", "content": "hello"}]
    response = LLMResponse(content="Hi", model="gpt-4o", provider="openai")
    cache.put(
        messages,
        provider="openai",
        model="gpt-4o",
        settings=_SETTINGS,
        response=response,
    )
    assert cache.get(
        messages,
        provider="openai",
        model="gpt-3.5-turbo",
        settings={**_SETTINGS, "model": "gpt-3.5-turbo"},
    ) is None


def test_cache_different_provider_miss(tmp_path):
    cache = PromptCache(tmp_path / "cache")
    messages = [{"role": "user", "content": "hello"}]
    response = LLMResponse(content="Hi", model="gpt-4o", provider="openai")
    cache.put(
        messages,
        provider="openai",
        model="gpt-4o",
        settings=_SETTINGS,
        response=response,
    )
    assert cache.get(
        messages,
        provider="local",
        model="gpt-4o",
        settings={**_SETTINGS, "provider": "local", "base_url": "http://localhost:11434/v1"},
    ) is None


def test_cache_different_settings_miss(tmp_path):
    cache = PromptCache(tmp_path / "cache")
    messages = [{"role": "user", "content": "hello"}]
    response = LLMResponse(content="Hi", model="gpt-4o", provider="openai")
    cache.put(
        messages,
        provider="openai",
        model="gpt-4o",
        settings=_SETTINGS,
        response=response,
    )
    assert cache.get(
        messages,
        provider="openai",
        model="gpt-4o",
        settings={**_SETTINGS, "temperature": 0.8},
    ) is None


def test_malformed_openai_payload_raises_permanent_error():
    async def _run() -> None:
        client = LLMClient(provider="local", base_url="http://localhost:11434/v1")
        await client.close()

        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"id": "bad-payload"})

        client._http = httpx.AsyncClient(
            base_url="http://localhost:11434/v1",
            transport=httpx.MockTransport(handler),
        )
        try:
            with pytest.raises(LLMPermanentError, match="malformed chat completion payload"):
                await client.chat([{"role": "user", "content": "hello"}])
        finally:
            await client.close()

    asyncio.run(_run())
