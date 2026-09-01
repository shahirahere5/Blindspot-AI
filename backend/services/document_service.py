"""
Document service for Phase 2.

Thin layer between the analysis API/service and the existing Phase 1
storage layer. Responsible for:

* Fetching a normalized document by ID.
* Validating that it is actually ready to be analyzed.
* Building the labeled, source-marked text blob sent to the AI model.

This does not duplicate or modify any Phase 1 processing/storage logic --
it only reads from the existing `document_store`.
"""

from __future__ import annotations

import config
from schemas.document import ContentBlockType, DocumentStatus, NormalizedDocument
from storage.document_store import document_store

# Human-readable marker labels per content block type, used to build the
# "[TYPE N]" source markers shown to the model (and referenced back in
# `source_locations`).
_MARKER_LABELS: dict[ContentBlockType, str] = {
    ContentBlockType.PAGE: "PAGE",
    ContentBlockType.SLIDE: "SLIDE",
    ContentBlockType.PARAGRAPH: "PARAGRAPH",
    ContentBlockType.TABLE: "TABLE",
    ContentBlockType.TEXT: "TEXT",
}


class DocumentServiceError(Exception):
    """Base class for document-service errors surfaced to the API layer."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class DocumentNotFoundError(DocumentServiceError):
    """Raised when the requested document_id does not exist."""


class DocumentNotReadyError(DocumentServiceError):
    """Raised when the document exists but is not in a state that can be analyzed."""


class DocumentTooLargeForAnalysisError(DocumentServiceError):
    """Raised when the document's extracted text exceeds the configured limit."""


class DocumentHasNoAnalyzableContentError(DocumentServiceError):
    """Raised when a processed document has no non-empty text content at all."""


def get_document_or_raise(document_id: str) -> NormalizedDocument:
    """Load a normalized document, raising DocumentNotFoundError if missing."""
    document = document_store.load_normalized_document(document_id)
    if document is None:
        raise DocumentNotFoundError(f"Document '{document_id}' was not found.")
    return document


def ensure_document_is_analyzable(document: NormalizedDocument) -> None:
    """
    Validate that a document is in a state Phase 2 can analyze.

    Raises DocumentNotReadyError with a clear, user-facing message for every
    non-analyzable state (image pending multimodal analysis, scanned PDF
    requiring multimodal processing, or a failed document).
    """
    if document.status == DocumentStatus.PENDING_MULTIMODAL_ANALYSIS:
        raise DocumentNotReadyError(
            "This document is an image pending multimodal analysis. "
            "Image understanding is planned for a later phase and is not "
            "yet supported by the analyzer."
        )

    if document.status == DocumentStatus.REQUIRES_MULTIMODAL_PROCESSING:
        raise DocumentNotReadyError(
            "This document appears to require OCR/multimodal processing "
            "(e.g. a scanned PDF with no extractable text) which is not "
            "yet supported by the analyzer."
        )

    if document.status == DocumentStatus.FAILED:
        raise DocumentNotReadyError(
            "This document failed processing and cannot be analyzed."
        )

    if document.status != DocumentStatus.PROCESSED:
        raise DocumentNotReadyError(
            f"Document status '{document.status.value}' is not eligible for analysis."
        )


def build_labeled_content(document: NormalizedDocument) -> tuple[str, set[int]]:
    """
    Build the labeled, source-marked text blob sent to the model.

    Returns a tuple of (labeled_text, valid_locations) where valid_locations
    is the set of integer locations that genuinely exist in the document, so
    the analysis service can cross-check the model's `source_locations`
    against real content rather than trusting them blindly.
    """
    sections: list[str] = []
    valid_locations: set[int] = set()

    for block in document.content:
        text = (block.text or "").strip()
        if not text:
            continue

        label = _MARKER_LABELS.get(block.type, block.type.value.upper())
        sections.append(f"[{label} {block.location}]\n{text}")
        valid_locations.add(block.location)

    labeled_text = "\n\n".join(sections)
    return labeled_text, valid_locations


def prepare_document_for_analysis(
    document_id: str,
) -> tuple[NormalizedDocument, str, set[int], int]:
    """
    Full preparation pipeline: fetch, validate, and build labeled content.

    Returns (document, labeled_text, valid_locations, content_item_count).
    Raises DocumentNotFoundError, DocumentNotReadyError,
    DocumentHasNoAnalyzableContentError, or DocumentTooLargeForAnalysisError.
    """
    document = get_document_or_raise(document_id)
    ensure_document_is_analyzable(document)

    labeled_text, valid_locations = build_labeled_content(document)

    if not labeled_text.strip():
        raise DocumentHasNoAnalyzableContentError(
            "This document has no extractable text content to analyze."
        )

    if len(labeled_text) > config.MAX_ANALYSIS_CONTENT_CHARS:
        raise DocumentTooLargeForAnalysisError(
            "This document's extracted text "
            f"({len(labeled_text):,} characters) exceeds the maximum "
            f"supported for a single analysis pass "
            f"({config.MAX_ANALYSIS_CONTENT_CHARS:,} characters). "
            "Chunked/RAG-based analysis for large documents is planned for "
            "a later phase."
        )

    content_item_count = sum(1 for block in document.content if (block.text or "").strip())

    return document, labeled_text, valid_locations, content_item_count
