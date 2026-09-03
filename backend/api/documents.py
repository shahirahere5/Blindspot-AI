"""API routes for document upload and retrieval."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from api.validation import ValidationError, read_and_validate_upload
from processing.exceptions import DocumentProcessingError, UnsupportedFileTypeError
from processing.factory import get_processor
from schemas.document import ErrorResponse, NormalizedDocument, UploadResponse
from storage.document_store import DocumentStoreError, document_store

logger = logging.getLogger("blindspot.documents")

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _new_document_id() -> str:
    return f"doc_{uuid.uuid4()}"


def _cleanup_failed_upload(document_id: str, extension: str) -> None:
    try:
        document_store.delete_raw_file(document_id, extension)
    except DocumentStoreError:
        logger.exception("Failed to clean up raw upload for %s", document_id)


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
    # --- Validation -------------------------------------------------
    try:
        raw_bytes, extension, file_type = await read_and_validate_upload(file)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    document_id = _new_document_id()

    # --- Storage: original file --------------------------------------
    try:
        file_path = document_store.save_raw_file(document_id, extension, raw_bytes)
    except DocumentStoreError as exc:
        logger.exception("Failed to store uploaded file for %s", document_id)
        raise HTTPException(
            status_code=500, detail="Failed to store uploaded file."
        ) from exc

    # --- Processing / normalization -----------------------------------
    try:
        processor = get_processor(file_type)
        normalized_document = processor.process(
            file_path=file_path,
            document_id=document_id,
            filename=file.filename or f"{document_id}{extension}",
        )
    except UnsupportedFileTypeError as exc:
        _cleanup_failed_upload(document_id, extension)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DocumentProcessingError as exc:
        logger.warning("Processing failed for %s: %s", document_id, exc.message)
        _cleanup_failed_upload(document_id, extension)
        raise HTTPException(
            status_code=422,
            detail=f"Failed to process file: {exc.message}",
        ) from exc
    except Exception as exc:  # noqa: BLE001 - never leak internals to the client
        logger.exception("Unexpected error while processing %s", document_id)
        _cleanup_failed_upload(document_id, extension)
        raise HTTPException(
            status_code=500, detail="Unexpected error while processing file."
        ) from exc

    # --- Storage: normalized document ----------------------------------
    try:
        document_store.save_normalized_document(normalized_document)
    except DocumentStoreError as exc:
        logger.exception("Failed to persist normalized document %s", document_id)
        _cleanup_failed_upload(document_id, extension)
        raise HTTPException(
            status_code=500, detail="Failed to persist normalized document."
        ) from exc

    return UploadResponse(
        success=True,
        document_id=normalized_document.document_id,
        filename=normalized_document.filename,
        file_type=normalized_document.file_type,
        status=normalized_document.status,
        metadata=normalized_document.metadata,
        warnings=normalized_document.warnings,
    )


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
