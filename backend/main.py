"""
Blind Spot AI - Phase 1: Input Pipeline

FastAPI application entrypoint. This file wires together the API routers
and global error handling. All extraction/validation logic lives in the
`processing/`, `api/`, and `storage/` modules — not here.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.analysis import router as analysis_router
from api.debate import router as debate_router
from api.documents import router as documents_router
from api.rag import router as rag_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("blindspot")

app = FastAPI(
    title="Blind Spot AI - Phase 1: Input Pipeline",
    description=(
        "Document ingestion pipeline that validates, stores, and normalizes "
        "uploaded files (PDF, PPTX, DOCX, TXT, images) into a common "
        "internal representation for future AI analysis phases."
    ),
    version="0.1.0",
)

app.include_router(documents_router)
app.include_router(analysis_router)
app.include_router(debate_router)
app.include_router(rag_router)


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
        "service": "Blind Spot AI - Phase 1: Input Pipeline",
        "status": "ok",
    }


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok"}
