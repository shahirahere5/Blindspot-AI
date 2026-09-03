"""Factory for resolving the configured embedding provider.

Kept as its own tiny module (mirroring `ai/client.py`'s `get_ai_client()`)
so callers never need to know which concrete provider is configured -- and
so tests can monkeypatch a single function rather than every call site.
"""

from __future__ import annotations

import config
from ai.embeddings.base import EmbeddingConfigurationError, EmbeddingProvider
from ai.embeddings.hashing import HashingEmbeddingProvider

_PROVIDERS: dict[str, type[EmbeddingProvider]] = {
    "hashing": HashingEmbeddingProvider,
}


def get_embedding_provider() -> EmbeddingProvider:
    """Return the embedding provider configured via `RAG_EMBEDDING_PROVIDER`.

    Raises EmbeddingConfigurationError for an unknown provider name -- this
    is a server misconfiguration, not a per-request error.
    """
    name = config.RAG_EMBEDDING_PROVIDER.strip().lower()
    provider_cls = _PROVIDERS.get(name)
    if provider_cls is None:
        supported = ", ".join(sorted(_PROVIDERS))
        raise EmbeddingConfigurationError(
            f"Unknown RAG_EMBEDDING_PROVIDER '{config.RAG_EMBEDDING_PROVIDER}'. "
            f"Supported providers: {supported}. The embedding interface "
            "(ai/embeddings/base.py) is designed to be extended with "
            "additional providers (e.g. a real semantic embedding model) -- "
            "see the README for details."
        )
    return provider_cls()
