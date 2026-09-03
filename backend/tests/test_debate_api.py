"""Tests for POST /api/documents/{document_id}/debate (Phase 3)."""

from __future__ import annotations

import api.debate as debate_api_module
from ai.base import (
    AIAuthenticationError,
    AIConfigurationError,
    AIConnectionError,
    AIModelUnavailableError,
    AIRateLimitError,
    AITimeoutError,
)
from tests.fakes import (
    ALL_VALID_AGENT_RESPONSES,
    INVALID_AGENT_JSON_RESPONSE,
    VALID_MODERATOR_JSON,
    DebateFakeAIClient,
)


def _patch_ai_client(monkeypatch, fake_client: DebateFakeAIClient) -> None:
    monkeypatch.setattr(debate_api_module, "get_ai_client", lambda: fake_client)


def _full_success_client() -> DebateFakeAIClient:
    return DebateFakeAIClient(
        responses={**ALL_VALID_AGENT_RESPONSES, "moderator": VALID_MODERATOR_JSON}
    )


# ---------------------------------------------------------------------------
# 1. Successful debate
# ---------------------------------------------------------------------------
def test_successful_debate(client, monkeypatch, uploaded_txt_document_id):
    fake_client = _full_success_client()
    _patch_ai_client(monkeypatch, fake_client)

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/debate")

    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == uploaded_txt_document_id
    assert body["status"] == "completed"
    assert len(body["agent_analyses"]) == 6
    assert {a["agent"] for a in body["agent_analyses"]} == {
        "optimist",
        "skeptic",
        "security",
        "financial",
        "ethics",
        "legal",
    }
    assert all(a["status"] == "succeeded" for a in body["agent_analyses"])
    assert body["metadata"]["agents_used"] == 6
    assert body["metadata"]["agents_failed"] == []
    assert len(body["final_risks"]) == 1
    assert body["overall_assessment"]
    assert len(fake_client.calls) == 7


# ---------------------------------------------------------------------------
# 2. Missing document -> 404
# ---------------------------------------------------------------------------
def test_debate_nonexistent_document_returns_404(client, monkeypatch):
    fake_client = _full_success_client()
    _patch_ai_client(monkeypatch, fake_client)

    response = client.post("/api/documents/doc_does_not_exist/debate")

    assert response.status_code == 404
    assert fake_client.calls == []


# ---------------------------------------------------------------------------
# 3. Image pending multimodal analysis -> 400 (same as Phase 2)
# ---------------------------------------------------------------------------
def test_debate_image_pending_multimodal_rejected(
    client, monkeypatch, uploaded_png_document_id
):
    fake_client = _full_success_client()
    _patch_ai_client(monkeypatch, fake_client)

    response = client.post(f"/api/documents/{uploaded_png_document_id}/debate")

    assert response.status_code == 400
    detail = response.json()["detail"].lower()
    assert "multimodal" in detail or "image" in detail
    assert fake_client.calls == []


# ---------------------------------------------------------------------------
# 4. Oversized document -> 413
# ---------------------------------------------------------------------------
def test_debate_document_exceeding_analysis_limit_returns_413(
    client, monkeypatch, sample_txt_bytes
):
    import services.document_service as document_service_module

    monkeypatch.setattr(document_service_module.config, "MAX_ANALYSIS_CONTENT_CHARS", 5)

    fake_client = _full_success_client()
    _patch_ai_client(monkeypatch, fake_client)

    upload_response = client.post(
        "/api/documents/upload",
        files={"file": ("pitch.txt", sample_txt_bytes, "text/plain")},
    )
    document_id = upload_response.json()["document_id"]

    response = client.post(f"/api/documents/{document_id}/debate")

    assert response.status_code == 413
    assert fake_client.calls == []


# ---------------------------------------------------------------------------
# 5. One agent fails -> debate still succeeds (200), failure recorded
# ---------------------------------------------------------------------------
def test_debate_one_agent_failure_still_returns_200(
    client, monkeypatch, uploaded_txt_document_id
):
    responses = {**ALL_VALID_AGENT_RESPONSES, "moderator": VALID_MODERATOR_JSON}
    del responses["security"]
    fake_client = DebateFakeAIClient(
        responses=responses,
        errors={"security": AIRateLimitError("Rate limit reached.")},
    )
    _patch_ai_client(monkeypatch, fake_client)

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/debate")

    assert response.status_code == 200
    body = response.json()
    security_analysis = next(
        a for a in body["agent_analyses"] if a["agent"] == "security"
    )
    assert security_analysis["status"] == "failed"
    assert body["metadata"]["agents_failed"] == ["security"]


# ---------------------------------------------------------------------------
# 6. All agents fail -> 502
# ---------------------------------------------------------------------------
def test_debate_all_agents_failing_returns_502(client, monkeypatch, uploaded_txt_document_id):
    error = AIConnectionError("Could not connect to Groq.")
    fake_client = DebateFakeAIClient(
        errors={
            "optimist": error,
            "skeptic": error,
            "security": error,
            "financial": error,
            "ethics": error,
            "legal": error,
        }
    )
    _patch_ai_client(monkeypatch, fake_client)

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/debate")

    assert response.status_code == 502


# ---------------------------------------------------------------------------
# 7. Moderator upstream AI failures map to the same statuses as Phase 2
# ---------------------------------------------------------------------------
def test_debate_moderator_connection_failure_returns_502(
    client, monkeypatch, uploaded_txt_document_id
):
    fake_client = DebateFakeAIClient(
        responses=ALL_VALID_AGENT_RESPONSES,
        errors={"moderator": AIConnectionError("Could not connect to Groq.")},
    )
    _patch_ai_client(monkeypatch, fake_client)

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/debate")

    assert response.status_code == 502


def test_debate_moderator_timeout_returns_504(
    client, monkeypatch, uploaded_txt_document_id
):
    fake_client = DebateFakeAIClient(
        responses=ALL_VALID_AGENT_RESPONSES,
        errors={"moderator": AITimeoutError("Groq did not respond in time.")},
    )
    _patch_ai_client(monkeypatch, fake_client)

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/debate")

    assert response.status_code == 504


def test_debate_missing_api_key_returns_500(
    client, monkeypatch, uploaded_txt_document_id
):
    fake_client = DebateFakeAIClient(
        responses=ALL_VALID_AGENT_RESPONSES,
        errors={"moderator": AIConfigurationError("GROQ_API_KEY is not set.")},
    )
    _patch_ai_client(monkeypatch, fake_client)

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/debate")

    assert response.status_code == 500


def test_debate_invalid_api_key_returns_502(
    client, monkeypatch, uploaded_txt_document_id
):
    fake_client = DebateFakeAIClient(
        responses=ALL_VALID_AGENT_RESPONSES,
        errors={
            "moderator": AIAuthenticationError(
                "Groq rejected the request due to an invalid API key."
            )
        },
    )
    _patch_ai_client(monkeypatch, fake_client)

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/debate")

    assert response.status_code == 502


def test_debate_model_unavailable_returns_502(
    client, monkeypatch, uploaded_txt_document_id
):
    fake_client = DebateFakeAIClient(
        responses=ALL_VALID_AGENT_RESPONSES,
        errors={
            "moderator": AIModelUnavailableError("Model is not available.")
        },
    )
    _patch_ai_client(monkeypatch, fake_client)

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/debate")

    assert response.status_code == 502


# ---------------------------------------------------------------------------
# 8. Malformed model responses from the moderator -> 422
# ---------------------------------------------------------------------------
def test_debate_moderator_invalid_json_returns_422(
    client, monkeypatch, uploaded_txt_document_id
):
    fake_client = DebateFakeAIClient(
        responses={
            **ALL_VALID_AGENT_RESPONSES,
            "moderator": INVALID_AGENT_JSON_RESPONSE,
        }
    )
    _patch_ai_client(monkeypatch, fake_client)

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/debate")

    assert response.status_code == 422


def test_debate_moderator_schema_validation_failure_returns_422(
    client, monkeypatch, uploaded_txt_document_id
):
    fake_client = DebateFakeAIClient(
        responses={
            **ALL_VALID_AGENT_RESPONSES,
            "moderator": '{"overall_assessment": "ok", "final_risks": "not a list"}',
        }
    )
    _patch_ai_client(monkeypatch, fake_client)

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/debate")

    assert response.status_code == 422
