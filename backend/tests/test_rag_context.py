"""Tests for rag/context_builder.py."""

from __future__ import annotations

from rag.context_builder import build_rag_context
from schemas.rag import DocumentChunk, RetrievedChunk


def _retrieved(text: str, source_type: str, location: int, score: float = 0.9) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=DocumentChunk(
            document_id="doc_1",
            chunk_index=0,
            text=text,
            source_type=source_type,
            source_location=location,
        ),
        score=score,
    )


def test_context_formats_source_labels_as_specified():
    chunks = [_retrieved("Some page text.", "page", 2)]

    content, _ = build_rag_context(chunks)

    assert content == "[Source: Page 2]\nSome page text."


def test_context_handles_multiple_chunks_and_source_types():
    chunks = [
        _retrieved("Page content.", "page", 2),
        _retrieved("Slide content.", "slide", 5),
    ]

    content, _ = build_rag_context(chunks)

    assert "[Source: Page 2]\nPage content." in content
    assert "[Source: Slide 5]\nSlide content." in content
    # Sections are separated so they're visually distinguishable.
    assert "\n\n" in content


def test_valid_locations_reflects_only_retrieved_chunks():
    chunks = [
        _retrieved("A.", "page", 1),
        _retrieved("B.", "page", 7),
    ]

    _, valid_locations = build_rag_context(chunks)

    assert valid_locations == {1, 7}


def test_empty_retrieved_chunks_produce_empty_context():
    content, valid_locations = build_rag_context([])

    assert content == ""
    assert valid_locations == set()


def test_never_invents_a_location_not_present_in_retrieved_chunks():
    chunks = [_retrieved("Only page 3 was retrieved.", "page", 3)]

    _, valid_locations = build_rag_context(chunks)

    # Locations that were never retrieved must never appear as "valid".
    assert 1 not in valid_locations
    assert 2 not in valid_locations
    assert valid_locations == {3}
