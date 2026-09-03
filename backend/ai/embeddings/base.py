"""
Embedding provider interface for Phase 4 (RAG).

Deliberately mirrors the existing `ai/base.py` pattern (an abstract
interface + a small, specific error hierarchy) so embeddings plug into the
same conventions as the Groq generation client, even though embeddings and
generation are two independent concerns with two independent providers --
Groq is a generation API and does not need to also provide embeddings.

Providers are swappable: today only a free, local, dependency-free
"hashing" provider is implemented (see hashing.py), but any future provider
(a real semantic embedding model, a paid embedding API, etc) only needs to
implement this interface -- nothing else in the RAG pipeline
(rag/chunking.py, storage/vector_store.py, services/retrieval_service.py)
needs to know or care which provider is in use.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingError(Exception):
    """Base class for every embedding-layer error."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class EmbeddingConfigurationError(EmbeddingError):
    """Raised when the configured embedding provider is invalid/unavailable
    (e.g. an unknown `RAG_EMBEDDING_PROVIDER` value, or a provider whose
    optional dependency is not installed)."""


class EmbeddingGenerationError(EmbeddingError):
    """Raised when embedding one or more texts fails unexpectedly."""


class EmbeddingProvider(ABC):
    """Interface every embedding provider must implement."""

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a batch of texts, returning one vector per input text in the
        same order. Never mutates `texts`. Raises `EmbeddingGenerationError`
        on failure -- never returns a partial/malformed result.

        An empty `texts` list returns an empty list (not an error).
        """

    @property
    @abstractmethod
    def dimension(self) -> int:
        """The fixed length of every vector this provider returns."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """A short, stable identifier for this provider (stored in the
        vector store alongside its vectors, so a later mismatch between the
        configured provider and an already-indexed document can be
        detected rather than silently comparing incompatible vectors)."""
