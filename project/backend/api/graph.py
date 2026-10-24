"""Read APIs for document-scoped and version-series knowledge graphs."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

import config
from schemas.graph import GraphEdgeType, GraphNeighborsResponse, GraphNodeType, GraphResponse
from services.document_service import DocumentNotFoundError
from services.graph_service import (
    GraphNodeNotFoundError,
    InvalidGraphNodeIdError,
    get_graph,
    get_neighbors,
)
from storage.graph_store import GraphStoreError
from storage.path_safety import validate_document_id
from storage.version_store import VersionStoreError

logger = logging.getLogger("blindspot.graph_api")
router = APIRouter(prefix="/api/documents", tags=["knowledge-graph"])


@router.get("/{document_id}/graph", response_model=GraphResponse)
async def get_document_graph(
    document_id: str,
    scope: Literal["document", "series"] = "document",
    node_type: list[GraphNodeType] | None = Query(default=None),
    relationship_type: list[GraphEdgeType] | None = Query(default=None),
    node_limit: int = Query(default=config.GRAPH_MAX_NODES, ge=1, le=config.GRAPH_MAX_NODES),
    edge_limit: int = Query(default=config.GRAPH_MAX_EDGES, ge=1, le=config.GRAPH_MAX_EDGES),
) -> GraphResponse:
    validate_document_id(document_id)
    try:
        return get_graph(
            document_id,
            scope=scope,
            node_types=set(node_type) if node_type else None,
            edge_types=set(relationship_type) if relationship_type else None,
            node_limit=node_limit,
            edge_limit=edge_limit,
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    except (GraphStoreError, VersionStoreError) as exc:
        logger.error("Graph storage failure for %s: %s", document_id, exc)
        raise HTTPException(status_code=500, detail="Knowledge graph is temporarily unavailable.") from exc


@router.get("/{document_id}/graph/nodes/{node_id}", response_model=GraphNeighborsResponse)
async def get_graph_node_neighbors(
    document_id: str,
    node_id: str,
    scope: Literal["document", "series"] = "document",
    depth: int = Query(default=1, ge=1, le=config.GRAPH_MAX_TRAVERSAL_DEPTH),
    relationship_type: list[GraphEdgeType] | None = Query(default=None),
    limit: int = Query(
        default=min(100, config.GRAPH_MAX_NODES), ge=1, le=config.GRAPH_MAX_NODES
    ),
) -> GraphNeighborsResponse:
    validate_document_id(document_id)
    try:
        return get_neighbors(
            document_id,
            node_id,
            scope=scope,
            depth=depth,
            edge_types=set(relationship_type) if relationship_type else None,
            limit=limit,
        )
    except InvalidGraphNodeIdError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except (DocumentNotFoundError, GraphNodeNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    except (GraphStoreError, VersionStoreError) as exc:
        logger.error("Graph storage failure for %s: %s", document_id, exc)
        raise HTTPException(status_code=500, detail="Knowledge graph is temporarily unavailable.") from exc
