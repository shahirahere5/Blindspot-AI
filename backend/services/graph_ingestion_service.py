"""Deterministically map validated Phase 2/3/8 outputs into graph data."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Iterable

from schemas.analysis import (
    AnalysisReport,
    Assumption,
    Bias,
    MissingPerspective,
    Recommendation,
    Risk,
    UnansweredQuestion,
)
from schemas.comparison import ComparisonFinding, ComparisonReport, RecommendationProgress
from schemas.debate import DebateResult
from schemas.document import ContentBlock, ContentBlockType, NormalizedDocument
from schemas.graph import (
    GraphContribution,
    GraphEdge,
    GraphEdgeType,
    GraphNode,
    GraphNodeType,
    GraphOrigin,
)
from services.document_service import get_document_or_raise
from storage.graph_store import GraphStore, graph_store
from storage.version_store import VersionStore, version_store

_SPACE = re.compile(r"\s+")


def _clean(value: str, limit: int = 4_000) -> str:
    return _SPACE.sub(" ", (value or "").strip())[:limit]


def _key(value: str) -> str:
    return _clean(value, 1_000).casefold()


def _id(prefix: str, *parts: object) -> str:
    raw = "\0".join(str(part) for part in parts)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]}"


class _Builder:
    def __init__(self, origin: GraphOrigin) -> None:
        self.origin = origin
        self.nodes: dict[str, GraphNode] = {}
        self.edges: dict[str, GraphEdge] = {}

    def node(
        self,
        node_type: GraphNodeType,
        stable_parts: Iterable[object],
        label: str,
        description: str,
        document_ids: Iterable[str],
        metadata: dict | None = None,
    ) -> GraphNode:
        node_id = _id("gn", node_type.value, *stable_parts)
        candidate = GraphNode(
            id=node_id,
            type=node_type,
            label=_clean(label, 300) or node_type.value.replace("_", " ").title(),
            description=_clean(description),
            document_ids=sorted(set(document_ids)),
            origins=[self.origin],
            metadata=metadata or {},
        )
        existing = self.nodes.get(node_id)
        if existing:
            existing.document_ids = sorted(set(existing.document_ids + candidate.document_ids))
            existing.origins = sorted(
                set(existing.origins + candidate.origins), key=lambda item: item.value
            )
            existing.metadata = {**existing.metadata, **candidate.metadata}
            if not existing.description:
                existing.description = candidate.description
            return existing
        self.nodes[node_id] = candidate
        return candidate

    def edge(
        self,
        source: GraphNode,
        target: GraphNode,
        edge_type: GraphEdgeType,
        metadata: dict | None = None,
    ) -> GraphEdge:
        edge_id = _id("ge", source.id, edge_type.value, target.id)
        edge = GraphEdge(
            id=edge_id,
            source=source.id,
            target=target.id,
            type=edge_type,
            origin=self.origin,
            metadata=metadata or {},
        )
        self.edges[edge_id] = edge
        return edge

    def contribution(
        self,
        artifact_id: str,
        document_ids: list[str],
        version_group_id: str | None,
    ) -> GraphContribution:
        return GraphContribution(
            artifact_id=artifact_id,
            document_ids=sorted(set(document_ids)),
            version_group_id=version_group_id,
            nodes=sorted(self.nodes.values(), key=lambda item: item.id),
            edges=sorted(self.edges.values(), key=lambda item: item.id),
            updated_at=datetime.now(timezone.utc),
        )


def _version_info(
    document: NormalizedDocument, store: VersionStore
) -> tuple[str | None, int | None, str | None, str | None]:
    group = store.find_group_for_document(document.document_id)
    if not group:
        return None, None, None, None
    entry = next(item for item in group.versions if item.document_id == document.document_id)
    return (
        group.version_group_id,
        entry.version_number,
        entry.label,
        entry.previous_document_id,
    )


def _add_document(
    builder: _Builder, document: NormalizedDocument, store: VersionStore
) -> tuple[GraphNode, str | None, int | None]:
    group_id, version_number, version_label, _ = _version_info(document, store)
    label = f"V{version_number} · {document.filename}" if version_number else document.filename
    node = builder.node(
        GraphNodeType.DOCUMENT,
        [document.document_id],
        label,
        "Normalized decision document",
        [document.document_id],
        {
            "document_id": document.document_id,
            "filename": document.filename,
            "file_type": document.file_type.value,
            "status": document.status.value,
            "version_number": version_number,
            "version_label": version_label,
        },
    )
    if group_id:
        group = builder.node(
            GraphNodeType.VERSION_GROUP,
            [group_id],
            "Version series",
            "Explicitly associated document versions",
            [document.document_id],
            {"version_group_id": group_id},
        )
        builder.edge(node, group, GraphEdgeType.VERSION_OF)
    return node, group_id, version_number


def _matching_blocks(document: NormalizedDocument, locations: list[int]) -> list[ContentBlock]:
    allowed = set(locations)
    return [block for block in document.content if block.location in allowed]


def _add_source(builder: _Builder, document: NormalizedDocument, block: ContentBlock, version: int | None) -> GraphNode:
    prefix = f"V{version} · " if version else ""
    label = f"{prefix}{block.type.value.title()} {block.location}"
    visual = block.type == ContentBlockType.IMAGE or bool(block.extra.get("visual_analysis"))
    return builder.node(
        GraphNodeType.SOURCE,
        [document.document_id, block.type.value, block.location],
        label,
        _clean(block.text, 800),
        [document.document_id],
        {
            "document_id": document.document_id,
            "source_type": block.type.value,
            "source_location": block.location,
            "version_number": version,
            "visual_derived": visual,
        },
    )


def _add_evidence(
    builder: _Builder,
    document: NormalizedDocument,
    finding: GraphNode,
    evidence: str,
    locations: list[int],
    version: int | None,
) -> GraphNode | None:
    blocks = _matching_blocks(document, locations)
    evidence_text = _clean(evidence, 2_000)
    # A model-provided evidence string without a real validated location is
    # not promoted to graph evidence. The finding remains visible and can be
    # diagnosed as unsupported/orphaned.
    if not evidence_text or not blocks:
        return None
    valid_locations = sorted({block.location for block in blocks})
    visual = any(
        block.type == ContentBlockType.IMAGE or bool(block.extra.get("visual_analysis"))
        for block in blocks
    )
    node = builder.node(
        GraphNodeType.EVIDENCE,
        [document.document_id, evidence_text.casefold(), *valid_locations],
        evidence_text[:120],
        evidence_text,
        [document.document_id],
        {
            "document_id": document.document_id,
            "source_locations": valid_locations,
            "version_number": version,
            "visual_derived": visual,
        },
    )
    builder.edge(node, finding, GraphEdgeType.SUPPORTS)
    for block in blocks:
        builder.edge(node, _add_source(builder, document, block, version), GraphEdgeType.HAS_SOURCE)
    return node


def _add_recommendation(
    builder: _Builder,
    document_node: GraphNode,
    document_id: str,
    title: str,
    description: str,
    priority: str | None = None,
) -> GraphNode:
    text_key = _key(title or description)
    node = builder.node(
        GraphNodeType.RECOMMENDATION,
        [document_id, text_key],
        title or description,
        description,
        [document_id],
        {"priority": priority} if priority else {},
    )
    builder.edge(document_node, node, GraphEdgeType.CONTAINS)
    return node


def _add_risk(builder: _Builder, document: NormalizedDocument, document_node: GraphNode, item: Risk, version: int | None) -> GraphNode:
    node = builder.node(
        GraphNodeType.RISK,
        [document.document_id, _key(item.title)],
        item.title,
        item.description,
        [document.document_id],
        {"severity": item.severity.value},
    )
    builder.edge(document_node, node, GraphEdgeType.CONTAINS)
    _add_evidence(builder, document, node, item.evidence, item.source_locations, version)
    if _clean(item.recommendation):
        recommendation = _add_recommendation(
            builder, document_node, document.document_id, item.recommendation, item.recommendation
        )
        builder.edge(node, recommendation, GraphEdgeType.ADDRESSED_BY)
    return node


def _add_assumption(builder: _Builder, document: NormalizedDocument, document_node: GraphNode, item: Assumption, version: int | None) -> GraphNode:
    node = builder.node(
        GraphNodeType.ASSUMPTION,
        [document.document_id, _key(item.title)],
        item.title,
        item.description,
        [document.document_id],
        {"confidence": item.confidence.value, "why_it_matters": _clean(item.why_it_matters)},
    )
    builder.edge(document_node, node, GraphEdgeType.CONTAINS)
    _add_evidence(builder, document, node, item.evidence, item.source_locations, version)
    return node


def _add_bias(builder: _Builder, document: NormalizedDocument, document_node: GraphNode, item: Bias, version: int | None) -> GraphNode:
    node = builder.node(
        GraphNodeType.BIAS,
        [document.document_id, _key(item.title)],
        item.title,
        item.description,
        [document.document_id],
    )
    builder.edge(document_node, node, GraphEdgeType.CONTAINS)
    _add_evidence(builder, document, node, item.evidence, item.source_locations, version)
    if _clean(item.recommendation):
        recommendation = _add_recommendation(
            builder, document_node, document.document_id, item.recommendation, item.recommendation
        )
        builder.edge(node, recommendation, GraphEdgeType.ADDRESSED_BY)
    return node


def _add_perspective(builder: _Builder, document_node: GraphNode, document_id: str, item: MissingPerspective) -> GraphNode:
    node = builder.node(
        GraphNodeType.MISSING_PERSPECTIVE,
        [document_id, _key(item.perspective)],
        item.perspective,
        item.description,
        [document_id],
        {"why_it_matters": _clean(item.why_it_matters), "questions": [_clean(q, 500) for q in item.questions_to_consider]},
    )
    builder.edge(document_node, node, GraphEdgeType.CONTAINS)
    return node


def _add_question(builder: _Builder, document_node: GraphNode, document_id: str, item: UnansweredQuestion) -> GraphNode:
    node = builder.node(
        GraphNodeType.QUESTION,
        [document_id, _key(item.question)],
        item.question,
        item.reason,
        [document_id],
        {"importance": item.importance.value},
    )
    builder.edge(document_node, node, GraphEdgeType.CONTAINS)
    return node


def ingest_analysis(
    report: AnalysisReport,
    *,
    store: GraphStore | None = None,
    versions: VersionStore | None = None,
) -> GraphContribution:
    store = store or graph_store
    versions = versions or version_store
    document = get_document_or_raise(report.document_id)
    builder = _Builder(GraphOrigin.ANALYSIS)
    document_node, group_id, version = _add_document(builder, document, versions)
    for item in report.risks:
        _add_risk(builder, document, document_node, item, version)
    for item in report.assumptions:
        _add_assumption(builder, document, document_node, item, version)
    for item in report.biases:
        _add_bias(builder, document, document_node, item, version)
    for item in report.missing_perspectives:
        _add_perspective(builder, document_node, document.document_id, item)
    for item in report.unanswered_questions:
        _add_question(builder, document_node, document.document_id, item)
    for item in report.recommendations:
        _add_recommendation(
            builder,
            document_node,
            document.document_id,
            item.title,
            item.description,
            item.priority.value,
        )
    contribution = builder.contribution(
        f"analysis:{document.document_id}", [document.document_id], group_id
    )
    store.upsert(contribution)
    return contribution


def ingest_debate(
    result: DebateResult,
    *,
    store: GraphStore | None = None,
    versions: VersionStore | None = None,
) -> GraphContribution:
    store = store or graph_store
    versions = versions or version_store
    document = get_document_or_raise(result.document_id)
    builder = _Builder(GraphOrigin.DEBATE)
    document_node, group_id, version = _add_document(builder, document, versions)
    for item in result.final_risks:
        _add_risk(builder, document, document_node, item, version)
    for item in result.final_assumptions:
        _add_assumption(builder, document, document_node, item, version)
    for item in result.final_biases:
        _add_bias(builder, document, document_node, item, version)
    for item in result.missing_perspectives:
        _add_perspective(builder, document_node, document.document_id, item)
    for item in result.unanswered_questions:
        _add_question(builder, document_node, document.document_id, item)
    for item in result.recommendations:
        _add_recommendation(builder, document_node, document.document_id, item.title, item.description, item.priority.value)

    for analysis in result.agent_analyses:
        if analysis.status.value != "succeeded":
            continue
        agent = builder.node(
            GraphNodeType.AGENT,
            [analysis.agent.value],
            f"{analysis.agent.value.title()} agent",
            analysis.role,
            [document.document_id],
            {"agent": analysis.agent.value, "confidence": analysis.confidence.value},
        )
        for finding in analysis.findings:
            node = builder.node(
                GraphNodeType.FINDING,
                [document.document_id, analysis.agent.value, _key(finding.title)],
                finding.title,
                finding.description,
                [document.document_id],
                {"severity": finding.severity.value, "agent": analysis.agent.value},
            )
            builder.edge(document_node, node, GraphEdgeType.CONTAINS)
            builder.edge(agent, node, GraphEdgeType.IDENTIFIED)
            _add_evidence(builder, document, node, finding.evidence, finding.source_locations, version)
        for assumption in analysis.assumptions:
            node = _add_assumption(builder, document, document_node, assumption, version)
            builder.edge(agent, node, GraphEdgeType.IDENTIFIED)
    contribution = builder.contribution(
        f"debate:{document.document_id}", [document.document_id], group_id
    )
    store.upsert(contribution)
    return contribution


def _comparison_finding(
    builder: _Builder,
    node_type: GraphNodeType,
    category: str,
    item: ComparisonFinding,
    report: ComparisonReport,
    old: NormalizedDocument,
    new: NormalizedDocument,
    old_node: GraphNode,
    new_node: GraphNode,
) -> GraphNode:
    node = builder.node(
        node_type,
        [report.version_group_id, node_type.value, _key(item.title)],
        item.title,
        item.description,
        [old.document_id, new.document_id],
        {"lifecycle_category": category},
    )
    old_edge: GraphEdgeType | None = GraphEdgeType.PRESENT_IN
    new_edge = GraphEdgeType.PRESENT_IN
    if category.startswith("new_"):
        old_edge = None
        new_edge = GraphEdgeType.INTRODUCED_IN
    elif category.startswith("resolved_"):
        new_edge = GraphEdgeType.RESOLVED_IN
    elif category.startswith("persistent_"):
        new_edge = GraphEdgeType.PERSISTS_IN
    elif category == "meaningful_additions":
        old_edge = None
        new_edge = GraphEdgeType.INTRODUCED_IN
    elif category == "meaningful_removals":
        new_edge = GraphEdgeType.RESOLVED_IN
    if old_edge:
        builder.edge(node, old_node, old_edge)
    builder.edge(node, new_node, new_edge)
    _add_evidence(builder, old, node, item.old_evidence, item.old_source_locations, report.old_version_number)
    _add_evidence(builder, new, node, item.new_evidence, item.new_source_locations, report.new_version_number)
    return node


def ingest_comparison(
    report: ComparisonReport,
    *,
    store: GraphStore | None = None,
    versions: VersionStore | None = None,
) -> GraphContribution:
    store = store or graph_store
    versions = versions or version_store
    old = get_document_or_raise(report.old_document_id)
    new = get_document_or_raise(report.new_document_id)
    builder = _Builder(GraphOrigin.VERSION_COMPARISON)
    old_node, _, _ = _add_document(builder, old, versions)
    new_node, _, _ = _add_document(builder, new, versions)
    group = versions.find_group_for_document(new.document_id)
    if group:
        new_entry = next(item for item in group.versions if item.document_id == new.document_id)
        if new_entry.previous_document_id == old.document_id:
            builder.edge(new_node, old_node, GraphEdgeType.PREVIOUS_VERSION)

    collections: list[tuple[str, GraphNodeType, list[ComparisonFinding]]] = [
        ("new_risks", GraphNodeType.RISK, report.new_risks),
        ("resolved_risks", GraphNodeType.RISK, report.resolved_risks),
        ("persistent_risks", GraphNodeType.RISK, report.persistent_risks),
        ("new_assumptions", GraphNodeType.ASSUMPTION, report.new_assumptions),
        ("resolved_assumptions", GraphNodeType.ASSUMPTION, report.resolved_assumptions),
        ("persistent_assumptions", GraphNodeType.ASSUMPTION, report.persistent_assumptions),
        ("new_biases", GraphNodeType.BIAS, report.new_biases),
        ("resolved_biases", GraphNodeType.BIAS, report.resolved_biases),
        ("persistent_biases", GraphNodeType.BIAS, report.persistent_biases),
        ("new_missing_perspectives", GraphNodeType.MISSING_PERSPECTIVE, report.new_missing_perspectives),
        ("resolved_missing_perspectives", GraphNodeType.MISSING_PERSPECTIVE, report.resolved_missing_perspectives),
        ("persistent_missing_perspectives", GraphNodeType.MISSING_PERSPECTIVE, report.persistent_missing_perspectives),
        ("new_questions", GraphNodeType.QUESTION, report.new_questions),
        ("resolved_questions", GraphNodeType.QUESTION, report.resolved_questions),
        ("persistent_questions", GraphNodeType.QUESTION, report.persistent_questions),
        ("meaningful_additions", GraphNodeType.FINDING, report.meaningful_additions),
        ("meaningful_removals", GraphNodeType.FINDING, report.meaningful_removals),
        ("regressions", GraphNodeType.FINDING, report.regressions),
    ]
    for category, node_type, items in collections:
        for item in items:
            _comparison_finding(builder, node_type, category, item, report, old, new, old_node, new_node)

    progress_edges = {
        "addressed": GraphEdgeType.ADDRESSED_IN,
        "partially_addressed": GraphEdgeType.PARTIALLY_ADDRESSED_IN,
        "not_addressed": GraphEdgeType.NOT_ADDRESSED_IN,
        "no_longer_applicable": GraphEdgeType.NO_LONGER_APPLICABLE_IN,
        "uncertain": GraphEdgeType.PRESENT_IN,
    }
    for item in report.recommendation_progress:
        recommendation = builder.node(
            GraphNodeType.RECOMMENDATION,
            [report.version_group_id, _key(item.title)],
            item.title,
            item.description,
            [old.document_id, new.document_id],
            {"progress_status": item.progress_status.value},
        )
        builder.edge(recommendation, old_node, GraphEdgeType.PRESENT_IN)
        builder.edge(recommendation, new_node, progress_edges[item.progress_status.value])
        _add_evidence(builder, old, recommendation, item.old_evidence, item.old_source_locations, report.old_version_number)
        _add_evidence(builder, new, recommendation, item.new_evidence, item.new_source_locations, report.new_version_number)

    contribution = builder.contribution(
        f"comparison:{old.document_id}:{new.document_id}",
        [old.document_id, new.document_id],
        report.version_group_id,
    )
    store.upsert(contribution)
    return contribution
