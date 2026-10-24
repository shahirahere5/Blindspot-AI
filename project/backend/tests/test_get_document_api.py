"""Tests for GET /api/documents/{document_id}."""

from __future__ import annotations


def test_get_existing_document(client, sample_txt_bytes):
    upload_response = client.post(
        "/api/documents/upload",
        files={"file": ("notes.txt", sample_txt_bytes, "text/plain")},
    )
    document_id = upload_response.json()["document_id"]

    get_response = client.get(f"/api/documents/{document_id}")
    assert get_response.status_code == 200

    body = get_response.json()
    assert body["document_id"] == document_id
    assert body["file_type"] == "txt"
    assert len(body["content"]) == 1
    assert "Hello Blind Spot AI" in body["content"][0]["text"]


def test_get_nonexistent_document_returns_404(client):
    response = client.get("/api/documents/doc_does_not_exist")
    assert response.status_code == 404
    body = response.json()
    assert "detail" in body


def test_document_id_path_traversal_is_rejected(client):
    response = client.get("/api/documents/doc_%5C..%5Coutside")

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_document_id"


def test_unsafe_document_id_is_rejected_across_document_operations(client):
    unsafe_id = "doc_%5C..%5Coutside"
    responses = [
        client.post(f"/api/documents/{unsafe_id}/analyze"),
        client.post(f"/api/documents/{unsafe_id}/debate"),
        client.post(f"/api/documents/{unsafe_id}/index"),
        client.post(
            f"/api/documents/{unsafe_id}/retrieve",
            json={"query": "risk", "top_k": 1},
        ),
    ]

    assert all(response.status_code == 400 for response in responses)
    assert all(
        response.json()["error"] == "invalid_document_id" for response in responses
    )
