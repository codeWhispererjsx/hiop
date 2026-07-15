import type { ReactNode } from "react";
import { Feedback } from "./Feedback";
import { useRequest } from "../hooks/useRequest";
import { endpoints } from "../lib/api";
import type { Device } from "../lib/types";

export function DeviceHistory({ device }: { device: Device }) {
  const scans = useRequest(() => endpoints.scanHistory(500));
  const audits = useRequest(endpoints.auditLogs);
  const tickets = useRequest(endpoints.tickets);
  const alerts = useRequest(endpoints.alerts);

  const deviceScans = (scans.data ?? []).filter((scan) => scan.device_id === device.id);
  const deviceAudits = (audits.data ?? []).filter((log) => log.entity_type.toLowerCase() === "device" && log.entity_id === device.id);
  const deviceTickets = (tickets.data ?? []).filter((ticket) => isRelatedTicket(ticket.title, ticket.description, device));
  const deviceAlerts = (alerts.data ?? []).filter((alert) => alert.device_id === device.id);

  return <section className="device-history" aria-labelledby="device-history-title">
    <header className="section-head">
      <div><h2 id="device-history-title">Device history</h2><p>Operational records associated with this asset.</p></div>
    </header>
    <div className="history-grid">
      <HistoryPanel title="Scan history" loading={scans.loading} error={scans.error} empty="No scans have been recorded for this device." retry={scans.reload}>
        {deviceScans.map((scan) => <article key={scan.id}>
          <span className={`pulse ${scan.status.toLowerCase()}`} />
          <div><strong>{scan.status}</strong><p>{scan.ip_address}</p></div>
          <small>{scan.response_time == null ? "No response" : `${scan.response_time} ms`}</small>
        </article>)}
      </HistoryPanel>

      <HistoryPanel title="Audit history" loading={audits.loading} error={audits.error} empty="No audit activity has been recorded for this device." retry={audits.reload}>
        {deviceAudits.map((log) => <article key={log.id}>
          <span className="pulse online" />
          <div><strong>{formatAction(log.action)}</strong><p>{log.description} / {log.actor}</p></div>
          <time>{formatDate(log.created_at)}</time>
        </article>)}
      </HistoryPanel>

      <HistoryPanel title="Related tickets" loading={tickets.loading} error={tickets.error} empty="No related tickets were found for this device." retry={tickets.reload}>
        {deviceTickets.map((ticket) => <article key={ticket.id}>
          <span className={`pulse ${ticket.status.toLowerCase() === "closed" ? "online" : "offline"}`} />
          <div><strong>{ticket.title}</strong><p>{ticket.priority} priority / {ticket.description}</p></div>
          <b className={`status-badge ${ticket.status.toLowerCase().replaceAll(" ", "-")}`}>{ticket.status}</b>
        </article>)}
      </HistoryPanel>

      <HistoryPanel title="Related alerts" loading={alerts.loading} error={alerts.error} empty="No alerts have been recorded for this device." retry={alerts.reload}>
        {deviceAlerts.map((alert) => <article key={alert.id}>
          <span className={`pulse ${alert.current_status.toLowerCase()}`} />
          <div><strong>{alert.message}</strong><p>{alert.previous_status} to {alert.current_status}</p></div>
          <time>{formatDate(alert.created_at)}</time>
        </article>)}
      </HistoryPanel>
    </div>
  </section>;
}

function HistoryPanel({ title, loading, error, empty, retry, children }: {
  title: string;
  loading: boolean;
  error: string;
  empty: string;
  retry: () => Promise<void>;
  children: ReactNode[];
}) {
  return <article className="history-panel">
    <h3>{title}</h3>
    {loading || error ? <Feedback loading={loading} error={error} onRetry={retry} />
      : children.length ? <div className="history-list">{children}</div>
      : <Feedback emptyTitle={`No ${title.toLowerCase()}`} empty={empty} />}
  </article>;
}

function isRelatedTicket(title: string, description: string, device: Device) {
  const text = `${title} ${description}`.toLowerCase();
  return [device.hostname, device.asset_tag, device.ip_address, device.serial_number]
    .filter(Boolean)
    .some((identifier) => text.includes(identifier.toLowerCase()));
}

function formatAction(action: string) {
  return action.toLowerCase().split("_").map((word) => word[0].toUpperCase() + word.slice(1)).join(" ");
}

function formatDate(value: string) {
  return value ? new Date(value).toLocaleString() : "Not recorded";
}
