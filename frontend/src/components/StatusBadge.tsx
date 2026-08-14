export function StatusBadge({ status }: { status: string }) {
  const label = status?.trim() || "Unknown";
  const className = label.toLowerCase().replaceAll("_", "-").replaceAll(" ", "-");
  return <span className={`status-badge ${className}`} aria-label={`Status: ${label}`}><i aria-hidden="true"/>{label.replaceAll("_", " ")}</span>;
}
