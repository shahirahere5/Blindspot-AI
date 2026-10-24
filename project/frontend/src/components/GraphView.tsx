import { useEffect, useMemo, useState } from "react";
import { ApiError, getKnowledgeGraph } from "../services/api";
import type {
  GraphEdge,
  GraphNode,
  GraphNodeType,
  KnowledgeGraph,
  NormalizedDocument,
} from "../types/api";

const nodeTypes: Array<[GraphNodeType, string]> = [
  ["document", "Documents"], ["version_group", "Version series"],
  ["source", "Sources"], ["evidence", "Evidence"], ["risk", "Risks"],
  ["assumption", "Assumptions"], ["bias", "Biases"],
  ["missing_perspective", "Missing perspectives"], ["question", "Questions"],
  ["recommendation", "Recommendations"], ["agent", "Agents"], ["finding", "Agent findings"],
];

const column: Record<GraphNodeType, number> = {
  document: 0, version_group: 0, source: 1, evidence: 2, assumption: 3,
  bias: 3, missing_perspective: 3, question: 3, agent: 3, risk: 4,
  finding: 4, recommendation: 5,
};

const relationshipLabels: Record<string, string> = {
  contains: "contains", version_of: "version of", previous_version: "previous version",
  has_source: "has source", supports: "supports", addressed_by: "addressed by",
  identified: "identified", present_in: "present in", introduced_in: "introduced in",
  persists_in: "persists in", resolved_in: "resolved in",
  partially_addressed_in: "partially addressed in", addressed_in: "addressed in",
  not_addressed_in: "not addressed in", no_longer_applicable_in: "no longer applicable in",
};

function errorMessage(error: unknown) {
  return error instanceof ApiError ? error.message : "An unexpected error occurred. Please try again.";
}

function compact(value: unknown): string {
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  if (value === null || value === undefined) return "—";
  return JSON.stringify(value);
}

function readable(value: string) {
  return value.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

interface PositionedNode { node: GraphNode; x: number; y: number }

export function GraphView({ document }: { document: NormalizedDocument }) {
  const [graph, setGraph] = useState<KnowledgeGraph | null>(null);
  const [scope, setScope] = useState<"document" | "series">("document");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [visibleTypes, setVisibleTypes] = useState<Set<GraphNodeType>>(
    () => new Set(nodeTypes.map(([type]) => type)),
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true); setError(null); setSelectedId(null);
    getKnowledgeGraph(document.document_id, scope)
      .then((value) => { if (active) setGraph(value); })
      .catch((caught) => { if (active) { setGraph(null); setError(errorMessage(caught)); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [document.document_id, scope, reload]);

  const visibleNodes = useMemo(
    () => graph?.nodes.filter((node) => visibleTypes.has(node.type)) ?? [],
    [graph, visibleTypes],
  );
  const visibleIds = useMemo(() => new Set(visibleNodes.map((node) => node.id)), [visibleNodes]);
  const visibleEdges = useMemo(
    () => graph?.edges.filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target)) ?? [],
    [graph, visibleIds],
  );
  const positioned = useMemo(() => {
    const rows = new Map<number, number>();
    return visibleNodes.map((node): PositionedNode => {
      const col = column[node.type];
      const row = rows.get(col) ?? 0;
      rows.set(col, row + 1);
      return { node, x: 30 + col * 175, y: 35 + row * 82 };
    });
  }, [visibleNodes]);
  const positions = useMemo(() => new Map(positioned.map((item) => [item.node.id, item])), [positioned]);
  const canvasHeight = Math.max(320, ...positioned.map((item) => item.y + 75));
  const selected = graph?.nodes.find((node) => node.id === selectedId) ?? null;
  const connected = selected && graph
    ? graph.edges.filter((edge) => edge.source === selected.id || edge.target === selected.id)
    : [];
  const nodeMap = useMemo(() => new Map(graph?.nodes.map((node) => [node.id, node]) ?? []), [graph]);

  const toggleType = (type: GraphNodeType) => {
    setVisibleTypes((current) => {
      const next = new Set(current);
      if (next.has(type)) next.delete(type); else next.add(type);
      return next;
    });
  };

  return <div className="view-stack graph-view">
    <section className="content-section graph-header-section">
      <div className="section-heading">
        <span className="eyebrow">Grounded relationships</span>
        <h2>Blind Spot Graph</h2>
        <p>Structured findings are connected deterministically. The graph does not replace document RAG.</p>
      </div>
      <div className="graph-toolbar">
        <div className="scope-toggle" aria-label="Graph scope">
          <button className={scope === "document" ? "active" : ""} onClick={() => setScope("document")}>Current document</button>
          <button className={scope === "series" ? "active" : ""} onClick={() => setScope("series")}>Version series</button>
        </div>
        <button className="button button-secondary" onClick={() => setReload((value) => value + 1)}>Refresh graph</button>
      </div>
    </section>

    {loading && <div className="state-card" role="status"><span className="spinner" /><div><h3>Loading knowledge graph</h3><p>Reading grounded nodes and relationships.</p></div></div>}
    {error && <div className="state-card error-state" role="alert"><span className="state-icon">!</span><div><h3>Graph unavailable</h3><p>{error}</p></div><button className="button button-secondary" onClick={() => setReload((value) => value + 1)}>Retry</button></div>}

    {!loading && !error && graph && graph.nodes.length === 0 && <section className="empty-state graph-empty">
      <span className="eyebrow">No graph data yet</span><h2>Run analysis or debate first</h2>
      <p>Validated results automatically become graph relationships. Version comparisons add lifecycle relationships to the series view.</p>
    </section>}

    {!loading && !error && graph && graph.nodes.length > 0 && <>
      <section className="content-section graph-filters">
        <div><strong>Filter node types</strong><span>{visibleNodes.length} of {graph.nodes.length} nodes visible</span></div>
        <div className="filter-chips">
          {nodeTypes.map(([type, label]) => <label key={type} className={visibleTypes.has(type) ? "selected" : ""}>
            <input type="checkbox" checked={visibleTypes.has(type)} onChange={() => toggleType(type)} />{label}
          </label>)}
        </div>
      </section>

      {graph.truncated && <div className="warning-banner" role="status"><strong>Graph limited</strong><span>The backend applied its safety limit.</span></div>}

      <div className="graph-layout">
        <section className="graph-canvas-panel" aria-label="Knowledge graph visualization">
          {positioned.length === 0 ? <p className="muted-copy">No nodes match the selected filters.</p> : <svg viewBox={`0 0 1080 ${canvasHeight}`} role="img" aria-label={`${positioned.length} graph nodes and ${visibleEdges.length} relationships`}>
            <defs><marker id="graph-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" /></marker></defs>
            {visibleEdges.map((edge) => {
              const from = positions.get(edge.source); const to = positions.get(edge.target);
              if (!from || !to) return null;
              const active = selectedId === edge.source || selectedId === edge.target;
              return <g key={edge.id} className={active ? "graph-edge active" : "graph-edge"}>
                <line x1={from.x + 145} y1={from.y + 25} x2={to.x} y2={to.y + 25} markerEnd="url(#graph-arrow)" />
                <title>{relationshipLabels[edge.type] ?? edge.type}</title>
                {active && <text x={(from.x + to.x + 145) / 2} y={(from.y + to.y) / 2 + 18}>{relationshipLabels[edge.type] ?? edge.type}</text>}
              </g>;
            })}
            {positioned.map(({ node, x, y }) => <g key={node.id} role="button" tabIndex={0}
              aria-label={`${readable(node.type)}: ${node.label}`}
              className={`graph-node node-${node.type}${selectedId === node.id ? " selected" : ""}`}
              transform={`translate(${x} ${y})`} onClick={() => setSelectedId(node.id)}
              onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelectedId(node.id); } }}>
              <rect width="145" height="52" rx="4" /><text className="node-type" x="10" y="16">{readable(node.type)}</text>
              <text className="node-label" x="10" y="36">{node.label.length > 20 ? `${node.label.slice(0, 19)}…` : node.label}</text>
            </g>)}
          </svg>}
        </section>

        <aside className="graph-details" aria-live="polite">
          {!selected && <div className="details-placeholder"><span className="eyebrow">Node details</span><h3>Select a node</h3><p>Use click, Tab, and Enter to inspect provenance and connected relationships.</p></div>}
          {selected && <>
            <span className={`node-badge node-${selected.type}`}>{readable(selected.type)}</span>
            <h3>{selected.label}</h3><p>{selected.description || "No additional description."}</p>
            <dl>
              <div><dt>Origin</dt><dd>{selected.origins.map(readable).join(", ")}</dd></div>
              <div><dt>Documents</dt><dd>{selected.document_ids.join(", ")}</dd></div>
              {Object.entries(selected.metadata).map(([key, value]) => <div key={key}><dt>{readable(key)}</dt><dd>{compact(value)}</dd></div>)}
            </dl>
            <h4>Connected relationships</h4>
            {connected.length === 0 ? <p className="muted-copy">No visible connections.</p> : <ul className="relationship-list">
              {connected.map((edge: GraphEdge) => {
                const otherId = edge.source === selected.id ? edge.target : edge.source;
                const other = nodeMap.get(otherId);
                return <li key={edge.id}><button onClick={() => setSelectedId(otherId)}>
                  <strong>{relationshipLabels[edge.type] ?? edge.type}</strong><span>{other?.label ?? "Unknown node"}</span>
                </button></li>;
              })}
            </ul>}
          </>}
        </aside>
      </div>

      <section className="content-section graph-diagnostics">
        <div className="section-heading"><span className="eyebrow">What am I missing?</span><h2>Graph diagnostics</h2><p>Deterministic checks based only on explicit relationships.</p></div>
        {graph.diagnostics.length === 0 ? <p className="muted-copy">No graph-based warnings were found.</p> : <div className="diagnostic-grid">
          {graph.diagnostics.map((item, index) => <button key={`${item.type}-${item.node_id}-${index}`} onClick={() => setSelectedId(item.node_id)}>
            <span>{readable(item.type)}</span><strong>{item.title}</strong><p>{item.description}</p>
          </button>)}
        </div>}
      </section>

      {scope === "series" && <section className="content-section lifecycle-section">
        <div className="section-heading"><span className="eyebrow">Version outcomes</span><h2>Lifecycle relationships</h2></div>
        {graph.edges.filter((edge) => edge.type.endsWith("_in") || edge.type === "present_in").length === 0
          ? <p className="muted-copy">Run a version comparison to add explicit lifecycle relationships.</p>
          : <ul>{graph.edges.filter((edge) => edge.type.endsWith("_in") || edge.type === "present_in").map((edge) => <li key={edge.id}>
            <button onClick={() => setSelectedId(edge.source)}>{nodeMap.get(edge.source)?.label ?? "Finding"}</button>
            <span>{relationshipLabels[edge.type]}</span><strong>{nodeMap.get(edge.target)?.label ?? "Version"}</strong>
          </li>)}</ul>}
      </section>}
    </>}
  </div>;
}
