import type { AnalysisReport, NormalizedDocument } from "../types/api";
import { EmptyState, ErrorState, LoadingState } from "./States";
import { SourceReferences } from "./SourceReferences";

interface AnalysisViewProps {
  document: NormalizedDocument;
  report: AnalysisReport | null;
  isLoading: boolean;
  error: string | null;
  onAnalyze: () => void;
}

function badgeClass(level: string): string {
  return `level-badge level-${level}`;
}

export function AnalysisView({ document, report, isLoading, error, onAnalyze }: AnalysisViewProps) {
  if (isLoading) {
    return <LoadingState title="Analyzing blind spots" detail="The AI is reviewing the document and validating source references." />;
  }
  if (error) return <ErrorState message={error} onRetry={onAnalyze} />;
  if (!report) {
    return (
      <EmptyState
        eyebrow="Single-pass review"
        title="Reveal the first layer of blind spots"
        detail="Run a grounded analysis of risks, assumptions, biases, missing perspectives, questions, and recommendations."
        actionLabel="Run analysis"
        onAction={onAnalyze}
      />
    );
  }

  return (
    <div className="view-stack">
      <section className="report-hero">
        <div><span className="eyebrow">Analysis complete</span><h2>Executive readout</h2></div>
        {report.metadata.rag_enabled === true && <span className="grounded-badge">RAG grounded</span>}
        <p className="report-summary">{report.summary || "No summary was returned."}</p>
        <div className="assessment"><span>Overall assessment</span><p>{report.overall_assessment || "No overall assessment was returned."}</p></div>
      </section>

      <ReportSection title="Risks" count={report.risks.length} tone="coral">
        {report.risks.map((risk, index) => (
          <article className="finding-card" key={`${risk.title}-${index}`}>
            <div className="finding-heading"><h3>{risk.title}</h3><span className={badgeClass(risk.severity)}>{risk.severity}</span></div>
            <p>{risk.description}</p>
            {risk.evidence && <blockquote><span>Evidence</span>{risk.evidence}</blockquote>}
            <SourceReferences locations={risk.source_locations} document={document} />
            {risk.recommendation && <p className="action-note"><strong>Response:</strong> {risk.recommendation}</p>}
          </article>
        ))}
      </ReportSection>

      <ReportSection title="Assumptions" count={report.assumptions.length} tone="gold">
        {report.assumptions.map((item, index) => (
          <article className="finding-card" key={`${item.title}-${index}`}>
            <div className="finding-heading"><h3>{item.title}</h3><span className={badgeClass(item.confidence)}>{item.confidence} confidence</span></div>
            <p>{item.description}</p>
            {item.evidence && <blockquote><span>Evidence</span>{item.evidence}</blockquote>}
            <SourceReferences locations={item.source_locations} document={document} />
            {item.why_it_matters && <p className="action-note"><strong>Why it matters:</strong> {item.why_it_matters}</p>}
          </article>
        ))}
      </ReportSection>

      <ReportSection title="Biases" count={report.biases.length} tone="violet">
        {report.biases.map((item, index) => (
          <article className="finding-card" key={`${item.title}-${index}`}>
            <h3>{item.title}</h3><p>{item.description}</p>
            {item.evidence && <blockquote><span>Evidence</span>{item.evidence}</blockquote>}
            <SourceReferences locations={item.source_locations} document={document} />
            {item.recommendation && <p className="action-note"><strong>Response:</strong> {item.recommendation}</p>}
          </article>
        ))}
      </ReportSection>

      <div className="two-column-sections">
        <ReportSection title="Missing perspectives" count={report.missing_perspectives.length} tone="blue">
          {report.missing_perspectives.map((item, index) => (
            <article className="finding-card compact-card" key={`${item.perspective}-${index}`}>
              <h3>{item.perspective}</h3><p>{item.description}</p>
              {item.why_it_matters && <p className="action-note">{item.why_it_matters}</p>}
              {item.questions_to_consider.length > 0 && <ul>{item.questions_to_consider.map((question) => <li key={question}>{question}</li>)}</ul>}
            </article>
          ))}
        </ReportSection>
        <ReportSection title="Unanswered questions" count={report.unanswered_questions.length} tone="ink">
          {report.unanswered_questions.map((item, index) => (
            <article className="finding-card compact-card" key={`${item.question}-${index}`}>
              <div className="finding-heading"><h3>{item.question}</h3><span className={badgeClass(item.importance)}>{item.importance}</span></div>
              {item.reason && <p>{item.reason}</p>}
            </article>
          ))}
        </ReportSection>
      </div>

      <ReportSection title="Recommendations" count={report.recommendations.length} tone="green">
        <div className="recommendation-list">
          {report.recommendations.map((item, index) => (
            <article className="recommendation-card" key={`${item.title}-${index}`}>
              <span className="recommendation-number">{String(index + 1).padStart(2, "0")}</span>
              <div><div className="finding-heading"><h3>{item.title}</h3><span className={badgeClass(item.priority)}>{item.priority}</span></div><p>{item.description}</p></div>
            </article>
          ))}
        </div>
      </ReportSection>
    </div>
  );
}

function ReportSection({ title, count, tone, children }: { title: string; count: number; tone: string; children: React.ReactNode }) {
  return (
    <section className={`content-section report-section tone-${tone}`}>
      <div className="section-heading horizontal-heading"><h2>{title}</h2><span>{count}</span></div>
      {count === 0 ? <p className="muted-copy">No {title.toLowerCase()} were returned.</p> : <div className="finding-grid">{children}</div>}
    </section>
  );
}
