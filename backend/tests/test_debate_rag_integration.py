"""Integration tests: RAG-enabled /debate (Phase 4) and non-regression of
the default (RAG-disabled) Phase 3 behavior."""

from __future__ import annotations

import config
import api.debate as debate_api_module
import services.debate_service as debate_service_module
from tests.fakes import (
    ALL_VALID_AGENT_RESPONSES,
    VALID_MODERATOR_JSON,
    DebateFakeAIClient,
    FakeEmbeddingProvider,
)


def _patch_ai_client(monkeypatch, fake_client):
    monkeypatch.setattr(debate_api_module, "get_ai_client", lambda: fake_client)


def _patch_embedding_provider(monkeypatch, provider):
    import services.retrieval_service as retrieval_service_module

    monkeypatch.setattr(
        retrieval_service_module, "get_embedding_provider", lambda: provider
    )


def _full_success_client() -> DebateFakeAIClient:
    return DebateFakeAIClient(
        responses={**ALL_VALID_AGENT_RESPONSES, "moderator": VALID_MODERATOR_JSON}
    )


def test_debate_without_rag_never_touches_embeddings(
    client, monkeypatch, uploaded_txt_document_id
):
    """Regression guard: the default (RAG_ENABLED=False) path must not call
    the embedding layer at all -- Phase 3 behavior stays untouched."""

    def _explode(*args, **kwargs):
        raise AssertionError("Embedding provider should never be called when RAG is disabled.")

    monkeypatch.setattr(
        debate_service_module.rag_service, "ensure_document_indexed", _explode
    )
    _patch_ai_client(monkeypatch, _full_success_client())

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/debate")

    assert response.status_code == 200
    assert len(response.json()["agent_analyses"]) == 6


def test_debate_with_rag_enabled_returns_full_report(
    client, monkeypatch, uploaded_txt_document_id
):
    monkeypatch.setattr(config, "RAG_ENABLED", True)
    _patch_embedding_provider(monkeypatch, FakeEmbeddingProvider(dimension=4))
    _patch_ai_client(monkeypatch, _full_success_client())

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/debate")

    assert response.status_code == 200
    body = response.json()
    assert len(body["agent_analyses"]) == 6
    assert all(a["status"] == "succeeded" for a in body["agent_analyses"])
    assert body["metadata"]["rag_enabled"] is True
    assert body["overall_assessment"]


def test_debate_with_rag_enabled_auto_indexes_once_per_debate(
    client, monkeypatch, uploaded_txt_document_id
):
    monkeypatch.setattr(config, "RAG_ENABLED", True)
    provider = FakeEmbeddingProvider(dimension=4)
    _patch_embedding_provider(monkeypatch, provider)
    _patch_ai_client(monkeypatch, _full_success_client())

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/debate")

    assert response.status_code == 200
    # Indexing embeds the document's chunks once; each of the 6 agents plus
    # the moderator then embeds its own query -- so at least 7 calls total.
    assert len(provider.calls) >= 7


def test_debate_with_rag_enabled_one_agent_still_recorded_on_ai_failure(
    client, monkeypatch, uploaded_txt_document_id
):
    monkeypatch.setattr(config, "RAG_ENABLED", True)
    _patch_embedding_provider(monkeypatch, FakeEmbeddingProvider(dimension=4))

    from ai.base import AIConnectionError

    responses = {**ALL_VALID_AGENT_RESPONSES, "moderator": VALID_MODERATOR_JSON}
    del responses["security"]
    fake_client = DebateFakeAIClient(
        responses=responses,
        errors={"security": AIConnectionError("Could not connect to Groq.")},
    )
    _patch_ai_client(monkeypatch, fake_client)

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/debate")

    assert response.status_code == 200
    body = response.json()
    security = next(a for a in body["agent_analyses"] if a["agent"] == "security")
    assert security["status"] == "failed"
    assert body["metadata"]["agents_failed"] == ["security"]


def test_debate_with_rag_enabled_embedding_failure_returns_500(
    client, monkeypatch, uploaded_txt_document_id
):
    monkeypatch.setattr(config, "RAG_ENABLED", True)
    _patch_embedding_provider(monkeypatch, FakeEmbeddingProvider(fail=True))
    _patch_ai_client(monkeypatch, _full_success_client())

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/debate")

    assert response.status_code == 500


def test_debate_with_rag_enabled_missing_document_returns_404(client, monkeypatch):
    monkeypatch.setattr(config, "RAG_ENABLED", True)
    _patch_embedding_provider(monkeypatch, FakeEmbeddingProvider(dimension=4))
    _patch_ai_client(monkeypatch, _full_success_client())

    response = client.post("/api/documents/doc_does_not_exist/debate")

    assert response.status_code == 404
