"""
Retrieval service for Phase 4.

Thin orchestration layer over `rag/chunking.py`, `ai/embeddings/*`, and
`storage/vector_store.py` -- mirrors `services/document_service.py`'s role
for Phase 2/3 (a service module that composes lower-level, independently
testable pieces, rather than API routes or other services reaching into
chunking/embeddings/vector-store directly).

Error handling follows the same convention as `services/debate_service.py`:
only genuinely retrieval-specific conditions get their own exception type
here (`DocumentNotIndexedError`); embedding failures (`EmbeddingError` and
subclasses) and vector-store failures (`VectorStoreError`) are left to
propagate untouched so the API layer can map them precisely, the same way
`AIClientError` subclasses propagate untouched out of `debate_service.py`.
"""

from __future__ import annotations

from ai.embeddings.base import EmbeddingProvider
from ai.embeddings.factory import get_embedding_provider
from rag.chunking import chunk_document
from schemas.document import NormalizedDocument
from schemas.rag import RetrievedChunk
from services.document_service import DocumentHasNoAnalyzableContentError
from storage.vector_store import vector_store

import config


class RetrievalServiceError(Exception):
    """Base class for retrieval-service errors surfaced to the API layer."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class DocumentNotIndexedError(RetrievalServiceError):
    """Raised when retrieval is requested for a document with no index yet."""


def ensure_document_indexed(
    document: NormalizedDocument,
    *,
    force: bool = False,
    embedding_provider: EmbeddingProvider | None = None,
) -> int:
    """
    Index a document's chunks into the vector store if it isn't already
    indexed (or unconditionally, if `force=True` -- used for explicit
    re-indexing).

    Returns the number of chunks now indexed for this document.

    Raises DocumentHasNoAnalyzableContentError (reused from
    services.document_service -- same meaning: no usable text at all) if
    chunking produces zero chunks. Raises ai.embeddings.base.EmbeddingError
    subclasses or storage.vector_store.VectorStoreError untouched on
    embedding/storage failure.
    """
    provider = embedding_provider or get_embedding_provider()

    if not force and vector_store.is_indexed(document.document_id):
        return vector_store.chunk_count(document.document_id)

    chunks = chunk_document(document)
    if not chunks:
        raise DocumentHasNoAnalyzableContentError(
            "This document has no extractable text content to index."
        )

    vectors = provider.embed_texts([chunk.text for chunk in chunks])

    vector_store.index_document(
        document.document_id,
        chunks,
        vectors,
        provider.provider_name,
        provider.dimension,
    )

    return len(chunks)


def retrieve_relevant_chunks(
    document_id: str,
    query: str,
    top_k: int | None = None,
    *,
    embedding_provider: EmbeddingProvider | None = None,
) -> list[RetrievedChunk]:
    """
    Retrieve the `top_k` chunks most relevant to `query` for a single
    document.

    Raises DocumentNotIndexedError if the document has not been indexed yet
    (call `ensure_document_indexed` first). Never retrieves chunks from any
    other document -- the vector store itself enforces this by storing and
    searching one document's chunks per file (see storage/vector_store.py).
    """
    if not vector_store.is_indexed(document_id):
        raise DocumentNotIndexedError(
            f"Document '{document_id}' has not been indexed for retrieval "
            "yet. Index it first via POST /api/documents/{document_id}/index."
        )

    resolved_top_k = top_k if top_k is not None else config.RAG_TOP_K
    provider = embedding_provider or get_embedding_provider()

    query_vector = provider.embed_texts([query])[0]

    return vector_store.search(document_id, query_vector, resolved_top_k)
