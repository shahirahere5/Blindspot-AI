"""
Document chunking for Phase 4 (RAG).

Operates directly on the already-extracted `NormalizedDocument.content`
(see schemas/document.py) produced by Phase 1 -- it does not re-parse or
re-extract anything. Each `ContentBlock` (a page, slide, paragraph, or
table) is split independently into one or more `DocumentChunk`s, so a
chunk's `source_location`/`source_type` are always copied directly from a
real `ContentBlock` and can never be invented.

Chunking is word-aware: it accumulates whole words up to `chunk_size`
characters and never splits a word in half, which is a simple, dependency-
free way to "avoid destroying meaningful document boundaries" without
needing a sentence tokenizer.
"""

from __future__ import annotations

import config
from schemas.document import NormalizedDocument
from schemas.rag import DocumentChunk


def _split_text_into_pieces(
    text: str, chunk_size: int, chunk_overlap: int
) -> list[str]:
    """Split `text` into word-aware pieces of at most `chunk_size` characters,
    with roughly `chunk_overlap` characters of trailing context repeated at
    the start of the next piece.

    A block whose text already fits within `chunk_size` is returned as a
    single piece unchanged (chunking should never fragment short content).
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    words = text.split()
    pieces: list[str] = []
    current: list[str] = []
    current_len = 0

    for word in words:
        separator = 1 if current else 0
        projected_len = current_len + len(word) + separator

        if current and projected_len > chunk_size:
            pieces.append(" ".join(current))
            # Seed the next piece with a trailing overlap window from the
            # piece we just closed, so context isn't lost at chunk edges.
            overlap: list[str] = []
            overlap_len = 0
            for w in reversed(current):
                extra = len(w) + (1 if overlap else 0)
                if overlap_len + extra > chunk_overlap:
                    break
                overlap.insert(0, w)
                overlap_len += extra
            current = overlap
            current_len = overlap_len
            separator = 1 if current else 0
            projected_len = current_len + len(word) + separator

        current.append(word)
        current_len = projected_len

    if current:
        pieces.append(" ".join(current))

    return pieces


def chunk_document(
    document: NormalizedDocument,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[DocumentChunk]:
    """
    Split every non-empty content block of a normalized document into
    `DocumentChunk`s, preserving each chunk's original source location and
    type, and assigning a stable, document-wide `chunk_index` in reading
    order.

    Uses `config.RAG_CHUNK_SIZE`/`config.RAG_CHUNK_OVERLAP` when not given
    explicitly. An overlap greater than or equal to the chunk size is
    clamped down (otherwise chunking would never make progress).
    """
    chunk_size = chunk_size if chunk_size is not None else config.RAG_CHUNK_SIZE
    chunk_overlap = (
        chunk_overlap if chunk_overlap is not None else config.RAG_CHUNK_OVERLAP
    )
    chunk_size = max(1, chunk_size)
    chunk_overlap = max(0, min(chunk_overlap, chunk_size - 1))

    chunks: list[DocumentChunk] = []
    index = 0
    version_group_id = document.metadata.get("version_group_id")
    version_number = document.metadata.get("version_number")
    if not isinstance(version_group_id, str):
        version_group_id = None
    if not isinstance(version_number, int) or version_number < 1:
        version_number = None

    for block in document.content:
        text = (block.text or "").strip()
        if not text:
            continue

        for piece in _split_text_into_pieces(text, chunk_size, chunk_overlap):
            chunks.append(
                DocumentChunk(
                    document_id=document.document_id,
                    chunk_index=index,
                    text=piece,
                    source_type=block.type.value,
                    source_location=block.location,
                    version_group_id=version_group_id,
                    version_number=version_number,
                )
            )
            index += 1

    return chunks
