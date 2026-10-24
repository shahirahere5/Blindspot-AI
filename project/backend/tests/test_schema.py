"""Verify that every processed document follows the normalized structure."""

from __future__ import annotations

import pytest

from schemas.document import NormalizedDocument


@pytest.mark.parametrize(
    "filename,fixture_name,content_type",
    [
        ("notes.txt", "sample_txt_bytes", "text/plain"),
        ("pitch.pdf", "sample_pdf_bytes", "application/pdf"),
        (
            "proposal.docx",
            "sample_docx_bytes",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        (
            "deck.pptx",
            "sample_pptx_bytes",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ),
        ("photo.png", "sample_png_bytes", "image/png"),
    ],
)
def test_uploaded_document_matches_normalized_schema(
    client, request, filename, fixture_name, content_type
):
    file_bytes = request.getfixturevalue(fixture_name)

    upload_response = client.post(
        "/api/documents/upload",
        files={"file": (filename, file_bytes, content_type)},
    )
    document_id = upload_response.json()["document_id"]

    get_response = client.get(f"/api/documents/{document_id}")
    payload = get_response.json()

    # Will raise a validation error if the shape doesn't match.
    document = NormalizedDocument.model_validate(payload)

    assert document.document_id == document_id
    assert isinstance(document.content, list)
    assert isinstance(document.metadata, dict)
