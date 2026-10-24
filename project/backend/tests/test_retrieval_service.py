"""Tests for services/retrieval_service.py (indexing + retrieval orchestration)."""

from __future__ import annotations

import pytest

from schemas.document import (
    ContentBlock,
    ContentBlockType,
    DocumentStatus,
    FileType,
    NormalizedDocument,
)
from services.document_service import DocumentHasNoAnalyzableContentError
from services.retrieval_service import (
    DocumentNotIndexedError,
    ensure_document_indexed,
    retrieve_relevant_chunks,
)
from tests.fakes import FakeEmbeddingProvider


def _document(document_id: str, texts: list[str]) -> NormalizedDocument:
    return NormalizedDocument(
        document_id=document_id,
        filename="test.txt",
        file_type=FileType.TXT,
        status=DocumentStatus.PROCESSED,
        content=[
            ContentBlock(type=ContentBlockType.PAGE, location=i + 1, text=text)
            for i, text in enumerate(texts)
        ],
    )


def test_ensure_document_indexed_indexes_a_new_document(client):
    provider = FakeEmbeddingProvider(dimension=4)
    document = _document("doc_x", ["hello world"])

    count = ensure_document_indexed(document, embedding_provider=provider)

    assert count == 1
    assert provider.calls  # embedding was actually invoked


def test_ensure_document_indexed_skips_reindexing_when_already_indexed(client):
    provider = FakeEmbeddingProvider(dimension=4)
    document = _document("doc_x", ["hello world"])

    ensure_document_indexed(document, embedding_provider=provider)
    call_count_after_first = len(provider.calls)
    ensure_document_indexed(document, embedding_provider=provider)

    assert len(provider.calls) == call_count_after_first  # no second embedding call


def test_ensure_document_indexed_force_reindexes(client):
    provider = FakeEmbeddingProvider(dimension=4)
    document = _document("doc_x", ["hello world"])

    ensure_document_indexed(document, embedding_provider=provider)
    ensure_document_indexed(document, force=True, embedding_provider=provider)

    assert len(provider.calls) == 2


def test_ensure_document_indexed_empty_document_raises(client):
    provider = FakeEmbeddingProvider(dimension=4)
    document = _document("doc_empty", ["   ", ""])

    with pytest.raises(DocumentHasNoAnalyzableContentError):
        ensure_document_indexed(document, embedding_provider=provider)


def test_retrieve_before_indexing_raises_not_indexed(client):
    with pytest.raises(DocumentNotIndexedError):
        retrieve_relevant_chunks(
            "doc_never_indexed", "query", embedding_provider=FakeEmbeddingProvider()
        )


def test_retrieve_top_k_behavior(client):
    provider = FakeEmbeddingProvider(
        dimension=2,
        vectors={
            "chunk about cats": [1.0, 0.0],
            "chunk about dogs": [0.9, 0.1],
            "chunk about finance": [0.0, 1.0],
        },
        default_vector=[1.0, 0.0],
    )
    document = _document(
        "doc_pets",
        ["chunk about cats", "chunk about dogs", "chunk about finance"],
    )
    ensure_document_indexed(document, embedding_provider=provider)

    results = retrieve_relevant_chunks(
        "doc_pets", "query", top_k=2, embedding_provider=provider
    )

    assert len(results) == 2
    # The two pet-related chunks should rank above the finance chunk for a
    # query embedded identically to the pet chunks (via default_vector).
    texts = {r.chunk.text for r in results}
    assert "chunk about finance" not in texts


def test_retrieve_preserves_source_metadata(client):
    provider = FakeEmbeddingProvider(dimension=2, default_vector=[1.0, 0.0])
    document = _document("doc_meta", ["some content"])
    ensure_document_indexed(document, embedding_provider=provider)

    results = retrieve_relevant_chunks(
        "doc_meta", "query", embedding_provider=provider
    )

    assert results[0].chunk.source_type == "page"
    assert results[0].chunk.source_location == 1
    assert results[0].chunk.document_id == "doc_meta"


def test_retrieve_never_crosses_documents(client):
    provider = FakeEmbeddingProvider(dimension=2, default_vector=[1.0, 0.0])
    doc_a = _document("doc_a", ["content a"])
    doc_b = _document("doc_b", ["content b"])
    ensure_document_indexed(doc_a, embedding_provider=provider)
    ensure_document_indexed(doc_b, embedding_provider=provider)

    results_a = retrieve_relevant_chunks("doc_a", "query", embedding_provider=provider)

    assert all(r.chunk.document_id == "doc_a" for r in results_a)


def test_retrieval_failure_propagates_embedding_error(client):
    failing_provider = FakeEmbeddingProvider(dimension=2, fail=True)
    document = _document("doc_fail", ["some content"])

    # Index with a working provider first so the "not indexed" branch isn't
    # what's under test here -- we want the query-embedding failure itself.
    ensure_document_indexed(document, embedding_provider=FakeEmbeddingProvider(dimension=2))

    from ai.embeddings.base import EmbeddingGenerationError

    with pytest.raises(EmbeddingGenerationError):
        retrieve_relevant_chunks("doc_fail", "query", embedding_provider=failing_provider)
