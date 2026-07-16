import type { ReactNode } from "react";
import { Feedback } from "./Feedback";
import { useRequest } from "../hooks/useRequest";
import { endpoints } from "../lib/api";
import type { Device } from "../lib/types";
import { StatusBadge } from "./StatusBadge";

export type HistorySection = "scans" | "alerts" | "tickets" | "audit";

export function DeviceHistory({ device, section }: { device: Device; section: HistorySection }) {
  const scans = useRequest(() => endpoints.deviceScans(device.id));
  const audits = useRequest(() => endpoints.deviceAuditLogs(device.id));
  const tickets = useRequest(() => endpoints.deviceTickets(device.id));
  const alerts = useRequest(() => endpoints.deviceAlerts(device.id));

  if (section === "scans") return <HistoryPanel title="Scan history" loading={scans.loading} error={scans.error} empty="No scans have been recorded for this device." retry={scans.reload}>
        {(scans.data ?? []).map((scan) => <article key={scan.id}>
          <span className={`pulse ${scan.status.toLowerCase()}`} />
          <div><strong>{scan.status}</strong><p>{scan.ip_address}</p></div>
          <small>{scan.response_time == null ? "No response" : `${scan.response_time} ms`} / {formatDate(scan.scanned_at)}</small>
        </article>)}
      </HistoryPanel>;

  if (section === "audit") return <HistoryPanel title="Audit trail" loading={audits.loading} error={audits.error} empty="No audit activity has been recorded for this device." retry={audits.reload}>
        {(audits.data ?? []).map((log) => <article key={log.id}>
          <span className="pulse online" />
          <div><strong>{formatAction(log.action)}</strong><p>{log.description} / {log.actor}</p></div>
          <time>{formatDate(log.created_at)}</time>
        </article>)}
      </HistoryPanel>;

  if (section === "tickets") return <HistoryPanel title="Related tickets" loading={tickets.loading} error={tickets.error} empty="No related tickets were found for this device." retry={tickets.reload}>
        {(tickets.data ?? []).map((ticket) => <article key={ticket.id}>
          <span className={`pulse ${ticket.status.toLowerCase() === "closed" ? "online" : "offline"}`} />
          <div><strong>{ticket.title}</strong><p>{ticket.priority} priority / {ticket.description}</p></div>
          <StatusBadge status={ticket.status} />
        </article>)}
      </HistoryPanel>;

  return <HistoryPanel title="Related alerts" loading={alerts.loading} error={alerts.error} empty="No alerts have been recorded for this device." retry={alerts.reload}>
        {(alerts.data ?? []).map((alert) => <article key={alert.id}>
          <span className={`pulse ${alert.current_status.toLowerCase()}`} />
          <div><strong>{alert.message}</strong><p>{alert.previous_status} to {alert.current_status}</p></div>
          <time>{formatDate(alert.created_at)}</time>
        </article>)}
      </HistoryPanel>;
}

function HistoryPanel({ title, loading, error, empty, retry, children }: {
  title: string;
  loading: boolean;
  error: string;
  empty: string;
  retry: () => Promise<void>;
  children: ReactNode[];
}) {
  return <section className="device-history history-panel">
    <header className="section-head"><div><h2>{title}</h2><p>Real backend records associated with this asset.</p></div></header>
    <div className="history-panel-body">
    {loading || error ? <Feedback loading={loading} error={error} onRetry={retry} />
      : children.length ? <div className="history-list">{children}</div>
      : <Feedback emptyTitle={`No ${title.toLowerCase()}`} empty={empty} />}
    </div>
  </section>;
}

function formatAction(action: string) {
  return action.toLowerCase().split("_").map((word) => word[0].toUpperCase() + word.slice(1)).join(" ");
}

function formatDate(value: string) {
  return value ? new Date(value).toLocaleString() : "Not recorded";
}
