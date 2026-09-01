"""Tests for POST /api/documents/{document_id}/analyze (Phase 2)."""

from __future__ import annotations

import pytest

import api.analysis as analysis_api_module
from ai.base import (
    AIAuthenticationError,
    AIConfigurationError,
    AIConnectionError,
    AIModelUnavailableError,
    AIRateLimitError,
    AITimeoutError,
)
from tests.fakes import (
    INVALID_JSON_RESPONSE,
    MALFORMED_SCHEMA_JSON,
    VALID_ANALYSIS_JSON,
    VALID_ANALYSIS_JSON_WITH_FAKE_LOCATION,
    FakeAIClient,
)


def _patch_ai_client(monkeypatch, fake_client: FakeAIClient) -> None:
    monkeypatch.setattr(analysis_api_module, "get_ai_client", lambda: fake_client)


# ---------------------------------------------------------------------------
# 1. Successful analysis using a mocked AI client
# ---------------------------------------------------------------------------
def test_successful_analysis(client, monkeypatch, uploaded_txt_document_id):
    fake_client = FakeAIClient(response_text=VALID_ANALYSIS_JSON)
    _patch_ai_client(monkeypatch, fake_client)

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/analyze")

    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == uploaded_txt_document_id
    assert body["status"] == "completed"
    assert len(body["risks"]) == 1
    assert body["risks"][0]["severity"] == "high"
    assert len(body["assumptions"]) == 1
    assert len(body["biases"]) == 1
    assert len(body["missing_perspectives"]) == 1
    assert len(body["unanswered_questions"]) == 1
    assert len(body["recommendations"]) == 1
    assert body["metadata"]["analyzed_content_items"] == 1
    assert "model" in body["metadata"]
    # The fake client was actually called with a prompt containing our content.
    assert len(fake_client.calls) == 1
    _, user_prompt = fake_client.calls[0]
    assert "Hello Blind Spot AI" in user_prompt


# ---------------------------------------------------------------------------
# 2. Document not found
# ---------------------------------------------------------------------------
def test_analyze_nonexistent_document_returns_404(client, monkeypatch):
    fake_client = FakeAIClient(response_text=VALID_ANALYSIS_JSON)
    _patch_ai_client(monkeypatch, fake_client)

    response = client.post("/api/documents/doc_does_not_exist/analyze")

    assert response.status_code == 404
    assert fake_client.calls == []  # Never should have called the AI.


# ---------------------------------------------------------------------------
# 3. Image pending multimodal analysis
# ---------------------------------------------------------------------------
def test_analyze_image_pending_multimodal_rejected(
    client, monkeypatch, uploaded_png_document_id
):
    fake_client = FakeAIClient(response_text=VALID_ANALYSIS_JSON)
    _patch_ai_client(monkeypatch, fake_client)

    response = client.post(f"/api/documents/{uploaded_png_document_id}/analyze")

    assert response.status_code == 400
    detail = response.json()["detail"].lower()
    assert "multimodal" in detail or "image" in detail
    assert fake_client.calls == []


# ---------------------------------------------------------------------------
# 4. AI client connection failure
# ---------------------------------------------------------------------------
def test_analyze_groq_connection_failure(
    client, monkeypatch, uploaded_txt_document_id
):
    fake_client = FakeAIClient(
        error=AIConnectionError("Could not connect to Groq.")
    )
    _patch_ai_client(monkeypatch, fake_client)

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/analyze")

    assert response.status_code == 502
    assert "groq" in response.json()["detail"].lower()


def test_analyze_groq_timeout(client, monkeypatch, uploaded_txt_document_id):
    fake_client = FakeAIClient(error=AITimeoutError("Groq did not respond in time."))
    _patch_ai_client(monkeypatch, fake_client)

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/analyze")

    assert response.status_code == 504


def test_analyze_model_unavailable(client, monkeypatch, uploaded_txt_document_id):
    fake_client = FakeAIClient(
        error=AIModelUnavailableError("Model 'openai/gpt-oss-120b' is not available.")
    )
    _patch_ai_client(monkeypatch, fake_client)

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/analyze")

    assert response.status_code == 502
    assert "model" in response.json()["detail"].lower()


def test_analyze_missing_api_key_returns_500(
    client, monkeypatch, uploaded_txt_document_id
):
    fake_client = FakeAIClient(
        error=AIConfigurationError("GROQ_API_KEY is not set.")
    )
    _patch_ai_client(monkeypatch, fake_client)

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/analyze")

    assert response.status_code == 500
    assert "groq_api_key" in response.json()["detail"].lower()


def test_analyze_invalid_api_key_returns_502(
    client, monkeypatch, uploaded_txt_document_id
):
    fake_client = FakeAIClient(
        error=AIAuthenticationError("Groq rejected the request due to an invalid API key.")
    )
    _patch_ai_client(monkeypatch, fake_client)

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/analyze")

    assert response.status_code == 502


def test_analyze_rate_limit_returns_429(
    client, monkeypatch, uploaded_txt_document_id
):
    fake_client = FakeAIClient(
        error=AIRateLimitError("The Groq API rate limit was reached.")
    )
    _patch_ai_client(monkeypatch, fake_client)

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/analyze")

    assert response.status_code == 429
    assert "rate limit" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 5. Invalid JSON from the model
# ---------------------------------------------------------------------------
def test_analyze_invalid_json_response(client, monkeypatch, uploaded_txt_document_id):
    fake_client = FakeAIClient(response_text=INVALID_JSON_RESPONSE)
    _patch_ai_client(monkeypatch, fake_client)

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/analyze")

    assert response.status_code == 422
    assert "detail" in response.json()


# ---------------------------------------------------------------------------
# 6. Schema validation
# ---------------------------------------------------------------------------
def test_analyze_response_failing_schema_validation(
    client, monkeypatch, uploaded_txt_document_id
):
    fake_client = FakeAIClient(response_text=MALFORMED_SCHEMA_JSON)
    _patch_ai_client(monkeypatch, fake_client)

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/analyze")

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 7. Evidence / source location handling
# ---------------------------------------------------------------------------
def test_fabricated_source_location_is_filtered_out(
    client, monkeypatch, uploaded_txt_document_id
):
    """The document only has one content block (location=1). A model response
    claiming a finding also comes from location 999 should have that bogus
    location silently dropped rather than trusted."""
    fake_client = FakeAIClient(response_text=VALID_ANALYSIS_JSON_WITH_FAKE_LOCATION)
    _patch_ai_client(monkeypatch, fake_client)

    response = client.post(f"/api/documents/{uploaded_txt_document_id}/analyze")

    assert response.status_code == 200
    body = response.json()
    assert body["risks"][0]["source_locations"] == [1]


# ---------------------------------------------------------------------------
# 8. Large document limit behavior
# ---------------------------------------------------------------------------
def test_document_exceeding_analysis_limit_returns_413(
    client, monkeypatch, sample_txt_bytes
):
    import services.document_service as document_service_module

    monkeypatch.setattr(document_service_module.config, "MAX_ANALYSIS_CONTENT_CHARS", 5)

    fake_client = FakeAIClient(response_text=VALID_ANALYSIS_JSON)
    _patch_ai_client(monkeypatch, fake_client)

    upload_response = client.post(
        "/api/documents/upload",
        files={"file": ("pitch.txt", sample_txt_bytes, "text/plain")},
    )
    document_id = upload_response.json()["document_id"]

    response = client.post(f"/api/documents/{document_id}/analyze")

    assert response.status_code == 413
    assert fake_client.calls == []
