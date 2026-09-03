"""Unit tests for storage/vector_store.py."""

from __future__ import annotations

import pytest

from schemas.rag import DocumentChunk
from storage.vector_store import SimpleVectorStore, VectorStoreError


def _chunk(document_id: str, index: int, text: str, location: int = 1) -> DocumentChunk:
    return DocumentChunk(
        document_id=document_id,
        chunk_index=index,
        text=text,
        source_type="page",
        source_location=location,
    )


def test_indexing_and_search_returns_expected_chunk(tmp_path):
    store = SimpleVectorStore(tmp_path)
    chunks = [_chunk("doc_a", 0, "hello"), _chunk("doc_a", 1, "world")]
    vectors = [[1.0, 0.0], [0.0, 1.0]]

    store.index_document("doc_a", chunks, vectors, "fake", 2)
    results = store.search("doc_a", [1.0, 0.0], top_k=1)

    assert len(results) == 1
    assert results[0].chunk.text == "hello"
    assert results[0].score == pytest.approx(1.0)


def test_search_ranks_by_similarity_descending(tmp_path):
    store = SimpleVectorStore(tmp_path)
    chunks = [_chunk("doc_a", 0, "a"), _chunk("doc_a", 1, "b"), _chunk("doc_a", 2, "c")]
    vectors = [[1.0, 0.0], [0.7, 0.7], [0.0, 1.0]]

    store.index_document("doc_a", chunks, vectors, "fake", 2)
    results = store.search("doc_a", [1.0, 0.0], top_k=3)

    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)
    assert results[0].chunk.text == "a"
    assert results[-1].chunk.text == "c"


def test_top_k_limits_number_of_results(tmp_path):
    store = SimpleVectorStore(tmp_path)
    chunks = [_chunk("doc_a", i, f"chunk {i}") for i in range(5)]
    vectors = [[float(i), 1.0] for i in range(5)]

    store.index_document("doc_a", chunks, vectors, "fake", 2)
    results = store.search("doc_a", [2.0, 1.0], top_k=2)

    assert len(results) == 2


def test_persistence_across_store_instances(tmp_path):
    store1 = SimpleVectorStore(tmp_path)
    chunks = [_chunk("doc_a", 0, "persisted text")]
    store1.index_document("doc_a", chunks, [[1.0, 0.0]], "fake", 2)

    # A brand new instance pointing at the same directory should see it.
    store2 = SimpleVectorStore(tmp_path)

    assert store2.is_indexed("doc_a")
    results = store2.search("doc_a", [1.0, 0.0], top_k=1)
    assert results[0].chunk.text == "persisted text"


def test_document_level_isolation(tmp_path):
    store = SimpleVectorStore(tmp_path)
    store.index_document(
        "doc_a", [_chunk("doc_a", 0, "doc a content")], [[1.0, 0.0]], "fake", 2
    )
    store.index_document(
        "doc_b", [_chunk("doc_b", 0, "doc b content")], [[1.0, 0.0]], "fake", 2
    )

    results_a = store.search("doc_a", [1.0, 0.0], top_k=5)
    results_b = store.search("doc_b", [1.0, 0.0], top_k=5)

    assert len(results_a) == 1 and results_a[0].chunk.text == "doc a content"
    assert len(results_b) == 1 and results_b[0].chunk.text == "doc b content"
    assert results_a[0].chunk.document_id == "doc_a"
    assert results_b[0].chunk.document_id == "doc_b"


def test_search_on_unindexed_document_returns_empty_list(tmp_path):
    store = SimpleVectorStore(tmp_path)

    results = store.search("never_indexed", [1.0, 0.0], top_k=5)

    assert results == []


def test_is_indexed_false_before_indexing(tmp_path):
    store = SimpleVectorStore(tmp_path)

    assert store.is_indexed("doc_a") is False


def test_delete_document_removes_index(tmp_path):
    store = SimpleVectorStore(tmp_path)
    store.index_document("doc_a", [_chunk("doc_a", 0, "x")], [[1.0]], "fake", 1)

    store.delete_document("doc_a")

    assert store.is_indexed("doc_a") is False
    assert store.search("doc_a", [1.0], top_k=1) == []


def test_delete_nonexistent_document_is_a_noop(tmp_path):
    store = SimpleVectorStore(tmp_path)

    store.delete_document("never_existed")  # should not raise


def test_reindexing_replaces_previous_chunks(tmp_path):
    store = SimpleVectorStore(tmp_path)
    store.index_document(
        "doc_a", [_chunk("doc_a", 0, "old content")], [[1.0, 0.0]], "fake", 2
    )
    store.index_document(
        "doc_a", [_chunk("doc_a", 0, "new content")], [[1.0, 0.0]], "fake", 2
    )

    results = store.search("doc_a", [1.0, 0.0], top_k=5)

    assert len(results) == 1
    assert results[0].chunk.text == "new content"


def test_mismatched_chunks_and_vectors_length_raises(tmp_path):
    store = SimpleVectorStore(tmp_path)
    with pytest.raises(VectorStoreError):
        store.index_document("doc_a", [_chunk("doc_a", 0, "x")], [], "fake", 1)


def test_query_dimension_mismatch_raises(tmp_path):
    store = SimpleVectorStore(tmp_path)
    store.index_document("doc_a", [_chunk("doc_a", 0, "x")], [[1.0, 0.0]], "fake", 2)

    with pytest.raises(VectorStoreError):
        store.search("doc_a", [1.0, 0.0, 0.0], top_k=1)


def test_chunk_count(tmp_path):
    store = SimpleVectorStore(tmp_path)
    assert store.chunk_count("doc_a") == 0

    store.index_document(
        "doc_a",
        [_chunk("doc_a", 0, "a"), _chunk("doc_a", 1, "b")],
        [[1.0, 0.0], [0.0, 1.0]],
        "fake",
        2,
    )

    assert store.chunk_count("doc_a") == 2
