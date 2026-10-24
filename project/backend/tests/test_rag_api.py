"""Tests for POST /api/documents/{id}/index and /retrieve (Phase 4)."""

from __future__ import annotations

import api.rag as rag_api_module
from ai.embeddings.base import EmbeddingGenerationError
from tests.fakes import FakeEmbeddingProvider


def _patch_embedding_provider(monkeypatch, provider):
    monkeypatch.setattr(rag_api_module, "get_embedding_provider", lambda: provider)
    import services.retrieval_service as retrieval_service_module

    monkeypatch.setattr(
        retrieval_service_module, "get_embedding_provider", lambda: provider
    )


def test_index_document_success(client, monkeypatch, uploaded_txt_document_id):
    provider = FakeEmbeddingProvider(dimension=4)
    _patch_embedding_provider(monkeypatch, provider)

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/index")

    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == uploaded_txt_document_id
    assert body["chunks_indexed"] >= 1
    assert body["embedding_provider"] == "fake"
    assert body["embedding_dimension"] == 4


def test_index_nonexistent_document_returns_404(client, monkeypatch):
    _patch_embedding_provider(monkeypatch, FakeEmbeddingProvider())

    response = client.post("/api/documents/doc_does_not_exist/index")

    assert response.status_code == 404


def test_index_image_pending_multimodal_returns_400(
    client, monkeypatch, uploaded_png_document_id
):
    _patch_embedding_provider(monkeypatch, FakeEmbeddingProvider())

    response = client.post(f"/api/documents/{uploaded_png_document_id}/index")

    assert response.status_code == 400


def test_index_embedding_failure_returns_500(
    client, monkeypatch, uploaded_txt_document_id
):
    _patch_embedding_provider(monkeypatch, FakeEmbeddingProvider(fail=True))

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/index")

    assert response.status_code == 500


def test_retrieve_auto_indexes_and_returns_chunks(
    client, monkeypatch, uploaded_txt_document_id
):
    provider = FakeEmbeddingProvider(dimension=4, default_vector=[1.0, 0.0, 0.0, 0.0])
    _patch_embedding_provider(monkeypatch, provider)

    response = client.post(
        f"/api/documents/{uploaded_txt_document_id}/retrieve",
        json={"query": "what are the risks?", "top_k": 3},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == uploaded_txt_document_id
    assert body["query"] == "what are the risks?"
    assert len(body["results"]) >= 1
    result = body["results"][0]
    assert "text" in result
    assert "score" in result
    assert result["metadata"]["source_type"] in {"page", "text", "paragraph", "table", "slide"}
    assert isinstance(result["metadata"]["source_location"], int)


def test_retrieve_nonexistent_document_returns_404(client, monkeypatch):
    _patch_embedding_provider(monkeypatch, FakeEmbeddingProvider())

    response = client.post(
        "/api/documents/doc_does_not_exist/retrieve", json={"query": "test"}
    )

    assert response.status_code == 404


def test_retrieve_requires_nonempty_query(client, monkeypatch, uploaded_txt_document_id):
    _patch_embedding_provider(monkeypatch, FakeEmbeddingProvider())

    response = client.post(
        f"/api/documents/{uploaded_txt_document_id}/retrieve", json={"query": ""}
    )

    assert response.status_code == 422  # FastAPI/Pydantic request validation


def test_retrieve_embedding_failure_returns_500(
    client, monkeypatch, uploaded_txt_document_id
):
    _patch_embedding_provider(monkeypatch, FakeEmbeddingProvider(fail=True))

    response = client.post(
        f"/api/documents/{uploaded_txt_document_id}/retrieve",
        json={"query": "test"},
    )

    assert response.status_code == 500
