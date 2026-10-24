import type { AgentAnalysis, DebateResult, NormalizedDocument } from "../types/api";
import { EmptyState, ErrorState, LoadingState } from "./States";
import { SourceReferences } from "./SourceReferences";

interface DebateViewProps {
  document: NormalizedDocument;
  debate: DebateResult | null;
  isLoading: boolean;
  error: string | null;
  onDebate: () => void;
}

const AGENT_NAMES: Record<AgentAnalysis["agent"], string> = {
  optimist: "Optimist",
  skeptic: "Skeptic",
  security: "Security",
  financial: "Financial",
  ethics: "Ethics",
  legal: "Legal",
};

export function DebateView({ document, debate, isLoading, error, onDebate }: DebateViewProps) {
  if (isLoading) {
    return <LoadingState title="Convening the agent panel" detail="Six specialist agents are reviewing the evidence before the moderator reconciles their findings." />;
  }
  if (error) return <ErrorState message={error} onRetry={onDebate} />;
  if (!debate) {
    return (
      <EmptyState
        eyebrow="Multi-agent review"
        title="Put the decision under constructive pressure"
        detail="Convene Optimist, Skeptic, Security, Financial, Ethics, and Legal perspectives, followed by a moderator synthesis."
        actionLabel="Start agent debate"
        onAction={onDebate}
      />
    );
  }

  return (
    <div className="view-stack">
      <section className="report-hero debate-hero">
        <div><span className="eyebrow">Moderator synthesis</span><h2>Where the panel landed</h2></div>
        <p className="report-summary">{debate.overall_assessment || "No overall assessment was returned."}</p>
        <div className="consensus-grid">
          <ConsensusList title="Agreements" items={debate.agreements} />
          <ConsensusList title="Disagreements" items={debate.disagreements} />
          <ConsensusList title="Final blind spots" items={debate.final_blind_spots} />
        </div>
      </section>

      <section className="content-section">
        <div className="section-heading"><span className="eyebrow">Independent perspectives</span><h2>Agent panel</h2></div>
        <div className="agent-grid">
          {debate.agent_analyses.map((agent) => (
            <article className={`agent-card agent-${agent.agent}`} key={agent.agent}>
              <div className="agent-heading">
                <span className="agent-monogram">{AGENT_NAMES[agent.agent].slice(0, 2)}</span>
                <div><h3>{AGENT_NAMES[agent.agent]}</h3><p>{agent.role}</p></div>
                <span className={`agent-status status-${agent.status}`}>{agent.status}</span>
              </div>
              {agent.status === "failed" ? (
                <p className="agent-error">{agent.error || "This agent could not complete its review."}</p>
              ) : (
                <>
                  <p className="agent-summary">{agent.summary || "No summary returned."}</p>
                  {agent.findings.map((finding, index) => (
                    <div className="agent-finding" key={`${finding.title}-${index}`}>
                      <div><strong>{finding.title}</strong><span className={`level-badge level-${finding.severity}`}>{finding.severity}</span></div>
                      <p>{finding.description}</p>
                      {finding.evidence && <small>{finding.evidence}</small>}
                      <SourceReferences locations={finding.source_locations} document={document} />
                      {finding.recommendation && <p className="action-note">{finding.recommendation}</p>}
                    </div>
                  ))}
                  <span className="confidence-line">Confidence · {agent.confidence}</span>
                </>
              )}
            </article>
          ))}
        </div>
      </section>

      <section className="content-section moderator-findings">
        <div className="section-heading"><span className="eyebrow">Reconciled findings</span><h2>Final risk register</h2></div>
        {debate.final_risks.length === 0 ? <p className="muted-copy">No final risks were returned.</p> : (
          <div className="finding-grid">
            {debate.final_risks.map((risk, index) => (
              <article className="finding-card" key={`${risk.title}-${index}`}>
                <div className="finding-heading"><h3>{risk.title}</h3><span className={`level-badge level-${risk.severity}`}>{risk.severity}</span></div>
                <p>{risk.description}</p>
                {risk.evidence && <blockquote><span>Evidence</span>{risk.evidence}</blockquote>}
                <SourceReferences locations={risk.source_locations} document={document} />
                {risk.recommendation && <p className="action-note"><strong>Response:</strong> {risk.recommendation}</p>}
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="content-section">
        <div className="section-heading"><span className="eyebrow">Next moves</span><h2>Moderator recommendations</h2></div>
        {debate.recommendations.length === 0 ? <p className="muted-copy">No recommendations were returned.</p> : (
          <div className="recommendation-list">
            {debate.recommendations.map((item, index) => (
              <article className="recommendation-card" key={`${item.title}-${index}`}>
                <span className="recommendation-number">{String(index + 1).padStart(2, "0")}</span>
                <div><div className="finding-heading"><h3>{item.title}</h3><span className={`level-badge level-${item.priority}`}>{item.priority}</span></div><p>{item.description}</p></div>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function ConsensusList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="consensus-card"><h3>{title}</h3>{items.length === 0 ? <p>None returned.</p> : <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul>}</div>
  );
}
