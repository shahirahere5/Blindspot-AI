"""Scoped graph queries, bounded traversal, and deterministic diagnostics."""

from __future__ import annotations

import re
from collections import deque

import config
from schemas.graph import (
    GraphContribution,
    GraphDiagnostic,
    GraphDiagnosticType,
    GraphEdge,
    GraphEdgeType,
    GraphNeighborsResponse,
    GraphNode,
    GraphNodeType,
    GraphResponse,
)
from services.document_service import get_document_or_raise
from storage.graph_store import GraphStore, graph_store
from storage.version_store import VersionStore, version_store

_NODE_ID = re.compile(r"^gn_[0-9a-f]{32}$")


class GraphNodeNotFoundError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class InvalidGraphNodeIdError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def _merge(contributions: list[GraphContribution]) -> tuple[list[GraphNode], list[GraphEdge]]:
    nodes: dict[str, GraphNode] = {}
    edges: dict[str, GraphEdge] = {}
    for contribution in contributions:
        for candidate in contribution.nodes:
            existing = nodes.get(candidate.id)
            if existing:
                existing.document_ids = sorted(set(existing.document_ids + candidate.document_ids))
                existing.origins = sorted(
                    set(existing.origins + candidate.origins), key=lambda item: item.value
                )
                existing.metadata = {**existing.metadata, **candidate.metadata}
                if not existing.description:
                    existing.description = candidate.description
            else:
                nodes[candidate.id] = candidate.model_copy(deep=True)
        for edge in contribution.edges:
            edges[edge.id] = edge.model_copy(deep=True)
    return sorted(nodes.values(), key=lambda item: item.id), sorted(edges.values(), key=lambda item: item.id)


def _contributions_for_scope(
    document_id: str,
    scope: str,
    store: GraphStore,
    versions: VersionStore,
) -> tuple[list[GraphContribution], str | None]:
    document = get_document_or_raise(document_id)
    group = versions.find_group_for_document(document.document_id)
    if scope == "document":
        contributions = [
            item for item in store.for_document(document_id)
            if not item.artifact_id.startswith("comparison:")
        ]
        return contributions, group.version_group_id if group else None
    if scope != "series":
        raise ValueError("Graph scope must be 'document' or 'series'.")
    if not group:
        contributions = [
            item for item in store.for_document(document_id)
            if not item.artifact_id.startswith("comparison:")
        ]
        return contributions, None

    by_artifact: dict[str, GraphContribution] = {}
    for entry in group.versions:
        for contribution in store.for_document(entry.document_id):
            by_artifact[contribution.artifact_id] = contribution
    for contribution in store.for_version_group(group.version_group_id):
        by_artifact[contribution.artifact_id] = contribution
    return list(by_artifact.values()), group.version_group_id


def graph_diagnostics(nodes: list[GraphNode], edges: list[GraphEdge]) -> list[GraphDiagnostic]:
    node_map = {node.id: node for node in nodes}
    incoming: dict[str, list[GraphEdge]] = {}
    outgoing: dict[str, list[GraphEdge]] = {}
    for edge in edges:
        outgoing.setdefault(edge.source, []).append(edge)
        incoming.setdefault(edge.target, []).append(edge)
    diagnostics: list[GraphDiagnostic] = []
    for node in nodes:
        if node.type == GraphNodeType.RISK:
            if not any(edge.type == GraphEdgeType.SUPPORTS for edge in incoming.get(node.id, [])):
                diagnostics.append(GraphDiagnostic(
                    type=GraphDiagnosticType.ORPHAN_RISK,
                    node_id=node.id,
                    title=f"Unsupported risk: {node.label}",
                    description="This risk has no connected evidence with a validated source.",
                ))
            if not any(edge.type == GraphEdgeType.ADDRESSED_BY for edge in outgoing.get(node.id, [])):
                diagnostics.append(GraphDiagnostic(
                    type=GraphDiagnosticType.UNMITIGATED_RISK,
                    node_id=node.id,
                    title=f"Unmitigated risk: {node.label}",
                    description="No recommendation is explicitly connected to this risk.",
                ))
        if node.type == GraphNodeType.ASSUMPTION and not any(
            edge.type == GraphEdgeType.SUPPORTS for edge in incoming.get(node.id, [])
        ):
            diagnostics.append(GraphDiagnostic(
                type=GraphDiagnosticType.UNSUPPORTED_ASSUMPTION,
                node_id=node.id,
                title=f"Unsupported assumption: {node.label}",
                description="This assumption has no evidence with a validated source.",
            ))
        if node.type == GraphNodeType.RECOMMENDATION:
            lifecycle = [
                edge for edge in outgoing.get(node.id, [])
                if edge.type in {
                    GraphEdgeType.NOT_ADDRESSED_IN, GraphEdgeType.ADDRESSED_IN,
                    GraphEdgeType.PARTIALLY_ADDRESSED_IN,
                    GraphEdgeType.NO_LONGER_APPLICABLE_IN,
                }
            ]
            not_addressed = [
                edge for edge in lifecycle if edge.type == GraphEdgeType.NOT_ADDRESSED_IN
            ]
            latest = max(
                lifecycle,
                key=lambda edge: int(node_map.get(edge.target, node).metadata.get("version_number") or 0),
                default=None,
            )
            if len(not_addressed) >= 2 and latest and latest.type == GraphEdgeType.NOT_ADDRESSED_IN:
                diagnostics.append(GraphDiagnostic(
                    type=GraphDiagnosticType.STALE_RECOMMENDATION,
                    node_id=node.id,
                    title=f"Stale recommendation: {node.label}",
                    description="Multiple version comparisons explicitly classified this recommendation as not addressed.",
                ))

    perspectives: dict[str, list[GraphNode]] = {}
    for node in nodes:
        if node.type == GraphNodeType.MISSING_PERSPECTIVE:
            perspectives.setdefault(node.label.casefold().strip(), []).append(node)
    for repeated in perspectives.values():
        document_ids = {document_id for node in repeated for document_id in node.document_ids}
        if len(document_ids) > 1:
            diagnostics.append(GraphDiagnostic(
                type=GraphDiagnosticType.REPEATED_MISSING_PERSPECTIVE,
                node_id=repeated[0].id,
                title=f"Repeated missing perspective: {repeated[0].label}",
                description=f"This perspective is missing in {len(document_ids)} document versions.",
            ))
    return sorted(diagnostics, key=lambda item: (item.type.value, item.node_id))


def _filter_and_limit(
    nodes: list[GraphNode],
    edges: list[GraphEdge],
    diagnostics: list[GraphDiagnostic],
    node_types: set[GraphNodeType] | None,
    edge_types: set[GraphEdgeType] | None,
    node_limit: int,
    edge_limit: int,
) -> tuple[list[GraphNode], list[GraphEdge], list[GraphDiagnostic], bool]:
    filtered_nodes = [node for node in nodes if not node_types or node.type in node_types]
    truncated = len(filtered_nodes) > node_limit
    filtered_nodes = filtered_nodes[:node_limit]
    node_ids = {node.id for node in filtered_nodes}
    filtered_edges = [
        edge for edge in edges
        if edge.source in node_ids and edge.target in node_ids
        and (not edge_types or edge.type in edge_types)
    ]
    truncated = truncated or len(filtered_edges) > edge_limit
    filtered_edges = filtered_edges[:edge_limit]
    filtered_diagnostics = [item for item in diagnostics if item.node_id in node_ids]
    return filtered_nodes, filtered_edges, filtered_diagnostics, truncated


def get_graph(
    document_id: str,
    *,
    scope: str = "document",
    node_types: set[GraphNodeType] | None = None,
    edge_types: set[GraphEdgeType] | None = None,
    node_limit: int | None = None,
    edge_limit: int | None = None,
    store: GraphStore | None = None,
    versions: VersionStore | None = None,
) -> GraphResponse:
    store = store or graph_store
    versions = versions or version_store
    contributions, group_id = _contributions_for_scope(document_id, scope, store, versions)
    nodes, edges = _merge(contributions)
    diagnostics = graph_diagnostics(nodes, edges)
    nodes, edges, diagnostics, truncated = _filter_and_limit(
        nodes,
        edges,
        diagnostics,
        node_types,
        edge_types,
        min(node_limit or config.GRAPH_MAX_NODES, config.GRAPH_MAX_NODES),
        min(edge_limit or config.GRAPH_MAX_EDGES, config.GRAPH_MAX_EDGES),
    )
    return GraphResponse(
        document_id=document_id,
        scope=scope,
        version_group_id=group_id,
        nodes=nodes,
        edges=edges,
        diagnostics=diagnostics,
        truncated=truncated,
        metadata={
            "node_count": len(nodes),
            "edge_count": len(edges),
            "contribution_count": len(contributions),
        },
    )


def get_neighbors(
    document_id: str,
    node_id: str,
    *,
    scope: str = "document",
    depth: int = 1,
    edge_types: set[GraphEdgeType] | None = None,
    limit: int | None = None,
    store: GraphStore | None = None,
    versions: VersionStore | None = None,
) -> GraphNeighborsResponse:
    if not _NODE_ID.fullmatch(node_id):
        raise InvalidGraphNodeIdError("Invalid graph node ID.")
    store = store or graph_store
    versions = versions or version_store
    contributions, group_id = _contributions_for_scope(document_id, scope, store, versions)
    nodes, edges = _merge(contributions)
    node_map = {node.id: node for node in nodes}
    if node_id not in node_map:
        raise GraphNodeNotFoundError("Graph node was not found in the requested scope.")
    resolved_depth = min(max(1, depth), config.GRAPH_MAX_TRAVERSAL_DEPTH)
    resolved_limit = min(limit or config.GRAPH_MAX_NODES, config.GRAPH_MAX_NODES)
    allowed_edges = [edge for edge in edges if not edge_types or edge.type in edge_types]
    adjacency: dict[str, list[tuple[str, GraphEdge]]] = {}
    for edge in allowed_edges:
        adjacency.setdefault(edge.source, []).append((edge.target, edge))
        adjacency.setdefault(edge.target, []).append((edge.source, edge))
    visited = {node_id}
    used_edges: dict[str, GraphEdge] = {}
    queue: deque[tuple[str, int]] = deque([(node_id, 0)])
    truncated = False
    while queue:
        current, current_depth = queue.popleft()
        if current_depth >= resolved_depth:
            continue
        for neighbor, edge in adjacency.get(current, []):
            if len(visited) >= resolved_limit and neighbor not in visited:
                truncated = True
                continue
            used_edges[edge.id] = edge
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, current_depth + 1))
    selected_nodes = sorted((node_map[value] for value in visited), key=lambda item: item.id)
    selected_edges = sorted(used_edges.values(), key=lambda item: item.id)[: config.GRAPH_MAX_EDGES]
    return GraphNeighborsResponse(
        document_id=document_id,
        scope=scope,
        version_group_id=group_id,
        root_node_id=node_id,
        depth=resolved_depth,
        nodes=selected_nodes,
        edges=selected_edges,
        diagnostics=graph_diagnostics(selected_nodes, selected_edges),
        truncated=truncated or len(used_edges) > config.GRAPH_MAX_EDGES,
        metadata={"node_count": len(selected_nodes), "edge_count": len(selected_edges)},
    )


def _connected_nodes(
    graph: GraphResponse,
    node_id: str,
    edge_type: GraphEdgeType,
    *,
    incoming: bool,
    expected_type: GraphNodeType,
) -> list[GraphNode]:
    node_map = {node.id: node for node in graph.nodes}
    connected_ids = {
        edge.source if incoming else edge.target
        for edge in graph.edges
        if edge.type == edge_type
        and (edge.target == node_id if incoming else edge.source == node_id)
    }
    return sorted(
        (node_map[value] for value in connected_ids if value in node_map and node_map[value].type == expected_type),
        key=lambda item: item.id,
    )


def get_evidence_for_finding(document_id: str, node_id: str, *, scope: str = "document") -> list[GraphNode]:
    """Return only validated evidence explicitly connected to a finding."""
    graph = get_graph(document_id, scope=scope)
    return _connected_nodes(
        graph, node_id, GraphEdgeType.SUPPORTS,
        incoming=True, expected_type=GraphNodeType.EVIDENCE,
    )


def get_recommendations_for_risk(document_id: str, node_id: str, *, scope: str = "document") -> list[GraphNode]:
    """Return recommendations explicitly attached to a risk."""
    graph = get_graph(document_id, scope=scope)
    return _connected_nodes(
        graph, node_id, GraphEdgeType.ADDRESSED_BY,
        incoming=False, expected_type=GraphNodeType.RECOMMENDATION,
    )


def get_unresolved_risks(document_id: str) -> list[GraphNode]:
    """Return risks explicitly persisting in a series without a later resolution edge."""
    graph = get_graph(document_id, scope="series")
    outgoing: dict[str, set[GraphEdgeType]] = {}
    for edge in graph.edges:
        outgoing.setdefault(edge.source, set()).add(edge.type)
    return [
        node for node in graph.nodes
        if node.type == GraphNodeType.RISK
        and GraphEdgeType.PERSISTS_IN in outgoing.get(node.id, set())
        and GraphEdgeType.RESOLVED_IN not in outgoing.get(node.id, set())
    ]


def get_persistent_assumptions(document_id: str) -> list[GraphNode]:
    """Return assumptions explicitly classified as persistent by comparison output."""
    graph = get_graph(document_id, scope="series")
    persistent_ids = {
        edge.source for edge in graph.edges if edge.type == GraphEdgeType.PERSISTS_IN
    }
    return [
        node for node in graph.nodes
        if node.type == GraphNodeType.ASSUMPTION and node.id in persistent_ids
    ]


def get_lifecycle(document_id: str, node_id: str) -> list[GraphEdge]:
    """Return explicit version lifecycle edges for a risk or recommendation."""
    graph = get_graph(document_id, scope="series")
    lifecycle_types = {
        GraphEdgeType.PRESENT_IN, GraphEdgeType.INTRODUCED_IN,
        GraphEdgeType.PERSISTS_IN, GraphEdgeType.RESOLVED_IN,
        GraphEdgeType.PARTIALLY_ADDRESSED_IN, GraphEdgeType.ADDRESSED_IN,
        GraphEdgeType.NOT_ADDRESSED_IN, GraphEdgeType.NO_LONGER_APPLICABLE_IN,
    }
    return [
        edge for edge in graph.edges
        if edge.source == node_id and edge.type in lifecycle_types
    ]
