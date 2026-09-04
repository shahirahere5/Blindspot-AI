"""OpenAI-compatible vision client used by optional multimodal processing."""

from __future__ import annotations

import base64

import httpx
from pydantic import ValidationError

from ai.json_utils import JSONExtractionError, extract_json_object
from ai.vision.base import (
    VisionAuthenticationError,
    VisionClient,
    VisionConfigurationError,
    VisionConnectionError,
    VisionRateLimitError,
    VisionResponseError,
    VisionTimeoutError,
)
from schemas.vision import VisualAnalysis


_SYSTEM_PROMPT = """You analyze visual evidence in decision documents.
Return only a JSON object with these fields:
visible_text (string), summary (string), key_evidence (array of strings),
relationships (array of strings), concerns (array of strings).
Focus on facts useful for identifying risks, assumptions, contradictions,
warnings, claims, chart trends, diagram relationships, labels, and missing
context. Do not provide artistic commentary. Do not invent page numbers."""


class OpenAICompatibleVisionClient(VisionClient):
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        provider: str,
        request_timeout_seconds: float,
        connect_timeout_seconds: float,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._provider = provider
        self.request_timeout_seconds = request_timeout_seconds
        self.connect_timeout_seconds = connect_timeout_seconds

    @property
    def provider_name(self) -> str:
        return self._provider

    @property
    def model_name(self) -> str:
        return self.model

    def _build_http_client(self, timeout: httpx.Timeout) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout)

    async def analyze_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        source_type: str,
        source_location: int,
    ) -> VisualAnalysis:
        if not self.api_key.strip() or not self.model.strip() or not self.base_url.strip():
            raise VisionConfigurationError(
                "Vision provider credentials, model, or base URL are not configured."
            )

        encoded = base64.b64encode(image_bytes).decode("ascii")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"Analyze this document {source_type}. Preserve only "
                                "visible evidence; the server records its location."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{encoded}"
                            },
                        },
                    ],
                },
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        timeout = httpx.Timeout(
            self.request_timeout_seconds, connect=self.connect_timeout_seconds
        )
        try:
            async with self._build_http_client(timeout) as http_client:
                response = await http_client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                )
        except httpx.TimeoutException as exc:
            raise VisionTimeoutError("Vision provider request timed out.") from exc
        except httpx.HTTPError as exc:
            raise VisionConnectionError("Could not reach the vision provider.") from exc

        if response.status_code in {401, 403}:
            raise VisionAuthenticationError("Vision provider rejected the credentials.")
        if response.status_code == 429:
            raise VisionRateLimitError("Vision provider rate limit was reached.")
        if response.status_code >= 500:
            raise VisionConnectionError("Vision provider is temporarily unavailable.")
        if response.status_code != 200:
            raise VisionResponseError(
                f"Vision provider returned status {response.status_code}."
            )

        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            parsed = extract_json_object(content)
            return VisualAnalysis.model_validate(parsed)
        except (ValueError, KeyError, IndexError, TypeError, JSONExtractionError, ValidationError) as exc:
            raise VisionResponseError(
                "Vision provider returned an invalid structured response."
            ) from exc
