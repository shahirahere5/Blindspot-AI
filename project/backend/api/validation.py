"""Validation helpers for uploaded files (extension, MIME type, size)."""

from __future__ import annotations

from pathlib import Path

from fastapi import UploadFile

from config import (
    ALL_ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE_BYTES,
    SUPPORTED_MIME_TYPES,
    extension_to_file_type,
)


class ValidationError(Exception):
    """Raised when an uploaded file fails validation."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def get_extension(filename: str) -> str:
    return Path(filename).suffix.lower()


def validate_filename_and_extension(filename: str | None) -> tuple[str, str]:
    """Validate filename presence and extension, returning (extension, file_type)."""
    if not filename or not filename.strip():
        raise ValidationError("Uploaded file must have a filename.")

    extension = get_extension(filename)
    if extension not in ALL_ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALL_ALLOWED_EXTENSIONS))
        raise ValidationError(
            f"Unsupported file extension '{extension}'. Allowed extensions: {allowed}."
        )

    file_type = extension_to_file_type(extension)
    if file_type is None:
        # Should not happen given the check above, but guard defensively.
        raise ValidationError(f"Unsupported file extension '{extension}'.")

    return extension, file_type


# Generic/placeholder content types sent by tools like curl or some browsers
# when they cannot determine a more specific MIME type. These are treated as
# "unknown" rather than as a mismatch, since the extension is the primary
# signal for routing to a processor.
GENERIC_CONTENT_TYPES = {"application/octet-stream", ""}


def validate_mime_type(content_type: str | None, file_type: str) -> None:
    """Soft-validate MIME type. Unknown/missing/generic content types are
    tolerated since browsers and clients are inconsistent about setting them,
    but a clearly mismatched, specific MIME type (e.g. an image content-type
    on a .docx file) is rejected."""
    if not content_type or content_type in GENERIC_CONTENT_TYPES:
        return

    allowed_mime_types = SUPPORTED_MIME_TYPES.get(file_type, set())
    if not allowed_mime_types:
        return

    if content_type not in allowed_mime_types:
        raise ValidationError(
            f"MIME type '{content_type}' does not match expected type "
            f"for '{file_type}' files."
        )


def validate_file_size(size_bytes: int) -> None:
    if size_bytes <= 0:
        raise ValidationError("Uploaded file is empty.")
    if size_bytes > MAX_FILE_SIZE_BYTES:
        max_mb = MAX_FILE_SIZE_BYTES / (1024 * 1024)
        raise ValidationError(f"File exceeds maximum allowed size of {max_mb:.0f} MB.")


async def read_and_validate_upload(upload_file: UploadFile) -> tuple[bytes, str, str]:
    """
    Fully validate an UploadFile and return (raw_bytes, extension, file_type).

    Raises ValidationError on any validation failure.
    """
    extension, file_type = validate_filename_and_extension(upload_file.filename)
    validate_mime_type(upload_file.content_type, file_type)

    # Read at most one byte beyond the limit. Reading the entire request first
    # would allow an oversized upload to consume unbounded application memory
    # before the configured limit could be enforced.
    raw_bytes = await upload_file.read(MAX_FILE_SIZE_BYTES + 1)
    validate_file_size(len(raw_bytes))

    return raw_bytes, extension, file_type
