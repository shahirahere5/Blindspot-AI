"""API routes for Phase 3: multi-agent debate analysis of a document."""

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
from ai.safe_errors import safe_ai_error_detail
from schemas.debate import DebateErrorResponse, DebateResult
from services.debate_service import (
    DebateAllAgentsFailedError,
    DebateGenerationError,
    run_debate,
)
from services.document_service import (
    DocumentHasNoAnalyzableContentError,
    DocumentNotFoundError,
    DocumentNotReadyError,
    DocumentTooLargeForAnalysisError,
)
from services.retrieval_service import DocumentNotIndexedError
from storage.path_safety import validate_document_id
from storage.vector_store import VectorStoreError

logger = logging.getLogger("blindspot.debate_api")

router = APIRouter(prefix="/api/documents", tags=["debate"])


@router.post(
    "/{document_id}/debate",
    response_model=DebateResult,
    responses={
        400: {"model": DebateErrorResponse},
        404: {"model": DebateErrorResponse},
        413: {"model": DebateErrorResponse},
        422: {"model": DebateErrorResponse},
        429: {"model": DebateErrorResponse},
        500: {"model": DebateErrorResponse},
        502: {"model": DebateErrorResponse},
        504: {"model": DebateErrorResponse},
    },
)
async def debate_document_endpoint(document_id: str) -> DebateResult:
    """
    Run the Phase 3 multi-agent Blind Spot debate over a previously uploaded
    and processed document: six independent specialist agents (Optimist,
    Skeptic, Security, Financial, Ethics, Legal) each analyze the document
    from their own perspective, and a Moderator agent synthesizes their
    findings into a single unified report.

    A single specialist agent failing does not fail the whole debate -- the
    Moderator is told which agents failed and the response's metadata
    records which succeeded/failed. If every agent fails, or the Moderator
    itself fails, a clear error is returned instead of a fabricated result.
    """
    validate_document_id(document_id)
    try:
        ai_client = get_ai_client()
        return await run_debate(document_id, ai_client)
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
        logger.error("Embedding error debating %s: %s", document_id, exc.message)
        raise HTTPException(status_code=500, detail="Document retrieval is temporarily unavailable.") from exc
    except VectorStoreError as exc:
        logger.error("Vector store error debating %s: %s", document_id, exc.message)
        raise HTTPException(status_code=500, detail="Document retrieval is temporarily unavailable.") from exc
    except AIConfigurationError as exc:
        # A missing/invalid server-side configuration (e.g. no GROQ_API_KEY)
        # is not the caller's fault -- surfaced as a 500, not a 4xx.
        logger.error("AI configuration error debating %s: %s", document_id, exc.message)
        raise HTTPException(status_code=500, detail=safe_ai_error_detail(exc, "debate")) from exc
    except AIAuthenticationError as exc:
        logger.error("AI authentication error debating %s: %s", document_id, exc.message)
        raise HTTPException(status_code=502, detail=safe_ai_error_detail(exc, "debate")) from exc
    except AIRateLimitError as exc:
        logger.warning("AI rate limit hit debating %s: %s", document_id, exc.message)
        raise HTTPException(status_code=429, detail=safe_ai_error_detail(exc, "debate")) from exc
    except AIConnectionError as exc:
        logger.error("AI connection error debating %s: %s", document_id, exc.message)
        raise HTTPException(status_code=502, detail=safe_ai_error_detail(exc, "debate")) from exc
    except AITimeoutError as exc:
        logger.error("AI timeout debating %s: %s", document_id, exc.message)
        raise HTTPException(status_code=504, detail=safe_ai_error_detail(exc, "debate")) from exc
    except AIModelUnavailableError as exc:
        logger.error("AI model unavailable debating %s: %s", document_id, exc.message)
        raise HTTPException(status_code=502, detail=safe_ai_error_detail(exc, "debate")) from exc
    except AIResponseError as exc:
        logger.error("AI response error debating %s: %s", document_id, exc.message)
        raise HTTPException(status_code=502, detail=safe_ai_error_detail(exc, "debate")) from exc
    except AIClientError as exc:  # catch-all for any other AI client failure
        logger.error("AI client error debating %s: %s", document_id, exc.message)
        raise HTTPException(status_code=502, detail=safe_ai_error_detail(exc, "debate")) from exc
    except DebateAllAgentsFailedError as exc:
        logger.error("All agents failed debating %s: %s", document_id, exc.message)
        raise HTTPException(status_code=502, detail=exc.message) from exc
    except DebateGenerationError as exc:
        logger.error("Debate generation error for %s: %s", document_id, exc.message)
        raise HTTPException(status_code=422, detail=exc.message) from exc
    except Exception as exc:  # noqa: BLE001 - never leak internals to the client
        logger.exception("Unexpected error running debate for document %s", document_id)
        raise HTTPException(
            status_code=500, detail="Unexpected error during debate analysis."
        ) from exc
