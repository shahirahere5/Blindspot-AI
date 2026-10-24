"""Security regression tests for document-scoped filesystem storage."""

from __future__ import annotations

import pytest

from storage.document_store import DocumentStore
from storage.path_safety import InvalidDocumentIdError


def test_document_store_rejects_path_traversal(tmp_path):
    store = DocumentStore(tmp_path / "uploads", tmp_path / "documents")

    with pytest.raises(InvalidDocumentIdError):
        store.load_normalized_document(r"doc_\..\outside")


def test_raw_file_extension_cannot_change_storage_path(tmp_path):
    store = DocumentStore(tmp_path / "uploads", tmp_path / "documents")

    with pytest.raises(ValueError, match="extension"):
        store.save_raw_file("doc_safe", r"\..\outside", b"data")
