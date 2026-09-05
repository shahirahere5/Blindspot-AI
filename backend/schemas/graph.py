"""Strongly typed contracts for the grounded Blind Spot knowledge graph."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class GraphNodeType(str, Enum):
    DOCUMENT = "document"
    VERSION_GROUP = "version_group"
    SOURCE = "source"
    EVIDENCE = "evidence"
    RISK = "risk"
    ASSUMPTION = "assumption"
    BIAS = "bias"
    MISSING_PERSPECTIVE = "missing_perspective"
    QUESTION = "question"
    RECOMMENDATION = "recommendation"
    AGENT = "agent"
    FINDING = "finding"


class GraphEdgeType(str, Enum):
    CONTAINS = "contains"
    VERSION_OF = "version_of"
    PREVIOUS_VERSION = "previous_version"
    HAS_SOURCE = "has_source"
    SUPPORTS = "supports"
    ADDRESSED_BY = "addressed_by"
    IDENTIFIED = "identified"
    PRESENT_IN = "present_in"
    INTRODUCED_IN = "introduced_in"
    PERSISTS_IN = "persists_in"
    RESOLVED_IN = "resolved_in"
    PARTIALLY_ADDRESSED_IN = "partially_addressed_in"
    ADDRESSED_IN = "addressed_in"
    NOT_ADDRESSED_IN = "not_addressed_in"
    NO_LONGER_APPLICABLE_IN = "no_longer_applicable_in"


class GraphOrigin(str, Enum):
    DETERMINISTIC = "deterministic"
    ANALYSIS = "analysis"
    DEBATE = "debate"
    VERSION_COMPARISON = "version_comparison"


class GraphDiagnosticType(str, Enum):
    ORPHAN_RISK = "orphan_risk"
    UNMITIGATED_RISK = "unmitigated_risk"
    UNSUPPORTED_ASSUMPTION = "unsupported_assumption"
    REPEATED_MISSING_PERSPECTIVE = "repeated_missing_perspective"
    STALE_RECOMMENDATION = "stale_recommendation"


class GraphNode(BaseModel):
    id: str
    type: GraphNodeType
    label: str
    description: str = ""
    document_ids: list[str] = Field(default_factory=list)
    origins: list[GraphOrigin] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: GraphEdgeType
    origin: GraphOrigin
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphDiagnostic(BaseModel):
    type: GraphDiagnosticType
    node_id: str
    title: str
    description: str
    severity: str = "warning"


class GraphResponse(BaseModel):
    document_id: str
    scope: Literal["document", "series"]
    version_group_id: str | None = None
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    diagnostics: list[GraphDiagnostic] = Field(default_factory=list)
    truncated: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphNeighborsResponse(GraphResponse):
    root_node_id: str
    depth: int


class GraphContribution(BaseModel):
    artifact_id: str
    document_ids: list[str]
    version_group_id: str | None = None
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    metadata: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime


class StoredGraphState(BaseModel):
    contributions: dict[str, GraphContribution] = Field(default_factory=dict)
    document_index: dict[str, list[str]] = Field(default_factory=dict)
    version_group_index: dict[str, list[str]] = Field(default_factory=dict)
