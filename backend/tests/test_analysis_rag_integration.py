"""Integration tests: RAG-enabled /analyze (Phase 4) and non-regression of
the default (RAG-disabled) Phase 2 behavior."""

from __future__ import annotations

import json

import config
import api.analysis as analysis_api_module
import services.analysis_service as analysis_service_module
from tests.fakes import FakeAIClient, FakeEmbeddingProvider


VALID_ANALYSIS_JSON = """{
  "risks": [
    {
      "title": "Example risk",
      "description": "An example risk grounded in retrieved context.",
      "severity": "high",
      "evidence": "Hello Blind Spot AI.",
      "source_locations": [1],
      "recommendation": "Address this risk."
    }
  ],
  "assumptions": [],
  "biases": [],
  "missing_perspectives": [],
  "unanswered_questions": [],
  "recommendations": []
}"""


def _patch_ai_client(monkeypatch, fake_client):
    monkeypatch.setattr(analysis_api_module, "get_ai_client", lambda: fake_client)


def _patch_embedding_provider(monkeypatch, provider):
    import services.retrieval_service as retrieval_service_module

    monkeypatch.setattr(
        retrieval_service_module, "get_embedding_provider", lambda: provider
    )


def test_rag_disabled_by_default():
    assert config.RAG_ENABLED is False


def test_analysis_without_rag_never_touches_embeddings(
    client, monkeypatch, uploaded_txt_document_id
):
    """Regression guard: the default (RAG_ENABLED=False) path must not call
    the embedding layer at all -- Phase 2 behavior stays untouched."""

    def _explode():
        raise AssertionError("Embedding provider should never be called when RAG is disabled.")

    monkeypatch.setattr(analysis_service_module.rag_service, "ensure_document_indexed", lambda *a, **k: _explode())
    _patch_ai_client(monkeypatch, FakeAIClient(response_text=VALID_ANALYSIS_JSON))

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/analyze")

    assert response.status_code == 200


def test_analysis_with_rag_enabled_returns_grounded_report(
    client, monkeypatch, uploaded_txt_document_id
):
    monkeypatch.setattr(config, "RAG_ENABLED", True)
    _patch_embedding_provider(monkeypatch, FakeEmbeddingProvider(dimension=4))
    _patch_ai_client(monkeypatch, FakeAIClient(response_text=VALID_ANALYSIS_JSON))

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/analyze")

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["rag_enabled"] is True
    assert body["metadata"]["analyzed_content_items"] >= 1
    assert len(body["risks"]) == 1


def test_analysis_with_rag_enabled_auto_indexes_document(
    client, monkeypatch, uploaded_txt_document_id
):
    monkeypatch.setattr(config, "RAG_ENABLED", True)
    provider = FakeEmbeddingProvider(dimension=4)
    _patch_embedding_provider(monkeypatch, provider)
    _patch_ai_client(monkeypatch, FakeAIClient(response_text=VALID_ANALYSIS_JSON))

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/analyze")

    assert response.status_code == 200
    assert provider.calls  # embedding was actually invoked (auto-indexing happened)


def test_analysis_with_rag_enabled_filters_fabricated_locations(
    client, monkeypatch, uploaded_txt_document_id
):
    monkeypatch.setattr(config, "RAG_ENABLED", True)
    _patch_embedding_provider(monkeypatch, FakeEmbeddingProvider(dimension=4))

    fabricated_response = VALID_ANALYSIS_JSON.replace(
        '"source_locations": [1]', '"source_locations": [1, 999]'
    )
    _patch_ai_client(monkeypatch, FakeAIClient(response_text=fabricated_response))

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/analyze")

    assert response.status_code == 200
    body = response.json()
    assert body["risks"][0]["source_locations"] == [1]


def test_analysis_clears_sources_when_no_location_is_valid():
    from schemas.analysis import AnalysisReport
    from services.analysis_service import _filter_source_locations

    payload = json.loads(VALID_ANALYSIS_JSON)
    payload["document_id"] = "doc_a"
    report = AnalysisReport.model_validate(payload)
    _filter_source_locations(report, set())

    assert report.risks[0].source_locations == []


def test_analysis_with_rag_enabled_missing_document_returns_404(client, monkeypatch):
    monkeypatch.setattr(config, "RAG_ENABLED", True)
    _patch_embedding_provider(monkeypatch, FakeEmbeddingProvider(dimension=4))
    _patch_ai_client(monkeypatch, FakeAIClient(response_text=VALID_ANALYSIS_JSON))

    response = client.post("/api/documents/doc_does_not_exist/analyze")

    assert response.status_code == 404


def test_analysis_with_rag_enabled_embedding_failure_returns_500(
    client, monkeypatch, uploaded_txt_document_id
):
    monkeypatch.setattr(config, "RAG_ENABLED", True)
    _patch_embedding_provider(monkeypatch, FakeEmbeddingProvider(fail=True))
    _patch_ai_client(monkeypatch, FakeAIClient(response_text=VALID_ANALYSIS_JSON))

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/analyze")

    assert response.status_code == 500
