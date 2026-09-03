"""
AI client abstraction.

`AIClient` is the interface the rest of the application depends on. The
current concrete implementation is `GroqClient`; the abstraction keeps
provider transport details out of the analysis and debate services.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class AIClientError(Exception):
    """Base class for all AI client errors."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class AIConfigurationError(AIClientError):
    """Raised when the AI client is missing required configuration (e.g. no API key)."""


class AIAuthenticationError(AIClientError):
    """Raised when the AI provider rejects the request due to invalid credentials."""


class AIRateLimitError(AIClientError):
    """Raised when the AI provider reports that a rate limit has been reached."""


class AIConnectionError(AIClientError):
    """Raised when the AI backend cannot be reached at all (network/DNS failure)."""


class AIModelUnavailableError(AIClientError):
    """Raised when the backend is reachable but the requested model is missing/invalid."""


class AITimeoutError(AIClientError):
    """Raised when the AI backend does not respond within the configured timeout."""


class AIResponseError(AIClientError):
    """Raised when the AI backend returns an unexpected/invalid response."""


class AIClient(ABC):
    """Minimal interface every AI provider client must implement."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """The configured model name, used for reporting in analysis metadata."""
        raise NotImplementedError

    @abstractmethod
    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send a system + user prompt to the model and return the raw text
        response. Implementations must raise a subclass of `AIClientError`
        on any failure rather than letting provider-specific exceptions leak.
        """
        raise NotImplementedError
