"""
A free, fully local, dependency-free embedding provider based on feature
hashing (the "hashing trick").

Why this instead of a real semantic embedding model or a paid embedding
API:

* The project's stated constraints are "use free resources wherever
  possible" and avoid adding a separate local LLM runtime. A hosted embedding
  API would need its own paid/rate-limited account, and Groq (the
  project's only configured AI provider) does not serve embeddings, so
  assuming it could would be incorrect.
* A real local embedding model (e.g. sentence-transformers) requires a
  multi-hundred-MB model download and a heavy dependency (PyTorch), which
  is a poor fit for "easy local development" and a hackathon judge who
  just wants to `pip install` and run.
* Feature hashing needs no training, no model file, and no network access:
  each token is hashed into a fixed-size vector with a deterministic sign,
  giving a bag-of-words-style vector where texts sharing more vocabulary
  score more similar under cosine similarity. It's a well-known, simple,
  and *good enough* baseline for retrieval over a single document's own
  chunks (a much easier task than open-domain search).

This is intentionally not the last word in embedding quality -- it's the
free, zero-dependency default. Swapping in a real semantic embedding model
later only requires implementing `EmbeddingProvider` (see base.py) and
registering it in `factory.py`; nothing else in the RAG pipeline needs to
change.
"""

from __future__ import annotations

import hashlib
import math
import re

import config
from ai.embeddings.base import (
    EmbeddingConfigurationError,
    EmbeddingGenerationError,
    EmbeddingProvider,
)

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class HashingEmbeddingProvider(EmbeddingProvider):
    """Deterministic feature-hashing embedding. Same text always produces
    the exact same vector, on any machine, with no network access."""

    def __init__(self, dimension: int | None = None) -> None:
        resolved_dimension = (
            dimension if dimension is not None else config.RAG_EMBEDDING_DIMENSION
        )
        if resolved_dimension <= 0:
            raise EmbeddingConfigurationError(
                "RAG_EMBEDDING_DIMENSION must be a positive integer."
            )
        self._dimension = resolved_dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def provider_name(self) -> str:
        return "hashing"

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self._dimension
        tokens = _TOKEN_PATTERN.findall((text or "").lower())

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(component * component for component in vector))
        if norm > 0:
            vector = [component / norm for component in vector]
        return vector

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            return [self._embed_one(text) for text in texts]
        except Exception as exc:  # noqa: BLE001 - normalize to EmbeddingError
            raise EmbeddingGenerationError(
                f"Failed to compute local hashing embeddings: {exc}"
            ) from exc
