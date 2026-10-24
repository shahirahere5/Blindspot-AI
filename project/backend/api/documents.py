"""API routes for document upload and retrieval."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from api.validation import ValidationError, read_and_validate_upload
from processing.exceptions import DocumentProcessingError, UnsupportedFileTypeError
from processing.factory import get_processor
from schemas.document import ErrorResponse, NormalizedDocument, UploadResponse
from schemas.versioning import VersionHistory, VersionedUploadResponse
from services import multimodal_service
from storage.document_store import DocumentStoreError, document_store
from storage.version_store import (
    VersionConflictError,
    VersionStoreError,
    version_store,
)

logger = logging.getLogger("blindspot.documents")

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _new_document_id() -> str:
    return f"doc_{uuid.uuid4()}"


def _cleanup_failed_upload(document_id: str, extension: str) -> None:
    try:
        document_store.delete_raw_file(document_id, extension)
    except DocumentStoreError:
        logger.exception("Failed to clean up raw upload for %s", document_id)


def _cleanup_processed_upload(processed: "_ProcessedUpload") -> None:
    _cleanup_failed_upload(processed.document.document_id, processed.extension)
    try:
        document_store.delete_normalized_document(processed.document.document_id)
    except DocumentStoreError:
        logger.exception("Failed to clean up normalized version upload")


@dataclass
class _ProcessedUpload:
    document: NormalizedDocument
    extension: str


async def _process_upload(file: UploadFile) -> _ProcessedUpload:
    """Run the shared validation, extraction, multimodal, and storage path."""
    try:
        raw_bytes, extension, file_type = await read_and_validate_upload(file)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    document_id = _new_document_id()
    try:
        file_path = document_store.save_raw_file(document_id, extension, raw_bytes)
    except DocumentStoreError as exc:
        logger.exception("Failed to store uploaded file for %s", document_id)
        raise HTTPException(status_code=500, detail="Failed to store uploaded file.") from exc

    try:
        processor = get_processor(file_type)
        document = processor.process(
            file_path=file_path,
            document_id=document_id,
            filename=file.filename or f"{document_id}{extension}",
        )
        document = await multimodal_service.enrich_document_with_visuals(document, file_path)
        document.metadata["uploaded_at"] = datetime.now(timezone.utc).isoformat()
    except UnsupportedFileTypeError as exc:
        _cleanup_failed_upload(document_id, extension)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DocumentProcessingError as exc:
        logger.warning("Processing failed for %s: %s", document_id, exc.message)
        _cleanup_failed_upload(document_id, extension)
        raise HTTPException(status_code=422, detail=f"Failed to process file: {exc.message}") from exc
    except Exception as exc:
        logger.exception("Unexpected error while processing %s", document_id)
        _cleanup_failed_upload(document_id, extension)
        raise HTTPException(status_code=500, detail="Unexpected error while processing file.") from exc

    try:
        document_store.save_normalized_document(document)
    except DocumentStoreError as exc:
        logger.exception("Failed to persist normalized document %s", document_id)
        _cleanup_failed_upload(document_id, extension)
        raise HTTPException(status_code=500, detail="Failed to persist normalized document.") from exc
    return _ProcessedUpload(document=document, extension=extension)


@router.post(
    "/upload",
    response_model=UploadResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def upload_document(file: UploadFile) -> UploadResponse:
    """
    Accept a file upload, validate it, extract its content, normalize it,
    and persist both the original file and the normalized representation.
    """
    processed = await _process_upload(file)
    normalized_document = processed.document

    return UploadResponse(
        success=True,
        document_id=normalized_document.document_id,
        filename=normalized_document.filename,
        file_type=normalized_document.file_type,
        status=normalized_document.status,
        metadata=normalized_document.metadata,
        warnings=normalized_document.warnings,
    )


@router.post(
    "/{document_id}/versions",
    response_model=VersionedUploadResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def upload_new_version(
    document_id: str,
    file: UploadFile = File(...),
    version_label: str | None = Form(default=None, max_length=120),
    notes: str | None = Form(default=None, max_length=2000),
) -> VersionedUploadResponse:
    """Upload a successor explicitly associated with the selected document."""
    parent = document_store.load_normalized_document(document_id)
    if parent is None:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' was not found.")
    try:
        version_store.assert_can_append(document_id)
    except VersionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except VersionStoreError as exc:
        logger.exception("Failed to inspect version history for %s", document_id)
        raise HTTPException(status_code=500, detail="Failed to read version history.") from exc

    processed = await _process_upload(file)
    try:
        group, entry = version_store.append(
            parent,
            processed.document,
            label=(version_label or "").strip() or None,
            notes=(notes or "").strip() or None,
        )
    except VersionConflictError as exc:
        _cleanup_processed_upload(processed)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except VersionStoreError as exc:
        logger.exception("Failed to persist new version for %s", document_id)
        _cleanup_processed_upload(processed)
        raise HTTPException(status_code=500, detail="Failed to persist version history.") from exc

    document = processed.document
    return VersionedUploadResponse(
        success=True,
        document_id=document.document_id,
        filename=document.filename,
        file_type=document.file_type,
        status=document.status,
        metadata=document.metadata,
        warnings=document.warnings,
        version_group_id=group.version_group_id,
        version_number=entry.version_number,
        previous_document_id=document_id,
        label=entry.label,
        notes=entry.notes,
        created_at=entry.created_at,
    )


@router.get(
    "/{document_id}/versions",
    response_model=VersionHistory,
    responses={404: {"model": ErrorResponse}},
)
async def get_version_history(document_id: str) -> VersionHistory:
    document = document_store.load_normalized_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' was not found.")
    try:
        return version_store.history_for(document)
    except VersionStoreError as exc:
        logger.exception("Failed to load version history for %s", document_id)
        raise HTTPException(status_code=500, detail="Failed to read version history.") from exc


@router.get(
    "/{document_id}",
    response_model=NormalizedDocument,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_document(document_id: str) -> NormalizedDocument:
    """Return the normalized document for a given document_id."""
    try:
        document = document_store.load_normalized_document(document_id)
    except DocumentStoreError as exc:
        logger.exception("Failed to load document %s", document_id)
        raise HTTPException(
            status_code=500, detail="Failed to load document."
        ) from exc

    if document is None:
        raise HTTPException(
            status_code=404, detail=f"Document '{document_id}' was not found."
        )

    return document
