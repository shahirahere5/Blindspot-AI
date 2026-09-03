"""Shared validation for document-scoped storage paths."""

from __future__ import annotations

import re
from pathlib import Path


_DOCUMENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_SUFFIX_PATTERN = re.compile(r"^\.[A-Za-z0-9]{1,10}$")


class InvalidDocumentIdError(ValueError):
    """Raised before an untrusted document ID can become a filesystem path."""


def validate_document_id(document_id: str) -> None:
    if not _DOCUMENT_ID_PATTERN.fullmatch(document_id):
        raise InvalidDocumentIdError("Invalid document ID.")


def document_path(base_dir: Path, document_id: str, suffix: str) -> Path:
    """Return a document-owned path guaranteed to remain below ``base_dir``."""
    validate_document_id(document_id)
    if not _SUFFIX_PATTERN.fullmatch(suffix):
        raise ValueError("Invalid storage file extension.")

    resolved_base = base_dir.resolve()
    candidate = (resolved_base / f"{document_id}{suffix}").resolve()
    if candidate.parent != resolved_base:
        raise InvalidDocumentIdError("Invalid document ID.")
    return candidate
