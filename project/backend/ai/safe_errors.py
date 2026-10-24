"""Stable client-facing messages for server-side AI failures."""

from __future__ import annotations

from ai.base import (
    AIAuthenticationError,
    AIClientError,
    AIConfigurationError,
    AIConnectionError,
    AIModelUnavailableError,
    AIRateLimitError,
    AIResponseError,
    AITimeoutError,
)


def safe_ai_error_detail(error: AIClientError, operation: str) -> str:
    """Describe an AI failure without exposing credentials or provider internals."""
    if isinstance(error, AIConfigurationError):
        return f"AI {operation} is unavailable because the server is not configured."
    if isinstance(error, AIAuthenticationError):
        return "The AI provider rejected the server credentials."
    if isinstance(error, AIRateLimitError):
        return "The AI service rate limit was reached. Please wait and try again."
    if isinstance(error, AIConnectionError):
        return "The AI service is temporarily unavailable. Please try again shortly."
    if isinstance(error, AITimeoutError):
        return "The AI service timed out. Please try again."
    if isinstance(error, AIModelUnavailableError):
        return "The configured AI model is currently unavailable."
    if isinstance(error, AIResponseError):
        return "The AI service returned an invalid response. Please try again."
    return f"AI {operation} is temporarily unavailable. Please try again."
