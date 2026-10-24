"""Phase 8 explicit version history API tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor


def _upload(client, name: str, text: str) -> str:
    response = client.post(
        "/api/documents/upload",
        files={"file": (name, text.encode(), "text/plain")},
    )
    assert response.status_code == 200
    return response.json()["document_id"]


def _version(client, parent: str, name: str, text: str, **data):
    return client.post(
        f"/api/documents/{parent}/versions",
        files={"file": (name, text.encode(), "text/plain")},
        data=data,
    )


def test_standalone_history_is_virtual_version_one(client):
    document_id = _upload(client, "plan.txt", "Initial plan")
    body = client.get(f"/api/documents/{document_id}/versions").json()
    assert body["version_group_id"] is None
    assert [(item["document_id"], item["version_number"]) for item in body["versions"]] == [(document_id, 1)]


def test_missing_version_parent_returns_404(client):
    response = _version(client, "doc_missing", "v2.txt", "Two")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_explicit_version_upload_creates_group_and_chronological_history(client):
    first = _upload(client, "original.txt", "Original plan")
    response = _version(
        client, first, "revised.txt", "Revised plan", version_label="Board revision", notes="After review"
    )
    assert response.status_code == 200
    second = response.json()["document_id"]
    assert response.json()["version_number"] == 2
    assert response.json()["previous_document_id"] == first

    third_response = _version(client, second, "final.txt", "Final plan")
    assert third_response.status_code == 200
    history = client.get(f"/api/documents/{first}/versions").json()
    assert [item["version_number"] for item in history["versions"]] == [1, 2, 3]
    assert [item["document_id"] for item in history["versions"]] == [first, second, third_response.json()["document_id"]]
    assert history["versions"][1]["label"] == "Board revision"


def test_version_upload_does_not_infer_relationship_from_filename(client):
    first = _upload(client, "same.txt", "One")
    second = _upload(client, "same.txt", "Two")
    assert client.get(f"/api/documents/{first}/versions").json()["version_group_id"] is None
    assert client.get(f"/api/documents/{second}/versions").json()["version_group_id"] is None


def test_cannot_append_to_non_latest_version(client):
    first = _upload(client, "v1.txt", "One")
    assert _version(client, first, "v2.txt", "Two").status_code == 200
    response = _version(client, first, "branch.txt", "Branch")
    assert response.status_code == 409
    assert "latest" in response.json()["detail"].lower()


def test_concurrent_store_append_keeps_unique_sequence(client):
    from api import documents as documents_api
    from schemas.document import NormalizedDocument

    parent_id = _upload(client, "v1.txt", "One")
    parent = documents_api.document_store.load_normalized_document(parent_id)
    assert parent is not None
    children = [
        NormalizedDocument.model_validate({
            **parent.model_dump(), "document_id": f"doc_child_{index}", "filename": f"v{index}.txt"
        }) for index in range(2)
    ]

    def append(child):
        return documents_api.version_store.append(parent, child, label=None, notes=None)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = []
        errors = []
        for future in [executor.submit(append, child) for child in children]:
            try:
                results.append(future.result())
            except Exception as exc:
                errors.append(exc)
    assert len(results) == 1
    assert len(errors) == 1
    assert results[0][1].version_number == 2


def test_history_survives_store_reinstantiation(client):
    from api import documents as documents_api
    from storage.version_store import VersionStore

    first = _upload(client, "v1.txt", "One")
    second = _version(client, first, "v2.txt", "Two").json()["document_id"]
    restored = VersionStore(documents_api.version_store.groups_dir)
    document = documents_api.document_store.load_normalized_document(second)
    assert document is not None
    assert [item.version_number for item in restored.history_for(document).versions] == [1, 2]
