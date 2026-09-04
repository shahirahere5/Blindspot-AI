"""API for grounded semantic comparison of explicit document versions."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ai.base import AIClientError, AIConfigurationError, AIRateLimitError, AITimeoutError
from ai.client import get_ai_client
from ai.embeddings.base import EmbeddingError
from ai.safe_errors import safe_ai_error_detail
from schemas.comparison import ComparisonReport, ComparisonRequest
from services.comparison_service import ComparisonGenerationError, compare_versions
from services.document_service import (
    DocumentHasNoAnalyzableContentError,
    DocumentNotFoundError,
    DocumentNotReadyError,
    DocumentTooLargeForAnalysisError,
)
from storage.comparison_cache import ComparisonCacheError
from storage.path_safety import validate_document_id
from storage.vector_store import VectorStoreError
from storage.version_store import VersionRelationshipError, VersionStoreError

logger = logging.getLogger("blindspot.comparison_api")
router = APIRouter(prefix="/api/documents", tags=["comparison"])


@router.post("/compare", response_model=ComparisonReport)
async def compare_document_versions(request: ComparisonRequest) -> ComparisonReport:
    validate_document_id(request.old_document_id)
    validate_document_id(request.new_document_id)
    try:
        return await compare_versions(
            request.old_document_id, request.new_document_id, get_ai_client()
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    except (VersionRelationshipError, DocumentNotReadyError, DocumentHasNoAnalyzableContentError) as exc:
        detail = getattr(exc, "message", str(exc))
        raise HTTPException(status_code=400, detail=detail) from exc
    except DocumentTooLargeForAnalysisError as exc:
        raise HTTPException(status_code=413, detail=exc.message) from exc
    except AIRateLimitError as exc:
        raise HTTPException(status_code=429, detail=safe_ai_error_detail(exc, "comparison")) from exc
    except AITimeoutError as exc:
        raise HTTPException(status_code=504, detail=safe_ai_error_detail(exc, "comparison")) from exc
    except AIConfigurationError as exc:
        raise HTTPException(status_code=500, detail=safe_ai_error_detail(exc, "comparison")) from exc
    except AIClientError as exc:
        raise HTTPException(status_code=502, detail=safe_ai_error_detail(exc, "comparison")) from exc
    except ComparisonGenerationError as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc
    except (EmbeddingError, VectorStoreError) as exc:
        logger.error("Comparison retrieval failed: %s", exc)
        raise HTTPException(status_code=500, detail="Document retrieval is temporarily unavailable.") from exc
    except (VersionStoreError, ComparisonCacheError) as exc:
        logger.error("Comparison persistence failed: %s", exc)
        raise HTTPException(status_code=500, detail="Version comparison is temporarily unavailable.") from exc
    except Exception as exc:
        logger.exception("Unexpected comparison failure")
        raise HTTPException(status_code=500, detail="Unexpected error during comparison.") from exc
