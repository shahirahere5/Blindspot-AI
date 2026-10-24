"""Phase 9 grounded graph ingestion, querying, lifecycle, and isolation tests."""

from __future__ import annotations

from schemas.analysis import AnalysisReport
from schemas.comparison import ComparisonReport, StructuralDiff
from schemas.debate import AgentAnalysis, AgentFinding, AgentRole, DebateResult
from schemas.document import ContentBlock, ContentBlockType
from schemas.graph import (
    GraphDiagnosticType,
    GraphEdge,
    GraphEdgeType,
    GraphNode,
    GraphNodeType,
    GraphOrigin,
)
from services import graph_ingestion_service as ingestion
from services import graph_service
from storage.graph_store import GraphStore
from tests.fakes import FakeAIClient, VALID_ANALYSIS_JSON


def _upload(client, name: str, text: str) -> str:
    response = client.post(
        "/api/documents/upload",
        files={"file": (name, text.encode(), "text/plain")},
    )
    assert response.status_code == 200
    return response.json()["document_id"]


def _analysis(document_id: str, risk_title: str = "Data exposure") -> AnalysisReport:
    return AnalysisReport.model_validate({
        "document_id": document_id,
        "summary": "Security review",
        "overall_assessment": "Mitigate before launch.",
        "risks": [{
            "title": risk_title,
            "description": "Confidential data may be exposed.",
            "severity": "high",
            "evidence": "No encryption strategy has been defined.",
            "source_locations": [1, 99],
            "recommendation": "Encrypt documents at rest.",
        }, {
            "title": "Unowned outage",
            "description": "No owner is assigned.",
            "severity": "medium",
            "evidence": "",
            "source_locations": [],
            "recommendation": "",
        }],
        "assumptions": [{
            "title": "Cloud is secure",
            "description": "The plan assumes default cloud security is sufficient.",
            "confidence": "low",
            "evidence": "",
            "source_locations": [99],
            "why_it_matters": "This controls the primary risk.",
        }],
        "biases": [],
        "missing_perspectives": [{
            "perspective": "Security operations",
            "description": "No security operator contributed.",
            "why_it_matters": "Operational controls are missing.",
            "questions_to_consider": ["Who owns incident response?"],
        }],
        "unanswered_questions": [{
            "question": "Who owns incident response?",
            "importance": "high",
            "reason": "Ownership is absent.",
        }],
        "recommendations": [],
        "metadata": {},
    })


def test_analysis_ingestion_builds_grounded_typed_graph_and_diagnostics(client):
    document_id = _upload(client, "security.txt", "No encryption strategy has been defined.")
    ingestion.ingest_analysis(_analysis(document_id))
    graph = graph_service.get_graph(document_id)

    types = {node.type for node in graph.nodes}
    assert {GraphNodeType.DOCUMENT, GraphNodeType.RISK, GraphNodeType.ASSUMPTION,
            GraphNodeType.EVIDENCE, GraphNodeType.SOURCE, GraphNodeType.RECOMMENDATION} <= types
    assert GraphEdgeType.SUPPORTS in {edge.type for edge in graph.edges}
    assert GraphEdgeType.ADDRESSED_BY in {edge.type for edge in graph.edges}
    evidence = next(node for node in graph.nodes if node.type == GraphNodeType.EVIDENCE)
    assert evidence.metadata["source_locations"] == [1]
    assert 99 not in evidence.metadata["source_locations"]
    source = next(node for node in graph.nodes if node.type == GraphNodeType.SOURCE)
    assert source.metadata == {
        "document_id": document_id,
        "source_type": "text",
        "source_location": 1,
        "version_number": None,
        "visual_derived": False,
    }
    diagnostic_types = {item.type for item in graph.diagnostics}
    assert GraphDiagnosticType.ORPHAN_RISK in diagnostic_types
    assert GraphDiagnosticType.UNMITIGATED_RISK in diagnostic_types
    assert GraphDiagnosticType.UNSUPPORTED_ASSUMPTION in diagnostic_types
    risk = next(node for node in graph.nodes if node.type == GraphNodeType.RISK and node.label == "Data exposure")
    assert [node.type for node in graph_service.get_evidence_for_finding(document_id, risk.id)] == [GraphNodeType.EVIDENCE]
    assert [node.type for node in graph_service.get_recommendations_for_risk(document_id, risk.id)] == [GraphNodeType.RECOMMENDATION]


def test_duplicate_ingestion_is_idempotent_and_regeneration_replaces_stale_nodes(client):
    document_id = _upload(client, "plan.txt", "No encryption strategy has been defined.")
    report = _analysis(document_id)
    ingestion.ingest_analysis(report)
    first = graph_service.get_graph(document_id)
    ingestion.ingest_analysis(report)
    second = graph_service.get_graph(document_id)
    assert [node.id for node in first.nodes] == [node.id for node in second.nodes]
    assert [edge.id for edge in first.edges] == [edge.id for edge in second.edges]

    ingestion.ingest_analysis(_analysis(document_id, "Revised exposure"))
    regenerated = graph_service.get_graph(document_id)
    assert "Data exposure" not in {node.label for node in regenerated.nodes}
    assert "Revised exposure" in {node.label for node in regenerated.nodes}


def test_graph_persists_across_store_reload(client):
    document_id = _upload(client, "plan.txt", "No encryption strategy has been defined.")
    ingestion.ingest_analysis(_analysis(document_id))
    restored = GraphStore(ingestion.graph_store.storage_dir)
    graph = graph_service.get_graph(
        document_id, store=restored, versions=ingestion.version_store
    )
    assert any(node.type == GraphNodeType.RISK for node in graph.nodes)


def test_document_scope_excludes_unrelated_documents(client):
    first = _upload(client, "security.txt", "No encryption strategy has been defined.")
    second = _upload(client, "restaurant.txt", "Open a second restaurant downtown.")
    ingestion.ingest_analysis(_analysis(first, "Cybersecurity risk"))
    ingestion.ingest_analysis(_analysis(second, "Lease risk"))
    graph = graph_service.get_graph(second)
    assert all(first not in node.document_ids for node in graph.nodes)
    assert "Cybersecurity risk" not in {node.label for node in graph.nodes}


def test_neighbor_traversal_is_bounded_and_validated(client, monkeypatch):
    document_id = _upload(client, "plan.txt", "No encryption strategy has been defined.")
    ingestion.ingest_analysis(_analysis(document_id))
    graph = graph_service.get_graph(document_id)
    risk = next(node for node in graph.nodes if node.type == GraphNodeType.RISK and node.label == "Data exposure")
    monkeypatch.setattr("config.GRAPH_MAX_TRAVERSAL_DEPTH", 1)
    neighbors = graph_service.get_neighbors(document_id, risk.id, depth=4, limit=3)
    assert neighbors.depth == 1
    assert len(neighbors.nodes) <= 3


def test_debate_agent_attribution_is_explicit(client):
    document_id = _upload(client, "plan.txt", "No encryption strategy has been defined.")
    result = DebateResult(
        document_id=document_id,
        agent_analyses=[AgentAnalysis(
            agent=AgentRole.SECURITY,
            role="Reviews security controls",
            findings=[AgentFinding(
                title="Encryption gap",
                description="Encryption is absent.",
                evidence="No encryption strategy has been defined.",
                source_locations=[1],
            )],
        )],
    )
    ingestion.ingest_debate(result)
    graph = graph_service.get_graph(document_id)
    agent = next(node for node in graph.nodes if node.type == GraphNodeType.AGENT)
    finding = next(node for node in graph.nodes if node.type == GraphNodeType.FINDING)
    assert any(
        edge.source == agent.id and edge.target == finding.id and edge.type == GraphEdgeType.IDENTIFIED
        for edge in graph.edges
    )


def test_multimodal_source_provenance_is_preserved(client):
    document_id = _upload(client, "chart.txt", "Placeholder")
    from services import document_service
    document = document_service.get_document_or_raise(document_id)
    document.content = [ContentBlock(
        type=ContentBlockType.IMAGE,
        location=1,
        text="Visual summary: operating margin declined.",
        extra={"visual_analysis": True},
    )]
    document_service.document_store.save_normalized_document(document)
    report = _analysis(document_id, "Margin risk")
    report.risks[0].evidence = "Operating margin declined."
    report.risks[0].source_locations = [1]
    ingestion.ingest_analysis(report)
    graph = graph_service.get_graph(document_id)
    evidence = next(node for node in graph.nodes if node.type == GraphNodeType.EVIDENCE)
    source = next(node for node in graph.nodes if node.type == GraphNodeType.SOURCE)
    assert evidence.metadata["visual_derived"] is True
    assert source.metadata["source_type"] == "image"
    assert source.metadata["visual_derived"] is True


def test_version_series_lifecycle_and_document_scope(client):
    old_id = _upload(client, "v1.txt", "No security audit is planned.")
    response = client.post(
        f"/api/documents/{old_id}/versions",
        files={"file": ("v2.txt", b"Security audit added.", "text/plain")},
    )
    assert response.status_code == 200
    new_id = response.json()["document_id"]
    group_id = response.json()["version_group_id"]
    report = ComparisonReport(
        old_document_id=old_id,
        new_document_id=new_id,
        version_group_id=group_id,
        old_version_number=1,
        new_version_number=2,
        summary="Security improved.",
        overall_change_assessment="Audit planning resolves one gap.",
        resolved_risks=[{
            "title": "Missing audit",
            "description": "An audit was added.",
            "old_evidence": "No security audit is planned.",
            "new_evidence": "Security audit added.",
            "old_source_locations": [1],
            "new_source_locations": [1],
        }],
        recommendation_progress=[{
            "title": "Plan a security audit",
            "description": "The audit is now planned.",
            "progress_status": "addressed",
            "old_evidence": "No security audit is planned.",
            "new_evidence": "Security audit added.",
            "old_source_locations": [1],
            "new_source_locations": [1],
        }],
        structural_diff=StructuralDiff(
            old_content_blocks=1, new_content_blocks=1, unchanged_blocks=0,
            added_blocks=1, removed_blocks=1,
        ),
    )
    ingestion.ingest_comparison(report)
    document_graph = graph_service.get_graph(new_id, scope="document")
    assert all(old_id not in node.document_ids for node in document_graph.nodes)
    series = graph_service.get_graph(new_id, scope="series")
    edge_types = {edge.type for edge in series.edges}
    assert GraphEdgeType.RESOLVED_IN in edge_types
    assert GraphEdgeType.ADDRESSED_IN in edge_types
    assert {old_id, new_id} <= {doc for node in series.nodes for doc in node.document_ids}
    risk = next(node for node in series.nodes if node.type == GraphNodeType.RISK)
    recommendation = next(node for node in series.nodes if node.type == GraphNodeType.RECOMMENDATION)
    assert GraphEdgeType.RESOLVED_IN in {edge.type for edge in graph_service.get_lifecycle(new_id, risk.id)}
    assert GraphEdgeType.ADDRESSED_IN in {edge.type for edge in graph_service.get_lifecycle(new_id, recommendation.id)}


def test_new_comparison_finding_is_not_present_in_old_version(client):
    old_id = _upload(client, "v1.txt", "Stable plan.")
    response = client.post(
        f"/api/documents/{old_id}/versions",
        files={"file": ("v2.txt", b"A new dependency appears.", "text/plain")},
    )
    new_id = response.json()["document_id"]
    report = ComparisonReport(
        old_document_id=old_id,
        new_document_id=new_id,
        version_group_id=response.json()["version_group_id"],
        old_version_number=1,
        new_version_number=2,
        summary="A risk appeared.",
        overall_change_assessment="One new dependency.",
        new_risks=[{
            "title": "New dependency",
            "description": "A new dependency appears.",
            "old_evidence": "",
            "new_evidence": "A new dependency appears.",
            "old_source_locations": [],
            "new_source_locations": [1],
        }],
        structural_diff=StructuralDiff(
            old_content_blocks=1, new_content_blocks=1, unchanged_blocks=0,
            added_blocks=1, removed_blocks=1,
        ),
    )
    ingestion.ingest_comparison(report)
    series = graph_service.get_graph(new_id, scope="series")
    risk = next(node for node in series.nodes if node.type == GraphNodeType.RISK)
    lifecycle = graph_service.get_lifecycle(new_id, risk.id)
    assert [(edge.type, edge.target) for edge in lifecycle] == [(GraphEdgeType.INTRODUCED_IN, next(node.id for node in series.nodes if new_id in node.document_ids and node.type == GraphNodeType.DOCUMENT))]


def test_graph_api_empty_filtering_neighbors_and_safe_errors(client):
    document_id = _upload(client, "plan.txt", "No encryption strategy has been defined.")
    empty = client.get(f"/api/documents/{document_id}/graph")
    assert empty.status_code == 200
    assert empty.json()["nodes"] == []
    ingestion.ingest_analysis(_analysis(document_id))
    filtered = client.get(
        f"/api/documents/{document_id}/graph",
        params=[("node_type", "risk")],
    )
    assert filtered.status_code == 200
    assert {node["type"] for node in filtered.json()["nodes"]} == {"risk"}
    node_id = filtered.json()["nodes"][0]["id"]
    neighbors = client.get(f"/api/documents/{document_id}/graph/nodes/{node_id}")
    assert neighbors.status_code == 200
    assert neighbors.json()["root_node_id"] == node_id
    assert client.get(f"/api/documents/{document_id}/graph/nodes/not-safe").status_code == 400
    assert client.get("/api/documents/doc_missing/graph").status_code == 404


def test_successful_analysis_endpoint_automatically_updates_graph(
    client, monkeypatch, uploaded_txt_document_id,
):
    import api.analysis as analysis_api

    monkeypatch.setattr(
        analysis_api, "get_ai_client", lambda: FakeAIClient(response_text=VALID_ANALYSIS_JSON)
    )
    response = client.post(f"/api/documents/{uploaded_txt_document_id}/analyze")
    assert response.status_code == 200
    graph = client.get(f"/api/documents/{uploaded_txt_document_id}/graph")
    assert graph.status_code == 200
    assert "risk" in {node["type"] for node in graph.json()["nodes"]}


def test_graph_storage_failure_does_not_break_existing_analysis_contract(
    client, monkeypatch, uploaded_txt_document_id,
):
    import api.analysis as analysis_api

    monkeypatch.setattr(
        analysis_api, "get_ai_client", lambda: FakeAIClient(response_text=VALID_ANALYSIS_JSON)
    )
    monkeypatch.setattr(
        analysis_api, "ingest_analysis", lambda _report: (_ for _ in ()).throw(RuntimeError("private graph path"))
    )
    response = client.post(f"/api/documents/{uploaded_txt_document_id}/analyze")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_stale_recommendation_requires_repeated_latest_non_addressment():
    recommendation = GraphNode(
        id="gn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        type=GraphNodeType.RECOMMENDATION,
        label="Run an audit",
    )
    versions = [
        GraphNode(
            id=f"gn_{value * 32}", type=GraphNodeType.DOCUMENT, label=f"V{number}",
            metadata={"version_number": number},
        )
        for value, number in [("b", 2), ("c", 3)]
    ]
    edges = [
        GraphEdge(
            id=f"ge_{value * 32}", source=recommendation.id, target=version.id,
            type=GraphEdgeType.NOT_ADDRESSED_IN, origin=GraphOrigin.VERSION_COMPARISON,
        )
        for value, version in [("d", versions[0]), ("e", versions[1])]
    ]
    diagnostics = graph_service.graph_diagnostics([recommendation, *versions], edges)
    assert [item.type for item in diagnostics] == [GraphDiagnosticType.STALE_RECOMMENDATION]

    edges[-1].type = GraphEdgeType.ADDRESSED_IN
    assert graph_service.graph_diagnostics([recommendation, *versions], edges) == []
