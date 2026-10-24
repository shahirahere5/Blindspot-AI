"""API routes for Phase 4: RAG document indexing and chunk retrieval.

Two endpoints, matching the two operations the RAG pipeline actually needs
exposed (index/re-index, and inspect retrieval for debugging) -- /analyze
and /debate call the same underlying services directly and do not go
through these HTTP endpoints themselves.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ai.embeddings.base import EmbeddingError
from ai.embeddings.factory import get_embedding_provider
from schemas.rag import (
    ChunkMetadataResponse,
    IndexDocumentResponse,
    RagErrorResponse,
    RetrievedChunkResponse,
    RetrieveRequest,
    RetrieveResponse,
)
from services.document_service import (
    DocumentHasNoAnalyzableContentError,
    DocumentNotFoundError,
    DocumentNotReadyError,
    ensure_document_is_analyzable,
    get_document_or_raise,
)
from services.retrieval_service import (
    DocumentNotIndexedError,
    ensure_document_indexed,
    retrieve_relevant_chunks,
)
from storage.path_safety import validate_document_id
from storage.vector_store import VectorStoreError

logger = logging.getLogger("blindspot.rag_api")

router = APIRouter(prefix="/api/documents", tags=["rag"])


@router.post(
    "/{document_id}/index",
    response_model=IndexDocumentResponse,
    responses={
        400: {"model": RagErrorResponse},
        404: {"model": RagErrorResponse},
        500: {"model": RagErrorResponse},
    },
)
async def index_document_endpoint(document_id: str) -> IndexDocumentResponse:
    """
    Chunk and embed a document's content and store it in the local vector
    store, so it's ready for retrieval. Always re-indexes from scratch
    (overwriting any previous index for this document), so this also
    doubles as the "re-index" operation if a document's content or the
    configured embedding provider ever changes.
    """
    validate_document_id(document_id)
    try:
        document = get_document_or_raise(document_id)
        ensure_document_is_analyzable(document)
        provider = get_embedding_provider()
        chunks_indexed = ensure_document_indexed(document, force=True)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    except DocumentNotReadyError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except DocumentHasNoAnalyzableContentError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except EmbeddingError as exc:
        logger.error("Embedding error indexing %s: %s", document_id, exc.message)
        raise HTTPException(status_code=500, detail="Document indexing is temporarily unavailable.") from exc
    except VectorStoreError as exc:
        logger.error("Vector store error indexing %s: %s", document_id, exc.message)
        raise HTTPException(status_code=500, detail="Document indexing is temporarily unavailable.") from exc
    except Exception as exc:  # noqa: BLE001 - never leak internals to the client
        logger.exception("Unexpected error indexing document %s", document_id)
        raise HTTPException(
            status_code=500, detail="Unexpected error during indexing."
        ) from exc

    return IndexDocumentResponse(
        document_id=document_id,
        chunks_indexed=chunks_indexed,
        embedding_provider=provider.provider_name,
        embedding_dimension=provider.dimension,
    )


@router.post(
    "/{document_id}/retrieve",
    response_model=RetrieveResponse,
    responses={
        400: {"model": RagErrorResponse},
        404: {"model": RagErrorResponse},
        500: {"model": RagErrorResponse},
    },
)
async def retrieve_chunks_endpoint(
    document_id: str, request: RetrieveRequest
) -> RetrieveResponse:
    """
    Retrieve the chunks most relevant to a query for a single document --
    mainly useful for debugging/inspecting what a RAG-enabled /analyze or
    /debate call would actually see. Auto-indexes the document first if it
    hasn't been indexed yet.
    """
    validate_document_id(document_id)
    try:
        document = get_document_or_raise(document_id)
        ensure_document_is_analyzable(document)
        ensure_document_indexed(document)
        results = retrieve_relevant_chunks(document_id, request.query, request.top_k)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    except DocumentNotReadyError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except DocumentNotIndexedError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except DocumentHasNoAnalyzableContentError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except EmbeddingError as exc:
        logger.error("Embedding error retrieving for %s: %s", document_id, exc.message)
        raise HTTPException(status_code=500, detail="Document retrieval is temporarily unavailable.") from exc
    except VectorStoreError as exc:
        logger.error(
            "Vector store error retrieving for %s: %s", document_id, exc.message
        )
        raise HTTPException(status_code=500, detail="Document retrieval is temporarily unavailable.") from exc
    except Exception as exc:  # noqa: BLE001 - never leak internals to the client
        logger.exception("Unexpected error retrieving chunks for %s", document_id)
        raise HTTPException(
            status_code=500, detail="Unexpected error during retrieval."
        ) from exc

    return RetrieveResponse(
        document_id=document_id,
        query=request.query,
        top_k=request.top_k if request.top_k is not None else len(results),
        results=[
            RetrievedChunkResponse(
                text=r.chunk.text,
                score=r.score,
                metadata=ChunkMetadataResponse(
                    chunk_index=r.chunk.chunk_index,
                    source_type=r.chunk.source_type,
                    source_location=r.chunk.source_location,
                ),
            )
            for r in results
        ],
    )
