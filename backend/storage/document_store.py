"""
Local filesystem storage for Phase 1.

Original uploaded files are stored under `data/uploads/`.
Normalized document JSON representations are stored under `data/documents/`.

No production database is introduced in Phase 1, per project constraints.
"""

from __future__ import annotations

import json
from pathlib import Path

from config import DOCUMENTS_DIR, UPLOADS_DIR
from schemas.document import NormalizedDocument


class DocumentStoreError(Exception):
    """Raised when a storage read/write operation fails."""


class DocumentStore:
    """Handles persistence of raw uploads and normalized documents."""

    def __init__(
        self,
        uploads_dir: Path = UPLOADS_DIR,
        documents_dir: Path = DOCUMENTS_DIR,
    ) -> None:
        self.uploads_dir = uploads_dir
        self.documents_dir = documents_dir
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.documents_dir.mkdir(parents=True, exist_ok=True)

    def save_raw_file(self, document_id: str, extension: str, data: bytes) -> Path:
        """Persist the original uploaded bytes to disk and return the path."""
        destination = self.uploads_dir / f"{document_id}{extension}"
        try:
            destination.write_bytes(data)
        except OSError as exc:
            raise DocumentStoreError(f"Failed to store uploaded file: {exc}") from exc
        return destination

    def save_normalized_document(self, document: NormalizedDocument) -> Path:
        """Persist the normalized document as JSON and return the path."""
        destination = self.documents_dir / f"{document.document_id}.json"
        try:
            destination.write_text(
                json.dumps(document.model_dump(mode="json"), indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            raise DocumentStoreError(
                f"Failed to persist normalized document: {exc}"
            ) from exc
        return destination

    def load_normalized_document(self, document_id: str) -> NormalizedDocument | None:
        """Load a normalized document by ID, or return None if not found."""
        path = self.documents_dir / f"{document_id}.json"
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DocumentStoreError(
                f"Failed to read normalized document '{document_id}': {exc}"
            ) from exc
        return NormalizedDocument.model_validate(raw)

    def document_exists(self, document_id: str) -> bool:
        return (self.documents_dir / f"{document_id}.json").exists()


# Shared singleton instance used across the API layer.
document_store = DocumentStore()
