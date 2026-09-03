"""
Blind Spot AI application

FastAPI application entrypoint. This file wires together the API routers
and global error handling. All extraction/validation logic lives in the
`processing/`, `api/`, and `storage/` modules — not here.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import config
from api.analysis import router as analysis_router
from api.debate import router as debate_router
from api.documents import router as documents_router
from api.rag import router as rag_router
from storage.path_safety import InvalidDocumentIdError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("blindspot")

app = FastAPI(
    title="Blind Spot AI",
    description=(
        "Document ingestion pipeline that validates, stores, and normalizes "
        "uploaded files (PDF, PPTX, DOCX, TXT, images) into a common "
        "internal representation for AI analysis and multi-agent review."
    ),
    version="0.1.0",
)

if config.FRONTEND_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.FRONTEND_ORIGINS),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

app.include_router(documents_router)
app.include_router(analysis_router)
app.include_router(debate_router)
app.include_router(rag_router)


@app.exception_handler(InvalidDocumentIdError)
async def invalid_document_id_handler(
    request: Request, exc: InvalidDocumentIdError
) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "success": False,
            "error": "invalid_document_id",
            "detail": "Invalid document ID.",
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler so no raw stack trace is ever leaked to a client."""
    logger.exception("Unhandled exception on %s %s", request.method, request.url)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "internal_server_error",
            "detail": "An unexpected error occurred.",
        },
    )


@app.get("/", tags=["health"])
async def root() -> dict:
    return {
        "service": "Blind Spot AI",
        "status": "ok",
    }


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok"}
