"""API routes for Phase 2: single-pass AI analysis of a document."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ai.base import (
    AIAuthenticationError,
    AIClientError,
    AIConfigurationError,
    AIConnectionError,
    AIModelUnavailableError,
    AIRateLimitError,
    AIResponseError,
    AITimeoutError,
)
from ai.client import get_ai_client
from ai.embeddings.base import EmbeddingError
from schemas.analysis import AnalysisErrorResponse, AnalysisReport
from services.analysis_service import AnalysisGenerationError, analyze_document
from services.document_service import (
    DocumentHasNoAnalyzableContentError,
    DocumentNotFoundError,
    DocumentNotReadyError,
    DocumentTooLargeForAnalysisError,
)
from services.retrieval_service import DocumentNotIndexedError
from storage.vector_store import VectorStoreError

logger = logging.getLogger("blindspot.analysis_api")

router = APIRouter(prefix="/api/documents", tags=["analysis"])


@router.post(
    "/{document_id}/analyze",
    response_model=AnalysisReport,
    responses={
        400: {"model": AnalysisErrorResponse},
        404: {"model": AnalysisErrorResponse},
        413: {"model": AnalysisErrorResponse},
        422: {"model": AnalysisErrorResponse},
        429: {"model": AnalysisErrorResponse},
        500: {"model": AnalysisErrorResponse},
        502: {"model": AnalysisErrorResponse},
        504: {"model": AnalysisErrorResponse},
    },
)
async def analyze_document_endpoint(document_id: str) -> AnalysisReport:
    """
    Run a single-pass Blind Spot analysis over a previously uploaded and
    processed document, identifying risks, assumptions, biases, missing
    perspectives, unanswered questions, and recommendations.
    """
    ai_client = get_ai_client()

    try:
        return await analyze_document(document_id, ai_client)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    except DocumentNotReadyError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except DocumentHasNoAnalyzableContentError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except DocumentTooLargeForAnalysisError as exc:
        raise HTTPException(status_code=413, detail=exc.message) from exc
    except DocumentNotIndexedError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except EmbeddingError as exc:
        logger.error("Embedding error analyzing %s: %s", document_id, exc.message)
        raise HTTPException(status_code=500, detail=exc.message) from exc
    except VectorStoreError as exc:
        logger.error("Vector store error analyzing %s: %s", document_id, exc.message)
        raise HTTPException(status_code=500, detail=exc.message) from exc
    except AIConfigurationError as exc:
        # A missing/invalid server-side configuration (e.g. no GROQ_API_KEY)
        # is not the caller's fault -- surfaced as a 500, not a 4xx.
        logger.error("AI configuration error analyzing %s: %s", document_id, exc.message)
        raise HTTPException(status_code=500, detail=exc.message) from exc
    except AIAuthenticationError as exc:
        logger.error("AI authentication error analyzing %s: %s", document_id, exc.message)
        raise HTTPException(status_code=502, detail=exc.message) from exc
    except AIRateLimitError as exc:
        logger.warning("AI rate limit hit analyzing %s: %s", document_id, exc.message)
        raise HTTPException(status_code=429, detail=exc.message) from exc
    except AIConnectionError as exc:
        logger.error("AI connection error analyzing %s: %s", document_id, exc.message)
        raise HTTPException(status_code=502, detail=exc.message) from exc
    except AITimeoutError as exc:
        logger.error("AI timeout analyzing %s: %s", document_id, exc.message)
        raise HTTPException(status_code=504, detail=exc.message) from exc
    except AIModelUnavailableError as exc:
        logger.error("AI model unavailable analyzing %s: %s", document_id, exc.message)
        raise HTTPException(status_code=502, detail=exc.message) from exc
    except AIResponseError as exc:
        logger.error("AI response error analyzing %s: %s", document_id, exc.message)
        raise HTTPException(status_code=502, detail=exc.message) from exc
    except AIClientError as exc:  # catch-all for any other AI client failure
        logger.error("AI client error analyzing %s: %s", document_id, exc.message)
        raise HTTPException(status_code=502, detail=exc.message) from exc
    except AnalysisGenerationError as exc:
        logger.error("Analysis generation error for %s: %s", document_id, exc.message)
        raise HTTPException(status_code=422, detail=exc.message) from exc
    except Exception as exc:  # noqa: BLE001 - never leak internals to the client
        logger.exception("Unexpected error analyzing document %s", document_id)
        raise HTTPException(
            status_code=500, detail="Unexpected error during analysis."
        ) from exc
