"""Unit tests for rag/chunking.py."""

from __future__ import annotations

from rag.chunking import chunk_document
from schemas.document import (
    ContentBlock,
    ContentBlockType,
    DocumentStatus,
    FileType,
    NormalizedDocument,
)


def _make_document(blocks: list[ContentBlock], document_id: str = "doc_1") -> NormalizedDocument:
    return NormalizedDocument(
        document_id=document_id,
        filename="test.txt",
        file_type=FileType.TXT,
        status=DocumentStatus.PROCESSED,
        content=blocks,
    )


def test_short_block_produces_a_single_chunk():
    document = _make_document(
        [ContentBlock(type=ContentBlockType.PAGE, location=1, text="A short page.")]
    )

    chunks = chunk_document(document, chunk_size=800, chunk_overlap=150)

    assert len(chunks) == 1
    assert chunks[0].text == "A short page."
    assert chunks[0].source_location == 1
    assert chunks[0].source_type == "page"
    assert chunks[0].chunk_index == 0
    assert chunks[0].document_id == "doc_1"


def test_long_block_is_split_into_multiple_chunks():
    long_text = " ".join(f"word{i}" for i in range(300))
    document = _make_document(
        [ContentBlock(type=ContentBlockType.PAGE, location=1, text=long_text)]
    )

    chunks = chunk_document(document, chunk_size=100, chunk_overlap=20)

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk.text) <= 130  # allow slack for a single long word
        assert chunk.source_location == 1
        assert chunk.source_type == "page"


def test_chunk_overlap_repeats_trailing_words():
    long_text = " ".join(f"word{i}" for i in range(300))
    document = _make_document(
        [ContentBlock(type=ContentBlockType.PAGE, location=1, text=long_text)]
    )

    chunks = chunk_document(document, chunk_size=100, chunk_overlap=20)

    first_words = chunks[0].text.split()
    second_words = chunks[1].text.split()
    overlap = set(first_words[-3:]) & set(second_words[:3])
    assert overlap, "expected some trailing words from chunk 0 to reappear at the start of chunk 1"


def test_no_overlap_configured_still_produces_valid_chunks():
    long_text = " ".join(f"word{i}" for i in range(300))
    document = _make_document(
        [ContentBlock(type=ContentBlockType.PAGE, location=1, text=long_text)]
    )

    chunks = chunk_document(document, chunk_size=100, chunk_overlap=0)

    assert len(chunks) > 1
    # Every word appears exactly once across all chunks when there's no overlap.
    all_words = [w for c in chunks for w in c.text.split()]
    assert all_words == [f"word{i}" for i in range(300)]


def test_page_and_slide_metadata_is_preserved_across_blocks():
    document = _make_document(
        [
            ContentBlock(type=ContentBlockType.PAGE, location=1, text="Page one content."),
            ContentBlock(type=ContentBlockType.PAGE, location=2, text="Page two content."),
            ContentBlock(type=ContentBlockType.SLIDE, location=1, text="Slide one content."),
        ]
    )

    chunks = chunk_document(document, chunk_size=800, chunk_overlap=150)

    assert [c.source_type for c in chunks] == ["page", "page", "slide"]
    assert [c.source_location for c in chunks] == [1, 2, 1]


def test_chunk_indexes_are_sequential_across_the_whole_document():
    document = _make_document(
        [
            ContentBlock(type=ContentBlockType.PAGE, location=1, text="Page one."),
            ContentBlock(type=ContentBlockType.PAGE, location=2, text="Page two."),
            ContentBlock(type=ContentBlockType.PAGE, location=3, text="Page three."),
        ]
    )

    chunks = chunk_document(document, chunk_size=800, chunk_overlap=150)

    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_empty_blocks_are_skipped():
    document = _make_document(
        [
            ContentBlock(type=ContentBlockType.PAGE, location=1, text="   "),
            ContentBlock(type=ContentBlockType.PAGE, location=2, text="Real content."),
        ]
    )

    chunks = chunk_document(document, chunk_size=800, chunk_overlap=150)

    assert len(chunks) == 1
    assert chunks[0].source_location == 2


def test_empty_document_produces_no_chunks():
    document = _make_document([])

    chunks = chunk_document(document, chunk_size=800, chunk_overlap=150)

    assert chunks == []


def test_overlap_larger_than_chunk_size_is_clamped_not_infinite():
    long_text = " ".join(f"word{i}" for i in range(50))
    document = _make_document(
        [ContentBlock(type=ContentBlockType.PAGE, location=1, text=long_text)]
    )

    # chunk_overlap >= chunk_size would otherwise never let chunking progress.
    chunks = chunk_document(document, chunk_size=20, chunk_overlap=999)

    assert len(chunks) > 1
