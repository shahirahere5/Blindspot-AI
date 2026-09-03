"""
A simple local vector store for Phase 4.

Deliberately not Chroma/a production vector database: the project's own
constraints prioritize simplicity, reliability, and easy local
development, and a single hackathon document rarely has more than a few
hundred chunks -- brute-force cosine similarity over a plain list is fast
enough at that scale and has zero extra runtime dependencies or moving
parts (no server process, no native extensions to build on a judge's
machine).

Persistence: one JSON file per document under `config.RAG_VECTOR_STORE_PATH`
(mirroring `storage/document_store.py`'s one-JSON-file-per-document
pattern), so indexes survive an application restart.

Isolation: every operation is scoped to a single `document_id` -- there is
no cross-document search, by construction (each document's chunks/vectors
live in their own file).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from config import RAG_VECTOR_STORE_PATH
from schemas.rag import DocumentChunk, RetrievedChunk
from storage.path_safety import document_path


class VectorStoreError(Exception):
    """Raised when a vector store read/write/search operation fails."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors. Returns 0.0 for
    a zero vector (e.g. an empty-text embedding) rather than dividing by
    zero."""
    if len(a) != len(b):
        raise VectorStoreError(
            f"Vector dimension mismatch: query has {len(a)} dimensions but "
            f"the index has {len(b)}."
        )
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class SimpleVectorStore:
    """Handles persistence and similarity search of per-document chunk
    embeddings on the local filesystem."""

    def __init__(self, storage_dir: Path = RAG_VECTOR_STORE_PATH) -> None:
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, document_id: str) -> Path:
        return document_path(self.storage_dir, document_id, ".json")

    def is_indexed(self, document_id: str) -> bool:
        return self._path_for(document_id).exists()

    def chunk_count(self, document_id: str) -> int:
        """Number of indexed chunks for a document, or 0 if not indexed."""
        if not self.is_indexed(document_id):
            return 0
        return len(self._load_raw(document_id)["chunks"])

    def index_document(
        self,
        document_id: str,
        chunks: list[DocumentChunk],
        vectors: list[list[float]],
        embedding_provider_name: str,
        embedding_dimension: int,
    ) -> None:
        """Persist (or fully replace) the index for one document.

        Re-indexing a document overwrites its previous index entirely --
        there is no partial/incremental update, which keeps the on-disk
        format simple and avoids ever mixing vectors from two different
        embedding providers/dimensions for the same document.
        """
        if len(chunks) != len(vectors):
            raise VectorStoreError(
                f"Got {len(chunks)} chunks but {len(vectors)} vectors -- "
                "these must be the same length."
            )
        if any(chunk.document_id != document_id for chunk in chunks):
            raise VectorStoreError(
                "Cannot index chunks belonging to a different document."
            )

        payload = {
            "document_id": document_id,
            "embedding_provider": embedding_provider_name,
            "embedding_dimension": embedding_dimension,
            "chunks": [
                {"chunk": chunk.model_dump(mode="json"), "vector": vector}
                for chunk, vector in zip(chunks, vectors)
            ],
        }
        try:
            self._path_for(document_id).write_text(
                json.dumps(payload), encoding="utf-8"
            )
        except OSError as exc:
            raise VectorStoreError(
                f"Failed to persist vector index for document '{document_id}': {exc}"
            ) from exc

    def delete_document(self, document_id: str) -> None:
        """Remove a document's index, if it exists. A no-op otherwise."""
        path = self._path_for(document_id)
        if path.exists():
            try:
                path.unlink()
            except OSError as exc:
                raise VectorStoreError(
                    f"Failed to delete vector index for document '{document_id}': {exc}"
                ) from exc

    def _load_raw(self, document_id: str) -> dict:
        path = self._path_for(document_id)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise VectorStoreError(
                f"Failed to read vector index for document '{document_id}': {exc}"
            ) from exc
        if not isinstance(raw, dict) or raw.get("document_id") != document_id:
            raise VectorStoreError("Vector index document ID does not match its path.")
        if not isinstance(raw.get("chunks"), list):
            raise VectorStoreError("Vector index has an invalid chunk collection.")
        return raw

    def search(
        self, document_id: str, query_vector: list[float], top_k: int
    ) -> list[RetrievedChunk]:
        """
        Return the `top_k` chunks most similar to `query_vector` for a
        single document, ranked by cosine similarity (highest first).

        Returns an empty list if the document has no indexed chunks at all
        (an empty collection is not an error). Raises `VectorStoreError` if
        the index cannot be read, or if the query vector's dimension
        doesn't match the index (e.g. the embedding provider was changed
        after indexing).
        """
        if not self.is_indexed(document_id):
            return []

        raw = self._load_raw(document_id)
        scored: list[RetrievedChunk] = []
        try:
            for entry in raw["chunks"]:
                chunk = DocumentChunk.model_validate(entry["chunk"])
                if chunk.document_id != document_id:
                    raise VectorStoreError(
                        "Vector index contains a chunk from another document."
                    )
                score = _cosine_similarity(query_vector, entry["vector"])
                scored.append(RetrievedChunk(chunk=chunk, score=score))
        except VectorStoreError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise VectorStoreError("Vector index contains invalid data.") from exc

        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[: max(0, top_k)]


# Shared singleton instance used across the API/service layer, mirroring
# `storage/document_store.py`'s `document_store` singleton.
vector_store = SimpleVectorStore()
