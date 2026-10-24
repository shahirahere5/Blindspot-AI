"""Tests for POST /api/documents/upload across all supported formats."""

from __future__ import annotations


def _upload(client, filename: str, content: bytes, content_type: str):
    return client.post(
        "/api/documents/upload",
        files={"file": (filename, content, content_type)},
    )


def test_upload_txt(client, sample_txt_bytes):
    response = _upload(client, "notes.txt", sample_txt_bytes, "text/plain")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["file_type"] == "txt"
    assert body["status"] == "processed"
    assert body["document_id"].startswith("doc_")


def test_upload_pdf(client, sample_pdf_bytes):
    response = _upload(client, "pitch.pdf", sample_pdf_bytes, "application/pdf")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["file_type"] == "pdf"
    assert body["status"] == "processed"
    assert body["metadata"]["page_count"] == 3


def test_upload_scanned_pdf_requires_multimodal(client, sample_scanned_pdf_bytes):
    response = _upload(client, "scanned.pdf", sample_scanned_pdf_bytes, "application/pdf")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "requires_multimodal_processing"


def test_upload_docx(client, sample_docx_bytes):
    response = _upload(
        client,
        "proposal.docx",
        sample_docx_bytes,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["file_type"] == "docx"
    assert body["metadata"]["paragraph_count"] >= 2
    assert body["metadata"]["table_count"] == 1


def test_upload_pptx(client, sample_pptx_bytes):
    response = _upload(
        client,
        "deck.pptx",
        sample_pptx_bytes,
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["file_type"] == "pptx"
    assert body["metadata"]["slide_count"] == 2


def test_upload_png(client, sample_png_bytes):
    response = _upload(client, "screenshot.png", sample_png_bytes, "image/png")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["file_type"] == "image"
    assert body["status"] == "pending_multimodal_analysis"
    assert body["metadata"]["width"] == 1920
    assert body["metadata"]["height"] == 1080


def test_corrupt_image_is_rejected_and_raw_upload_is_removed(client):
    response = _upload(client, "broken.png", b"not a real image", "image/png")

    assert response.status_code == 422
    assert "process" in response.json()["detail"].lower()
    import api.documents as documents_module

    assert list(documents_module.document_store.uploads_dir.iterdir()) == []


def test_document_id_is_not_the_filename(client, sample_txt_bytes):
    response = _upload(client, "my_secret_plan.txt", sample_txt_bytes, "text/plain")
    body = response.json()
    assert "my_secret_plan" not in body["document_id"]


def test_failed_processing_removes_orphaned_raw_upload(
    client, monkeypatch, sample_txt_bytes
):
    import api.documents as documents_module
    from processing.exceptions import DocumentProcessingError

    class BrokenProcessor:
        def process(self, **_kwargs):
            raise DocumentProcessingError("corrupt fixture")

    monkeypatch.setattr(documents_module, "get_processor", lambda _type: BrokenProcessor())

    response = _upload(client, "broken.txt", sample_txt_bytes, "text/plain")

    assert response.status_code == 422
    assert list(documents_module.document_store.uploads_dir.iterdir()) == []
