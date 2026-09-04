"""Provider transport tests for optional OpenAI-compatible visual analysis."""

from __future__ import annotations

import httpx
import pytest

from ai.vision.base import VisionRateLimitError, VisionResponseError, VisionTimeoutError
from ai.vision.client import OpenAICompatibleVisionClient


def _client(handler) -> OpenAICompatibleVisionClient:
    client = OpenAICompatibleVisionClient(
        api_key="test-key",
        base_url="https://vision.example/v1",
        model="vision-test",
        provider="openai_compatible",
        request_timeout_seconds=10,
        connect_timeout_seconds=2,
    )
    transport = httpx.MockTransport(handler)
    client._build_http_client = lambda timeout: httpx.AsyncClient(  # type: ignore[method-assign]
        transport=transport, timeout=timeout
    )
    return client


@pytest.mark.asyncio
async def test_vision_client_sends_image_and_validates_structured_response():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        image_url = payload["messages"][1]["content"][1]["image_url"]["url"]
        assert image_url.startswith("data:image/png;base64,")
        assert payload["model"] == "vision-test"
        return httpx.Response(
            200,
            json={
                "choices": [{
                    "message": {
                        "content": '{"visible_text":"Revenue +20%","summary":"An upward chart.","key_evidence":["Growth rises"],"relationships":[],"concerns":[]}'
                    }
                }]
            },
        )

    result = await _client(handler).analyze_image(b"png", "image/png", "page", 2)

    assert result.visible_text == "Revenue +20%"
    assert result.key_evidence == ["Growth rises"]


@pytest.mark.asyncio
async def test_vision_client_maps_rate_limit_without_exposing_response_body():
    client = _client(
        lambda _request: httpx.Response(
            429, json={"error": {"message": "private provider detail"}}
        )
    )

    with pytest.raises(VisionRateLimitError, match="rate limit") as exc_info:
        await client.analyze_image(b"png", "image/png", "image", 1)

    assert "private provider detail" not in exc_info.value.message


@pytest.mark.asyncio
async def test_vision_client_rejects_malformed_structured_result():
    client = _client(
        lambda _request: httpx.Response(
            200, json={"choices": [{"message": {"content": "not json"}}]}
        )
    )

    with pytest.raises(VisionResponseError, match="invalid structured"):
        await client.analyze_image(b"png", "image/png", "image", 1)


@pytest.mark.asyncio
async def test_vision_client_maps_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(VisionTimeoutError, match="timed out"):
        await _client(handler).analyze_image(b"png", "image/png", "image", 1)
