export function StatusBadge({ status }: { status: string }) {
  const className = status.trim().toLowerCase().replaceAll(" ", "-");
  return <b className={`status-badge ${className}`}>{status}</b>;
}
