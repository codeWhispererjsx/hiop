import { Icon } from "./Icon";
export function Feedback({ loading, error, empty, emptyTitle, onRetry }: { loading?: boolean; error?: string; empty?: string; emptyTitle?: string; onRetry?: () => void }) {
  if (loading) return <div className="feedback-card"><span className="spinner"/><h3>Loading operational data</h3><p>Please wait while HIOP contacts the backend.</p></div>;
  if (error) return <div className="feedback-card error"><Icon name="warning" size={28}/><h3>Something went wrong</h3><p>{error}</p>{onRetry && <button className="secondary-action" onClick={onRetry}>Try again</button>}</div>;
  return <div className="feedback-card"><Icon name="search" size={28}/><h3>{emptyTitle ?? "No records found"}</h3><p>{empty ?? "There is nothing to display yet."}</p></div>;
}
export function ApiGap({ title, endpoint }: { title: string; endpoint: string }) { return <div className="api-gap"><Icon name="warning"/><div><strong>{title}</strong><p>This screen is intentionally read-only because the backend does not expose <code>{endpoint}</code>. No local data is presented as saved.</p></div></div>; }
