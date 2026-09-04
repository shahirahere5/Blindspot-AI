import { useEffect, useMemo, useState } from "react";
import { ApiError, compareDocumentVersions, getVersionHistory, uploadDocumentVersion } from "../services/api";
import type { ComparisonFinding, ComparisonReport, NormalizedDocument, VersionEntry, VersionHistory } from "../types/api";

function message(error: unknown) {
  return error instanceof ApiError ? error.message : "An unexpected error occurred. Please try again.";
}

function sourceName(version: VersionEntry, location: number) {
  const unit = version.file_type === "pdf" ? "Page" : version.file_type === "pptx" ? "Slide" : "Source";
  return `V${version.version_number} · ${unit} ${location}`;
}

function FindingCard({ finding, oldVersion, newVersion }: {
  finding: ComparisonFinding; oldVersion: VersionEntry; newVersion: VersionEntry;
}) {
  return <article className="comparison-finding">
    <h4>{finding.title}</h4><p>{finding.description}</p>
    {(finding.old_evidence || finding.new_evidence) && <div className="evidence-pair">
      {finding.old_evidence && <div><strong>V{oldVersion.version_number} evidence</strong><p>{finding.old_evidence}</p></div>}
      {finding.new_evidence && <div><strong>V{newVersion.version_number} evidence</strong><p>{finding.new_evidence}</p></div>}
    </div>}
    <div className="source-row">
      {finding.old_source_locations.map((location) => <span className="source-chip old" key={`old-${location}`}>{sourceName(oldVersion, location)}</span>)}
      {finding.new_source_locations.map((location) => <span className="source-chip new" key={`new-${location}`}>{sourceName(newVersion, location)}</span>)}
    </div>
  </article>;
}

const sections: Array<[keyof ComparisonReport, string]> = [
  ["new_risks", "New risks"], ["resolved_risks", "Resolved risks"], ["persistent_risks", "Persistent risks"],
  ["new_assumptions", "New assumptions"], ["resolved_assumptions", "Resolved assumptions"], ["persistent_assumptions", "Persistent assumptions"],
  ["new_biases", "New biases"], ["resolved_biases", "Resolved biases"], ["persistent_biases", "Persistent biases"],
  ["new_missing_perspectives", "New missing perspectives"], ["resolved_missing_perspectives", "Resolved missing perspectives"],
  ["persistent_missing_perspectives", "Persistent missing perspectives"], ["new_questions", "New questions"],
  ["resolved_questions", "Resolved questions"], ["persistent_questions", "Persistent questions"],
  ["recommendation_progress", "Recommendation progress"], ["meaningful_additions", "Meaningful additions"],
  ["meaningful_removals", "Meaningful removals"], ["regressions", "Regressions"],
];

export function VersionView({ document }: { document: NormalizedDocument }) {
  const [history, setHistory] = useState<VersionHistory | null>(null);
  const [oldId, setOldId] = useState("");
  const [newId, setNewId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [label, setLabel] = useState("");
  const [notes, setNotes] = useState("");
  const [comparison, setComparison] = useState<ComparisonReport | null>(null);
  const [busy, setBusy] = useState<"history" | "upload" | "compare" | null>("history");
  const [error, setError] = useState<string | null>(null);

  const loadHistory = async () => {
    setBusy("history"); setError(null);
    try {
      const loaded = await getVersionHistory(document.document_id);
      setHistory(loaded);
      setOldId((current) => current || loaded.versions[0]?.document_id || "");
      setNewId((current) => current || loaded.versions.at(-1)?.document_id || "");
    } catch (caught) { setError(message(caught)); }
    finally { setBusy(null); }
  };

  useEffect(() => { void loadHistory(); }, [document.document_id]);
  const latest = history?.versions.at(-1);
  const versionById = useMemo(() => new Map(history?.versions.map((item) => [item.document_id, item]) ?? []), [history]);

  const upload = async (event: React.FormEvent) => {
    event.preventDefault(); if (!file || !latest) return;
    setBusy("upload"); setError(null);
    try {
      await uploadDocumentVersion(latest.document_id, file, label, notes);
      setFile(null); setLabel(""); setNotes(""); setComparison(null);
      const loaded = await getVersionHistory(document.document_id);
      setHistory(loaded); setOldId(loaded.versions[0]?.document_id ?? ""); setNewId(loaded.versions.at(-1)?.document_id ?? "");
    } catch (caught) { setError(message(caught)); }
    finally { setBusy(null); }
  };

  const compare = async () => {
    setBusy("compare"); setError(null); setComparison(null);
    try { setComparison(await compareDocumentVersions(oldId, newId)); }
    catch (caught) { setError(message(caught)); }
    finally { setBusy(null); }
  };

  const oldVersion = versionById.get(oldId);
  const newVersion = versionById.get(newId);
  return <div className="view-stack version-view">
    <section className="content-section">
      <div className="section-heading"><span className="eyebrow">Version memory</span><h2>Document history</h2><p>Relationships are created only through an explicit new-version upload.</p></div>
      {busy === "history" && <p role="status">Loading version history…</p>}
      {error && <div className="error-banner" role="alert"><strong>Could not complete the request</strong><p>{error}</p></div>}
      {history && <ol className="version-timeline">
        {history.versions.map((version) => <li key={version.document_id}>
          <span className="version-number">V{version.version_number}</span><div><strong>{version.label || version.filename}</strong>
          <p>{new Date(version.created_at).toLocaleString()} · {version.document_id}</p>{version.notes && <p>{version.notes}</p>}</div>
        </li>)}
      </ol>}
    </section>

    {latest && <section className="content-section">
      <div className="section-heading"><span className="eyebrow">Continue the family</span><h2>Upload a new version</h2></div>
      <form className="version-upload" onSubmit={upload}>
        <label>Revision file<input type="file" required onChange={(event) => setFile(event.target.files?.[0] ?? null)} /></label>
        <label>Version label <span>(optional)</span><input maxLength={120} value={label} onChange={(event) => setLabel(event.target.value)} placeholder="e.g. Board review" /></label>
        <label>Notes <span>(optional)</span><textarea maxLength={2000} value={notes} onChange={(event) => setNotes(event.target.value)} /></label>
        <button type="submit" className="button button-primary" disabled={!file || busy !== null}>{busy === "upload" ? "Uploading version…" : `Upload after V${latest.version_number}`}</button>
      </form>
    </section>}

    {history && history.versions.length > 1 && <section className="content-section">
      <div className="section-heading"><span className="eyebrow">Comparative blind spots</span><h2>Compare versions</h2></div>
      <div className="comparison-controls">
        <label>Older version<select value={oldId} onChange={(event) => setOldId(event.target.value)}>{history.versions.slice(0, -1).map((version) => <option value={version.document_id} key={version.document_id}>V{version.version_number} · {version.label || version.filename}</option>)}</select></label>
        <label>Newer version<select value={newId} onChange={(event) => setNewId(event.target.value)}>{history.versions.slice(1).map((version) => <option value={version.document_id} key={version.document_id}>V{version.version_number} · {version.label || version.filename}</option>)}</select></label>
        <button className="button button-primary" onClick={compare} disabled={!oldId || !newId || oldId === newId || busy !== null}>{busy === "compare" ? "Comparing…" : "Compare blind spots"}</button>
      </div>
    </section>}

    {comparison && oldVersion && newVersion && <section className="content-section comparison-results">
      <div className="section-heading"><span className="eyebrow">V{comparison.old_version_number} → V{comparison.new_version_number}</span><h2>{comparison.summary}</h2><p>{comparison.overall_change_assessment}</p></div>
      <div className="diff-metrics"><span><strong>{comparison.structural_diff.added_blocks}</strong> added</span><span><strong>{comparison.structural_diff.removed_blocks}</strong> removed</span><span><strong>{comparison.structural_diff.unchanged_blocks}</strong> unchanged</span></div>
      {sections.map(([key, title]) => {
        const findings = comparison[key];
        if (!Array.isArray(findings) || findings.length === 0) return null;
        return <div className="comparison-section" key={key}><h3>{title}</h3>{(findings as ComparisonFinding[]).map((finding, index) => <FindingCard key={`${finding.title}-${index}`} finding={finding} oldVersion={oldVersion} newVersion={newVersion} />)}</div>;
      })}
    </section>}
  </div>;
}
