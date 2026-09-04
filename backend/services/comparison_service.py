"""Deterministic-first, document-isolated semantic version comparison."""

from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass

import config
from ai.base import AIClient
from ai.comparison_prompts import SYSTEM_PROMPT, build_comparison_prompt
from ai.json_utils import JSONExtractionError, extract_json_object
from pydantic import ValidationError as PydanticValidationError
from schemas.comparison import ComparisonFinding, ComparisonReport, StructuralDiff
from schemas.document import NormalizedDocument
from services import rag_service
from services.document_service import (
    build_labeled_content,
    ensure_document_is_analyzable,
    get_document_or_raise,
)
from storage.comparison_cache import ComparisonCacheError, comparison_cache
from storage.version_store import VersionStore, version_store

logger = logging.getLogger("blindspot.comparison")


class ComparisonGenerationError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass
class _ComparisonContext:
    content: str
    valid_locations: set[int]
    item_count: int


def build_structural_diff(old: NormalizedDocument, new: NormalizedDocument) -> StructuralDiff:
    old_blocks = [(block.text or "").strip() for block in old.content if (block.text or "").strip()]
    new_blocks = [(block.text or "").strip() for block in new.content if (block.text or "").strip()]
    matcher = difflib.SequenceMatcher(a=old_blocks, b=new_blocks, autojunk=False)
    unchanged = added = removed = 0
    added_text: list[str] = []
    removed_text: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            unchanged += i2 - i1
        if tag in {"insert", "replace"}:
            added += j2 - j1
            added_text.extend(new_blocks[j1:j2])
        if tag in {"delete", "replace"}:
            removed += i2 - i1
            removed_text.extend(old_blocks[i1:i2])
    snippet = lambda value: " ".join(value.split())[:300]
    return StructuralDiff(
        old_content_blocks=len(old_blocks),
        new_content_blocks=len(new_blocks),
        unchanged_blocks=unchanged,
        added_blocks=added,
        removed_blocks=removed,
        added_snippets=[snippet(value) for value in added_text[:8]],
        removed_snippets=[snippet(value) for value in removed_text[:8]],
    )


def _full_context(document: NormalizedDocument, version_label: str) -> _ComparisonContext:
    content, locations = build_labeled_content(document)
    labeled = "\n\n".join(
        f"[{version_label} | {section[1:]}" if section.startswith("[") else section
        for section in content.split("\n\n")
    )
    return _ComparisonContext(labeled, locations, len(locations))


def _rag_context(
    document: NormalizedDocument,
    version_label: str,
    query: str,
    version_group_id: str,
    version_number: int,
) -> _ComparisonContext:
    versioned_document = document.model_copy(deep=True)
    versioned_document.metadata["version_group_id"] = version_group_id
    versioned_document.metadata["version_number"] = version_number
    # A document may have been indexed by ordinary analysis before it joined a
    # family. Rebuild once for this uncached comparison so its stored chunks
    # carry the explicit identity; search remains document-ID scoped.
    rag_service.ensure_document_indexed(versioned_document, force=True)
    context = rag_service.build_context_from_query(
        document.document_id, query, config.COMPARISON_RAG_TOP_K
    )
    labeled = "\n\n".join(
        f"[{version_label} | {section[1:]}" if section.startswith("[") else section
        for section in context.content.split("\n\n")
    )
    return _ComparisonContext(labeled, context.valid_locations, context.item_count)


def _comparison_contexts(
    old: NormalizedDocument,
    new: NormalizedDocument,
    diff: StructuralDiff,
    version_group_id: str,
    old_version_number: int,
    new_version_number: int,
) -> tuple[_ComparisonContext, _ComparisonContext, bool]:
    old_full = _full_context(old, "OLD VERSION")
    new_full = _full_context(new, "NEW VERSION")
    if len(old_full.content) + len(new_full.content) <= config.MAX_COMPARISON_CONTENT_CHARS:
        return old_full, new_full, False
    query_parts = diff.added_snippets[:3] + diff.removed_snippets[:3]
    query = "version changes risks assumptions biases recommendations " + " ".join(query_parts)
    return (
        _rag_context(old, "OLD VERSION", query, version_group_id, old_version_number),
        _rag_context(new, "NEW VERSION", query, version_group_id, new_version_number),
        True,
    )


def _filter_sources(report: ComparisonReport, old_valid: set[int], new_valid: set[int]) -> None:
    for field_name, value in report:
        if not isinstance(value, list):
            continue
        for finding in value:
            if isinstance(finding, ComparisonFinding):
                finding.old_source_locations = [loc for loc in finding.old_source_locations if loc in old_valid]
                finding.new_source_locations = [loc for loc in finding.new_source_locations if loc in new_valid]


async def compare_versions(
    old_document_id: str,
    new_document_id: str,
    ai_client: AIClient,
    store: VersionStore | None = None,
) -> ComparisonReport:
    store = store or version_store
    group, old_entry, new_entry = store.require_comparable(old_document_id, new_document_id)
    old = get_document_or_raise(old_document_id)
    new = get_document_or_raise(new_document_id)
    ensure_document_is_analyzable(old)
    ensure_document_is_analyzable(new)

    try:
        cached = comparison_cache.load(old_document_id, new_document_id, ai_client.model_name)
    except ComparisonCacheError:
        logger.warning("Ignoring unreadable comparison cache", exc_info=True)
        cached = None
    if cached:
        cached.metadata["cache_hit"] = True
        return cached

    structural_diff = build_structural_diff(old, new)
    old_context, new_context, rag_used = _comparison_contexts(
        old,
        new,
        structural_diff,
        group.version_group_id,
        old_entry.version_number,
        new_entry.version_number,
    )
    raw = await ai_client.generate(
        SYSTEM_PROMPT,
        build_comparison_prompt(old_context.content, new_context.content, structural_diff),
    )
    try:
        parsed = extract_json_object(raw)
    except JSONExtractionError as exc:
        raise ComparisonGenerationError(
            "The AI model did not return a parseable comparison. Please try again."
        ) from exc
    parsed.update({
        "old_document_id": old_document_id,
        "new_document_id": new_document_id,
        "version_group_id": group.version_group_id,
        "old_version_number": old_entry.version_number,
        "new_version_number": new_entry.version_number,
        "status": "completed",
        "structural_diff": structural_diff.model_dump(),
        "metadata": {
            **(parsed.get("metadata") or {}),
            "model": ai_client.model_name,
            "rag_enabled": rag_used,
            "old_context_items": old_context.item_count,
            "new_context_items": new_context.item_count,
            "cache_hit": False,
        },
    })
    try:
        report = ComparisonReport.model_validate(parsed)
    except PydanticValidationError as exc:
        logger.warning("Comparison response failed validation: %s", exc)
        raise ComparisonGenerationError(
            "The AI model's response did not match the expected comparison format. Please try again."
        ) from exc
    _filter_sources(report, old_context.valid_locations, new_context.valid_locations)
    try:
        comparison_cache.save(report, ai_client.model_name)
    except ComparisonCacheError:
        logger.warning("Comparison completed but could not be cached", exc_info=True)
    return report
