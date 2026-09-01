"""
Pydantic models describing the normalized document representation.

This is the contract between Phase 1 (Input Pipeline) and every future
phase (LLM analysis, RAG, specialist agents, etc). Future phases should be
able to consume `NormalizedDocument` without any knowledge of the original
file format.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class FileType(str, Enum):
    PDF = "pdf"
    PPTX = "pptx"
    DOCX = "docx"
    TXT = "txt"
    IMAGE = "image"


class DocumentStatus(str, Enum):
    PROCESSED = "processed"
    REQUIRES_MULTIMODAL_PROCESSING = "requires_multimodal_processing"
    PENDING_MULTIMODAL_ANALYSIS = "pending_multimodal_analysis"
    FAILED = "failed"


class ContentBlockType(str, Enum):
    PAGE = "page"
    SLIDE = "slide"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    TEXT = "text"


class ContentBlock(BaseModel):
    """A single unit of extracted content (a page, a slide, a paragraph...)."""

    type: ContentBlockType
    location: int = Field(..., description="1-indexed position within the document")
    text: str = ""
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional format-specific metadata (e.g. slide title).",
    )


class NormalizedDocument(BaseModel):
    """The common internal representation for every supported input format."""

    document_id: str
    filename: str
    file_type: FileType
    status: DocumentStatus
    content: list[ContentBlock] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class UploadResponse(BaseModel):
    """Response returned by POST /api/documents/upload."""

    success: bool
    document_id: str
    filename: str
    file_type: FileType
    status: DocumentStatus
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """Uniform error payload returned to clients."""

    success: bool = False
    error: str
    detail: str | None = None
