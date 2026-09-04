import type { NormalizedDocument } from "../types/api";

function readableKey(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

function renderMetadata(value: unknown): string {
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

export function DocumentView({ document }: { document: NormalizedDocument }) {
  const metadata = Object.entries(document.metadata);
  const multimodal = typeof document.metadata.multimodal === "object"
    && document.metadata.multimodal !== null
    && !Array.isArray(document.metadata.multimodal)
    ? document.metadata.multimodal as Record<string, unknown>
    : null;
  const multimodalStatus = typeof multimodal?.status === "string" ? multimodal.status : null;

  return (
    <div className="view-stack">
      {multimodalStatus && (
        <div className={`multimodal-banner ${multimodalStatus}`} role="status">
          <strong>
            {multimodalStatus === "completed" && "Visual analysis complete"}
            {multimodalStatus === "partial" && "Visual analysis partially complete"}
            {multimodalStatus === "unavailable" && "Visual analysis unavailable"}
          </strong>
          <span>
            {multimodalStatus === "completed"
              ? "Visual evidence is included in the normalized document."
              : multimodalStatus === "partial"
                ? "Available visual evidence was kept; some items could not be analyzed."
                : "No provider-derived visual evidence was added."}
          </span>
        </div>
      )}
      {document.warnings.length > 0 && (
        <div className="warning-banner" role="status">
          <strong>Processing note</strong>
          <ul>{document.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
        </div>
      )}

      <section className="overview-grid">
        <article className="overview-card primary-overview">
          <span className="eyebrow">Document overview</span>
          <h2>{document.filename}</h2>
          <p>{document.content.length} extracted content block{document.content.length === 1 ? "" : "s"}</p>
        </article>
        <article className="overview-card metric-card">
          <span>Format</span><strong>{document.file_type.toUpperCase()}</strong>
        </article>
        <article className="overview-card metric-card">
          <span>Status</span><strong className="status-text">{readableKey(document.status)}</strong>
        </article>
      </section>

      {metadata.length > 0 && (
        <section className="content-section">
          <div className="section-heading"><span className="eyebrow">File facts</span><h2>Metadata</h2></div>
          <dl className="metadata-grid">
            {metadata.map(([key, value]) => (
              <div key={key}><dt>{readableKey(key)}</dt><dd>{renderMetadata(value)}</dd></div>
            ))}
          </dl>
        </section>
      )}

      <section className="content-section">
        <div className="section-heading">
          <span className="eyebrow">Extracted source</span>
          <h2>Document content</h2>
          <p>This is the normalized content the analysis system can ground its findings in.</p>
        </div>
        {document.content.length === 0 ? (
          <p className="muted-copy">No analyzable text was extracted from this document.</p>
        ) : (
          <div className="document-blocks">
            {document.content.map((block, index) => (
              <article className="document-block" key={`${block.type}-${block.location}-${index}`}>
                <span className="block-label">{readableKey(block.type)} {block.location}</span>
                <p>{block.text || "No text extracted for this block."}</p>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
