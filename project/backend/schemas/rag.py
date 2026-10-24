"""
Pydantic models for Phase 4 (RAG): document chunks, retrieval results, and
the request/response bodies for the new indexing/retrieval API endpoints.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DocumentChunk(BaseModel):
    """A single chunk of a document's extracted text, ready to be embedded.

    `source_location` and `source_type` are copied straight from the
    `ContentBlock` (see schemas/document.py) the chunk was cut from, so a
    chunk can never carry a source location that didn't already exist in
    the normalized document -- chunking never invents locations, it only
    ever subdivides real ones.
    """

    document_id: str
    chunk_index: int
    text: str
    source_type: str
    source_location: int
    version_group_id: str | None = None
    version_number: int | None = None


class RetrievedChunk(BaseModel):
    """A chunk returned by a similarity search, with its relevance score."""

    chunk: DocumentChunk
    score: float


class ChunkMetadataResponse(BaseModel):
    chunk_index: int
    source_type: str
    source_location: int


class RetrievedChunkResponse(BaseModel):
    text: str
    score: float
    metadata: ChunkMetadataResponse


class IndexDocumentResponse(BaseModel):
    """Response for POST /api/documents/{document_id}/index."""

    success: bool = True
    document_id: str
    chunks_indexed: int
    embedding_provider: str
    embedding_dimension: int


class RetrieveRequest(BaseModel):
    """Request body for POST /api/documents/{document_id}/retrieve."""

    query: str = Field(..., min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=50)


class RetrieveResponse(BaseModel):
    """Response for POST /api/documents/{document_id}/retrieve."""

    document_id: str
    query: str
    top_k: int
    results: list[RetrievedChunkResponse] = Field(default_factory=list)


class RagErrorResponse(BaseModel):
    success: bool = False
    error: str
    detail: str | None = None
