"""
Analysis service for Phase 2.

Orchestrates a single end-to-end analysis pass:

    normalized document -> labeled content -> AI model -> validated report

This is intentionally a single, unified analyzer (not multiple agents).
The design keeps each concern (prompting, AI transport, JSON safety, schema
validation) in its own module so Phase 3 can replace this orchestration
with a multi-agent version without touching those lower-level pieces.
"""

from __future__ import annotations

import logging

import config
from ai.base import AIClient, AIClientError
from ai.json_utils import JSONExtractionError, extract_json_object
from ai.prompts import SYSTEM_PROMPT, build_user_prompt
from pydantic import ValidationError as PydanticValidationError
from schemas.analysis import AnalysisReport, AnalysisStatus
from services import rag_service
from services.document_service import (
    ensure_document_is_analyzable,
    get_document_or_raise,
    prepare_document_for_analysis,
)

logger = logging.getLogger("blindspot.analysis")


class AnalysisServiceError(Exception):
    """Base class for analysis-service errors surfaced to the API layer."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class AnalysisGenerationError(AnalysisServiceError):
    """Raised when the AI response could not be turned into a valid report."""


def _filter_source_locations(report: AnalysisReport, valid_locations: set[int]) -> None:
    """
    Cross-check every finding's `source_locations` against locations that
    genuinely exist in the document, dropping any that don't. This is a
    best-effort safeguard against the model fabricating a location -- it
    never adds locations, it only ever removes invalid ones.
    """
    for collection in (report.risks, report.assumptions, report.biases):
        for item in collection:
            item.source_locations = [
                loc for loc in item.source_locations if loc in valid_locations
            ]


async def analyze_document(document_id: str, ai_client: AIClient) -> AnalysisReport:
    """
    Run the full Phase 2 analysis pipeline for a document.

    Raises (all defined in services.document_service, allowed to propagate
    to the API layer for precise HTTP status mapping):
        DocumentNotFoundError
        DocumentNotReadyError
        DocumentHasNoAnalyzableContentError
        DocumentTooLargeForAnalysisError

    Raises AnalysisGenerationError if the AI response cannot be turned into
    a valid AnalysisReport. Raises ai.base.AIClientError subclasses if the
    AI backend itself fails (connection, timeout, missing model, etc).

    When config.RAG_ENABLED is true, retrieves and grounds the prompt in
    only the most relevant indexed chunks (auto-indexing the document on
    first use) instead of sending the full document text -- see
    services/rag_service.py. When false (the default), this is byte-for-
    byte the same full-document behavior as Phase 2.
    """
    if config.RAG_ENABLED:
        document = get_document_or_raise(document_id)
        ensure_document_is_analyzable(document)
        rag_service.ensure_document_indexed(document)
        rag_context = rag_service.build_context_from_query(
            document_id, rag_service.ANALYSIS_RETRIEVAL_QUERY
        )
        labeled_content = rag_context.content
        valid_locations = rag_context.valid_locations
        content_item_count = rag_context.item_count
    else:
        _, labeled_content, valid_locations, content_item_count = (
            prepare_document_for_analysis(document_id)
        )

    user_prompt = build_user_prompt(labeled_content, content_item_count)

    # Let AIClientError subclasses propagate untouched -- the API layer maps
    # them to specific, user-facing HTTP errors.
    raw_response = await ai_client.generate(SYSTEM_PROMPT, user_prompt)

    try:
        parsed_json = extract_json_object(raw_response)
    except JSONExtractionError as exc:
        logger.warning(
            "Failed to extract JSON from model response for %s: %s",
            document_id,
            exc.message,
        )
        raise AnalysisGenerationError(
            "The AI model did not return a parseable response. Please try again."
        ) from exc

    parsed_json["document_id"] = document_id
    parsed_json.setdefault("status", AnalysisStatus.COMPLETED.value)
    parsed_json["metadata"] = {
        **(parsed_json.get("metadata") or {}),
        "model": ai_client.model_name,
        "analyzed_content_items": content_item_count,
        "rag_enabled": config.RAG_ENABLED,
    }

    try:
        report = AnalysisReport.model_validate(parsed_json)
    except PydanticValidationError as exc:
        logger.warning(
            "Model response for %s failed schema validation: %s", document_id, exc
        )
        raise AnalysisGenerationError(
            "The AI model's response did not match the expected analysis "
            "format. Please try again."
        ) from exc

    _filter_source_locations(report, valid_locations)

    return report
