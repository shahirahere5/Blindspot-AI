interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div className="state-card error-state" role="alert">
      <span className="state-icon" aria-hidden="true">!</span>
      <div>
        <h3>Something needs attention</h3>
        <p>{message}</p>
      </div>
      {onRetry && <button className="button button-secondary" onClick={onRetry}>Try again</button>}
    </div>
  );
}

export function LoadingState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="state-card loading-state" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <div>
        <h3>{title}</h3>
        <p>{detail}</p>
      </div>
    </div>
  );
}

export function EmptyState({
  eyebrow,
  title,
  detail,
  actionLabel,
  onAction,
}: {
  eyebrow: string;
  title: string;
  detail: string;
  actionLabel: string;
  onAction: () => void;
}) {
  return (
    <div className="empty-state">
      <span className="eyebrow">{eyebrow}</span>
      <h2>{title}</h2>
      <p>{detail}</p>
      <button className="button button-primary" onClick={onAction}>{actionLabel}</button>
    </div>
  );
}
