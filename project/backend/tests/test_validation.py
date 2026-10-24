"""Tests for upload validation: bad extensions, empty files, oversized files."""

from __future__ import annotations

import config
import pytest

from api.validation import ValidationError, read_and_validate_upload


def test_unsupported_extension_rejected(client, sample_txt_bytes):
    response = client.post(
        "/api/documents/upload",
        files={"file": ("malware.exe", sample_txt_bytes, "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "Unsupported file extension" in response.json()["detail"]


def test_empty_file_rejected(client):
    response = client.post(
        "/api/documents/upload",
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_oversized_file_rejected(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_FILE_SIZE_BYTES", 10)
    import api.validation as validation_module

    monkeypatch.setattr(validation_module, "MAX_FILE_SIZE_BYTES", 10)

    response = client.post(
        "/api/documents/upload",
        files={"file": ("big.txt", b"x" * 1000, "text/plain")},
    )
    assert response.status_code == 400
    assert "exceeds maximum" in response.json()["detail"]


def test_missing_filename_rejected(client, sample_txt_bytes):
    response = client.post(
        "/api/documents/upload",
        files={"file": ("", sample_txt_bytes, "text/plain")},
    )
    assert response.status_code in (400, 422)


@pytest.mark.asyncio
async def test_oversized_upload_read_is_bounded(monkeypatch):
    import api.validation as validation_module

    monkeypatch.setattr(validation_module, "MAX_FILE_SIZE_BYTES", 10)

    class TrackingUpload:
        filename = "large.txt"
        content_type = "text/plain"
        requested_size: int | None = None

        async def read(self, size: int) -> bytes:
            self.requested_size = size
            return b"x" * size

    upload = TrackingUpload()
    with pytest.raises(ValidationError, match="maximum allowed size"):
        await read_and_validate_upload(upload)  # type: ignore[arg-type]

    assert upload.requested_size == 11
