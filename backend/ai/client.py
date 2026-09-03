"""
Groq-backed implementation of the AIClient interface.

Groq (https://groq.com) exposes an OpenAI-compatible Chat Completions API
and hosts fast inference for open-weight models (e.g. Meta Llama, OpenAI's
gpt-oss). This client talks to that API directly over HTTP via `httpx`
(already a project dependency) rather than adding the Groq SDK, since a
simple Chat Completions POST does not need it.

All connection settings are read from `config.py`, which itself reads from
environment variables (see `.env.example`). The API key is never hardcoded
and is treated as required configuration -- its absence is a controlled
`AIConfigurationError`, not a crash.
"""

from __future__ import annotations

import httpx

import config
from ai.base import (
    AIAuthenticationError,
    AIClient,
    AIConfigurationError,
    AIConnectionError,
    AIModelUnavailableError,
    AIRateLimitError,
    AIResponseError,
    AITimeoutError,
)


class GroqClient(AIClient):
    # Sentinel distinguishing "api_key not passed at all" (fall back to
    # config.GROQ_API_KEY, as `get_ai_client()` relies on for real usage)
    # from "api_key explicitly passed as None" (means no key, full stop --
    # must never silently fall back to whatever happens to be in the
    # environment/.env at runtime, e.g. during tests).
    _UNSET = object()

    def __init__(
        self,
        api_key: str | None = _UNSET,  # type: ignore[assignment]
        base_url: str | None = None,
        model: str | None = None,
        request_timeout_seconds: float | None = None,
        connect_timeout_seconds: float | None = None,
        temperature: float | None = None,
    ) -> None:
        self.api_key = config.GROQ_API_KEY if api_key is self._UNSET else api_key
        self.base_url = (base_url or config.GROQ_BASE_URL).rstrip("/")
        self.model = model or config.GROQ_MODEL
        self.request_timeout_seconds = (
            request_timeout_seconds
            if request_timeout_seconds is not None
            else config.GROQ_TIMEOUT_SECONDS
        )
        self.connect_timeout_seconds = (
            connect_timeout_seconds
            if connect_timeout_seconds is not None
            else config.GROQ_CONNECT_TIMEOUT_SECONDS
        )
        self.temperature = (
            temperature if temperature is not None else config.GROQ_TEMPERATURE
        )

    @property
    def model_name(self) -> str:
        return self.model

    def _build_http_client(self, timeout: httpx.Timeout) -> httpx.AsyncClient:
        """
        Construct the underlying httpx client. Isolated into its own method
        so tests can inject a mock transport without touching global state.
        """
        return httpx.AsyncClient(timeout=timeout)

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Call Groq's OpenAI-compatible /chat/completions endpoint."""
        if not self.api_key or not self.api_key.strip():
            raise AIConfigurationError(
                "GROQ_API_KEY is not set. Add it to your .env file "
                "(see .env.example) before requesting an analysis. "
                "You can create a key at https://console.groq.com/keys."
            )

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        timeout = httpx.Timeout(
            self.request_timeout_seconds, connect=self.connect_timeout_seconds
        )

        try:
            async with self._build_http_client(timeout) as http_client:
                response = await http_client.post(url, json=payload, headers=headers)
        except httpx.ConnectTimeout as exc:
            raise AIConnectionError(
                f"Could not connect to Groq at {self.base_url} "
                "(connection timed out). Check your network connection."
            ) from exc
        except httpx.ConnectError as exc:
            raise AIConnectionError(
                f"Could not connect to Groq at {self.base_url}. "
                "Check your network connection and GROQ_BASE_URL."
            ) from exc
        except httpx.TimeoutException as exc:
            raise AITimeoutError(
                f"Groq did not respond within {self.request_timeout_seconds:.0f}s."
            ) from exc
        except httpx.HTTPError as exc:
            raise AIConnectionError(f"Error communicating with Groq: {exc}") from exc

        return self._handle_response(response)

    def _handle_response(self, response: httpx.Response) -> str:
        if response.status_code == 401:
            raise AIAuthenticationError(
                "Groq rejected the request due to an invalid API key. "
                "Check GROQ_API_KEY in your .env file."
            )

        if response.status_code == 429:
            raise AIRateLimitError(
                "The Groq API rate limit was reached for the configured "
                "API key. Please wait a moment and try again."
            )

        if response.status_code == 404:
            raise AIModelUnavailableError(
                f"Model '{self.model}' is not available on Groq. "
                "Check GROQ_MODEL and see https://console.groq.com/docs/models "
                "for currently supported models."
            )

        if response.status_code == 400:
            detail = self._extract_error_message(response)
            if detail and "model" in detail.lower():
                raise AIModelUnavailableError(
                    f"Groq rejected the request, likely due to an invalid "
                    f"model configuration: {detail}"
                )
            raise AIResponseError(f"Groq rejected the request: {detail or 'bad request'}.")

        if response.status_code >= 500:
            raise AIConnectionError(
                f"Groq returned a server error (status {response.status_code}). "
                "This is usually temporary; please try again shortly."
            )

        if response.status_code != 200:
            raise AIResponseError(
                f"Groq returned an unexpected status code {response.status_code}."
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise AIResponseError("Groq returned a non-JSON HTTP response.") from exc

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIResponseError(
                "Groq response did not contain the expected message content."
            ) from exc

        if not content or not isinstance(content, str):
            raise AIResponseError(
                "Groq response did not contain the expected message content."
            )

        return content

    @staticmethod
    def _extract_error_message(response: httpx.Response) -> str | None:
        try:
            body = response.json()
        except ValueError:
            return None
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                return error.get("message")
            if isinstance(error, str):
                return error
        return None


def get_ai_client() -> AIClient:
    """
    Factory returning the configured AI client.

    Only Groq is implemented today, but this indirection lets a future
    provider be selected via `config.AI_PROVIDER` without touching callers.
    """
    if config.AI_PROVIDER == "groq":
        return GroqClient()
    raise ValueError(f"Unsupported AI_PROVIDER: '{config.AI_PROVIDER}'")
