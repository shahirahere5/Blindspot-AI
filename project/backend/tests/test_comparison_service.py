"""Phase 8 deterministic and grounded semantic comparison tests."""

from __future__ import annotations

import json

import pytest

from ai.base import AIClient
from ai.base import AIRateLimitError, AITimeoutError
from services.comparison_service import build_structural_diff
from storage.version_store import VersionRelationshipError


class StubClient(AIClient):
    def __init__(self) -> None:
        self.calls = 0
        self.prompt = ""

    @property
    def model_name(self) -> str:
        return "comparison-test-model"

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        self.prompt = user_prompt
        return json.dumps({
            "summary": "The plan improved.",
            "overall_change_assessment": "A material revision.",
            "new_risks": [{
                "title": "New risk", "description": "New exposure", "old_evidence": "",
                "new_evidence": "New risk text", "old_source_locations": [999], "new_source_locations": [1, 999]
            }],
            "resolved_risks": [], "persistent_risks": [],
            "recommendation_progress": [{
                "title": "Validate", "description": "Partly done", "progress_status": "partially_addressed",
                "old_evidence": "Validate", "new_evidence": "Pilot", "old_source_locations": [1], "new_source_locations": [1]
            }]
        })


class FailingClient(StubClient):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        raise self.error


class MalformedClient(StubClient):
    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        return "not-json"


def _upload(client, name, text):
    response = client.post("/api/documents/upload", files={"file": (name, text.encode(), "text/plain")})
    assert response.status_code == 200
    return response.json()["document_id"]


def _version(client, parent, name, text):
    response = client.post(f"/api/documents/{parent}/versions", files={"file": (name, text.encode(), "text/plain")})
    assert response.status_code == 200
    return response.json()["document_id"]


def test_structural_diff_runs_without_ai(client):
    from services.document_service import get_document_or_raise
    old_id = _upload(client, "old.txt", "Alpha")
    new_id = _version(client, old_id, "new.txt", "Alpha\nBeta")
    diff = build_structural_diff(get_document_or_raise(old_id), get_document_or_raise(new_id))
    assert diff.added_blocks == 1
    assert diff.removed_blocks == 1
    assert diff.added_snippets == ["Alpha Beta"]


@pytest.mark.asyncio
async def test_comparison_labels_versions_filters_sources_and_uses_cache(client):
    import services.comparison_service as service
    old_id = _upload(client, "old.txt", "Validate demand before launch.")
    new_id = _version(client, old_id, "new.txt", "Pilot completed. New risk text.")
    ai = StubClient()
    report = await service.compare_versions(old_id, new_id, ai, store=service.version_store)
    assert "[OLD VERSION | TEXT 1]" in ai.prompt
    assert "[NEW VERSION | TEXT 1]" in ai.prompt
    assert report.new_risks[0].old_source_locations == []
    assert report.new_risks[0].new_source_locations == [1]
    assert report.metadata["cache_hit"] is False
    cached = await service.compare_versions(old_id, new_id, ai, store=service.version_store)
    assert ai.calls == 1
    assert cached.metadata["cache_hit"] is True


@pytest.mark.asyncio
async def test_normalized_multimodal_evidence_participates(client):
    import services.comparison_service as service
    from schemas.document import ContentBlock, ContentBlockType
    from services.document_service import get_document_or_raise

    old_id = _upload(client, "old.txt", "Old chart description")
    new_id = _version(client, old_id, "new.txt", "New chart description")
    new_document = get_document_or_raise(new_id)
    new_document.content = [ContentBlock(
        type=ContentBlockType.IMAGE,
        location=1,
        text="Visual summary: operating margin declined.",
        extra={"visual_analysis": True},
    )]
    from services import document_service
    document_service.document_store.save_normalized_document(new_document)
    ai = StubClient()
    await service.compare_versions(old_id, new_id, ai, store=service.version_store)
    assert "[NEW VERSION | IMAGE 1]" in ai.prompt
    assert "operating margin declined" in ai.prompt


@pytest.mark.asyncio
async def test_unrelated_document_cannot_contaminate_comparison(client):
    import services.comparison_service as service
    old_id = _upload(client, "old.txt", "Family A")
    _version(client, old_id, "new.txt", "Family A revised")
    unrelated = _upload(client, "secret.txt", "CONFIDENTIAL FAMILY C")
    with pytest.raises(VersionRelationshipError):
        await service.compare_versions(old_id, unrelated, StubClient(), store=service.version_store)


@pytest.mark.asyncio
async def test_large_comparison_retrieves_old_and_new_independently(client, monkeypatch):
    import config
    import services.comparison_service as service

    old_id = _upload(client, "old.txt", "Demand validation and customer evidence. " * 30)
    new_id = _version(client, old_id, "new.txt", "Pilot evidence and customer validation. " * 30)
    _upload(client, "unrelated.txt", "CONFIDENTIAL FAMILY C SHOULD NEVER APPEAR " * 30)
    monkeypatch.setattr(config, "MAX_COMPARISON_CONTENT_CHARS", 100)
    ai = StubClient()
    report = await service.compare_versions(old_id, new_id, ai, store=service.version_store)
    assert report.metadata["rag_enabled"] is True
    assert "OLD VERSION" in ai.prompt and "NEW VERSION" in ai.prompt
    assert "CONFIDENTIAL FAMILY C" not in ai.prompt
    from services import retrieval_service
    indexed_old = retrieval_service.vector_store._load_raw(old_id)
    indexed_new = retrieval_service.vector_store._load_raw(new_id)
    assert indexed_old["chunks"][0]["chunk"]["version_group_id"] == report.version_group_id
    assert indexed_old["chunks"][0]["chunk"]["version_number"] == 1
    assert indexed_new["chunks"][0]["chunk"]["version_number"] == 2


def test_comparison_api_returns_structured_report(client, monkeypatch):
    import api.comparison as comparison_api

    old_id = _upload(client, "old.txt", "Validate demand.")
    new_id = _version(client, old_id, "new.txt", "Demand validated with a pilot.")
    ai = StubClient()
    monkeypatch.setattr(comparison_api, "get_ai_client", lambda: ai)
    response = client.post(
        "/api/documents/compare",
        json={"old_document_id": old_id, "new_document_id": new_id},
    )
    assert response.status_code == 200
    assert response.json()["old_document_id"] == old_id
    assert response.json()["new_document_id"] == new_id
    assert response.json()["new_risks"][0]["new_source_locations"] == [1]


def test_comparison_api_rejects_cross_family_pair_before_ai(client, monkeypatch):
    import api.comparison as comparison_api

    first = _upload(client, "a.txt", "Family A")
    second = _upload(client, "b.txt", "Family B")
    ai = StubClient()
    monkeypatch.setattr(comparison_api, "get_ai_client", lambda: ai)
    response = client.post(
        "/api/documents/compare",
        json={"old_document_id": first, "new_document_id": second},
    )
    assert response.status_code == 400
    assert ai.calls == 0


@pytest.mark.parametrize(
    ("error", "status"),
    [(AITimeoutError("private timeout detail"), 504), (AIRateLimitError("private limit detail"), 429)],
)
def test_comparison_api_safely_maps_provider_failures(client, monkeypatch, error, status):
    import api.comparison as comparison_api

    old_id = _upload(client, "old.txt", "Old")
    new_id = _version(client, old_id, "new.txt", "New")
    monkeypatch.setattr(comparison_api, "get_ai_client", lambda: FailingClient(error))
    response = client.post("/api/documents/compare", json={"old_document_id": old_id, "new_document_id": new_id})
    assert response.status_code == status
    assert "private" not in response.json()["detail"]


def test_comparison_api_rejects_malformed_ai_output(client, monkeypatch):
    import api.comparison as comparison_api

    old_id = _upload(client, "old.txt", "Old")
    new_id = _version(client, old_id, "new.txt", "New")
    monkeypatch.setattr(comparison_api, "get_ai_client", MalformedClient)
    response = client.post("/api/documents/compare", json={"old_document_id": old_id, "new_document_id": new_id})
    assert response.status_code == 422
    assert "parseable comparison" in response.json()["detail"]
