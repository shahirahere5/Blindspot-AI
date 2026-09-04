"""Configuration-driven construction of the optional vision client."""

from __future__ import annotations

import config
from ai.vision.base import VisionClient, VisionConfigurationError
from ai.vision.client import OpenAICompatibleVisionClient


def get_vision_client() -> VisionClient:
    provider = config.VISION_PROVIDER.strip().lower()
    if provider == "groq":
        api_key = config.VISION_API_KEY or config.GROQ_API_KEY
        base_url = config.VISION_BASE_URL or config.GROQ_BASE_URL
    elif provider == "openai_compatible":
        api_key = config.VISION_API_KEY
        base_url = config.VISION_BASE_URL
    else:
        raise VisionConfigurationError("Unsupported vision provider configuration.")

    if not api_key.strip() or not base_url.strip() or not config.VISION_MODEL.strip():
        raise VisionConfigurationError("Visual analysis is not fully configured.")

    return OpenAICompatibleVisionClient(
        api_key=api_key,
        base_url=base_url,
        model=config.VISION_MODEL,
        provider=provider,
        request_timeout_seconds=max(1.0, config.VISION_TIMEOUT_SECONDS),
        connect_timeout_seconds=max(1.0, config.VISION_CONNECT_TIMEOUT_SECONDS),
    )
