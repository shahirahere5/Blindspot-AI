"""Unit tests for ai.client.GroqClient using httpx's MockTransport.

These tests never touch the real Groq API and never require GROQ_API_KEY
to be set. `_build_http_client` is overridden per-instance to inject a mock
transport instead of patching any global httpx state.
"""

from __future__ import annotations

import httpx
import pytest

from ai.base import (
    AIAuthenticationError,
    AIConfigurationError,
    AIConnectionError,
    AIModelUnavailableError,
    AIRateLimitError,
    AIResponseError,
    AITimeoutError,
)
from ai.client import GroqClient


def _client_with_handler(handler, api_key: str | None = "fake-api-key") -> GroqClient:
    transport = httpx.MockTransport(handler)
    groq_client = GroqClient(
        api_key=api_key,
        base_url="https://fake-groq.example.com/openai/v1",
        model="fake-model",
    )
    groq_client._build_http_client = lambda timeout: httpx.AsyncClient(  # type: ignore[method-assign]
        timeout=timeout, transport=transport
    )
    return groq_client


# ---------------------------------------------------------------------------
# 1. Successful Groq response / 9. Valid structured analysis (transport-level)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_generate_returns_message_content():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer fake-api-key"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": '{"ok": true}'}}
                ]
            },
        )

    client = _client_with_handler(handler)
    result = await client.generate("system", "user")
    assert result == '{"ok": true}'


def test_model_name_property():
    client = GroqClient(api_key="x", model="openai/gpt-oss-120b")
    assert client.model_name == "openai/gpt-oss-120b"


# ---------------------------------------------------------------------------
# 2. Missing API key
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_generate_raises_configuration_error_when_api_key_missing():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Should never make an HTTP call without an API key.")

    client = _client_with_handler(handler, api_key="")
    with pytest.raises(AIConfigurationError):
        await client.generate("system", "user")


@pytest.mark.asyncio
async def test_generate_raises_configuration_error_when_api_key_is_none():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Should never make an HTTP call without an API key.")

    client = _client_with_handler(handler, api_key=None)
    with pytest.raises(AIConfigurationError):
        await client.generate("system", "user")


# ---------------------------------------------------------------------------
# 3. Invalid API key / provider error
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_generate_raises_authentication_error_on_401():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, json={"error": {"message": "Invalid API Key", "type": "invalid_request_error"}}
        )

    client = _client_with_handler(handler)
    with pytest.raises(AIAuthenticationError):
        await client.generate("system", "user")


# ---------------------------------------------------------------------------
# 4. Network / connection failure
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_generate_raises_connection_error_on_connect_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = _client_with_handler(handler)
    with pytest.raises(AIConnectionError):
        await client.generate("system", "user")


@pytest.mark.asyncio
async def test_generate_raises_connection_error_on_dns_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Name or service not known", request=request)

    client = _client_with_handler(handler)
    with pytest.raises(AIConnectionError):
        await client.generate("system", "user")


@pytest.mark.asyncio
async def test_generate_raises_connection_error_on_server_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="service unavailable")

    client = _client_with_handler(handler)
    with pytest.raises(AIConnectionError):
        await client.generate("system", "user")


# ---------------------------------------------------------------------------
# 5. Timeout
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_generate_raises_timeout_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = _client_with_handler(handler)
    with pytest.raises(AITimeoutError):
        await client.generate("system", "user")


# ---------------------------------------------------------------------------
# 6. Rate limit
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_generate_raises_rate_limit_error_on_429():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429, json={"error": {"message": "Rate limit reached"}}
        )

    client = _client_with_handler(handler)
    with pytest.raises(AIRateLimitError):
        await client.generate("system", "user")


# ---------------------------------------------------------------------------
# 7. Invalid model
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_generate_raises_model_unavailable_on_404():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404, json={"error": {"message": "model not found"}}
        )

    client = _client_with_handler(handler)
    with pytest.raises(AIModelUnavailableError):
        await client.generate("system", "user")


@pytest.mark.asyncio
async def test_generate_raises_model_unavailable_on_400_mentioning_model():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {
                    "message": "The model `bad-model` does not exist",
                    "type": "invalid_request_error",
                }
            },
        )

    client = _client_with_handler(handler)
    with pytest.raises(AIModelUnavailableError):
        await client.generate("system", "user")


# ---------------------------------------------------------------------------
# 8. Invalid JSON (malformed HTTP body -- extraction of the *analysis* JSON
# from a well-formed chat completion is covered in tests/test_json_utils.py
# and tests/test_analysis_api.py)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_generate_raises_response_error_on_non_json_http_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json at all")

    client = _client_with_handler(handler)
    with pytest.raises(AIResponseError):
        await client.generate("system", "user")


@pytest.mark.asyncio
async def test_generate_raises_response_error_on_missing_choices():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    client = _client_with_handler(handler)
    with pytest.raises(AIResponseError):
        await client.generate("system", "user")


@pytest.mark.asyncio
async def test_generate_raises_response_error_on_unexpected_400():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, json={"error": {"message": "temperature must be between 0 and 2"}}
        )

    client = _client_with_handler(handler)
    with pytest.raises(AIResponseError):
        await client.generate("system", "user")
