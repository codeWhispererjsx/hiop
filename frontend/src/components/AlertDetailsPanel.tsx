import { useMemo } from "react";
import Modal from "./Modal";
import { Feedback } from "./Feedback";
import { StatusBadge } from "./StatusBadge";
import { Icon } from "./Icon";
import { endpoints } from "../lib/api";
import { useRequest } from "../hooks/useRequest";
import type { Alert, Device, Ticket } from "../lib/types";

const alertSeverity = (alert: Alert) => alert.current_status === "Offline" ? "Critical" : "Informational";

export function AlertDetailsPanel({alert, device, ticket, busy, onClose, onAcknowledge, onDevice, onTicket}: {alert: Alert; device?: Device; ticket?: Ticket; busy: boolean; onClose: () => void; onAcknowledge: () => void; onDevice: () => void; onTicket: () => void}) {
  const scans = useRequest(() => endpoints.deviceScans(alert.device_id), [alert.device_id]);
  const audit = useRequest(() => endpoints.auditLogs({ entity_type: "Alert", page_size: 100 }), []);
  const alertAudit = useMemo(() => (audit.data?.items ?? []).filter(item => item.entity_id === alert.id), [alert.id, audit.data]);
  const latestScan = scans.data?.[0];
  const timeline = useMemo(() => {
    const events: Array<{time: string; title: string; detail: string}> = [{time: alert.created_at, title: "Alert created", detail: `${alert.previous_status} changed to ${alert.current_status}`}];
    for (const item of alertAudit) events.push({time: item.created_at, title: item.action === "ACKNOWLEDGE_ALERT" ? "Alert acknowledged" : item.action, detail: `${item.actor}: ${item.description}`});
    if (ticket) events.push({time: ticket.created_at, title: "Ticket created", detail: ticket.title});
    return events.sort((a,b) => new Date(a.time).getTime() - new Date(b.time).getTime());
  }, [alert, alertAudit, ticket]);

  return <Modal title="Alert details" onClose={onClose}><div className="alert-detail-body">
    <div className="alert-detail-hero"><span className={`severity-icon ${alertSeverity(alert).toLowerCase()}`}><Icon name="warning"/></span><div><span className="detail-kicker">{alertSeverity(alert)} · Device status change</span><h3>{alert.message}</h3><p>{new Date(alert.created_at).toLocaleString()}</p></div><span className={`alert-state ${alert.acknowledged ? "acknowledged" : "active"}`}>{alert.acknowledged ? "Acknowledged" : "Active"}</span></div>
    <dl className="alert-detail-grid"><div><dt>Related device</dt><dd>{device?.hostname ?? "Unknown device"}</dd></div><div><dt>Asset tag</dt><dd>{device?.asset_tag ?? "—"}</dd></div><div><dt>Department</dt><dd>{device?.department || "Unassigned"}</dd></div><div><dt>IP address</dt><dd>{device?.ip_address ?? "—"}</dd></div><div><dt>Previous status</dt><dd><StatusBadge status={alert.previous_status}/></dd></div><div><dt>Current status</dt><dd><StatusBadge status={alert.current_status}/></dd></div><div><dt>Related device ticket</dt><dd>{ticket?.title ?? "No device-related ticket"}</dd></div><div><dt>Latest scan</dt><dd>{latestScan ? `${latestScan.response_time == null ? "No response" : `${latestScan.response_time} ms`} · ${new Date(latestScan.scanned_at).toLocaleString()}` : "No scan recorded"}</dd></div></dl>
    <section className="alert-detail-section"><h4>Activity timeline</h4>{scans.loading || audit.loading ? <Feedback loading/> : scans.error || audit.error ? <Feedback error={scans.error || audit.error} onRetry={() => void Promise.all([scans.reload(), audit.reload()])}/> : <div className="alert-timeline">{timeline.map((item,index) => <article key={`${item.title}-${item.time}-${index}`}><i/><time>{new Date(item.time).toLocaleString()}</time><strong>{item.title}</strong><p>{item.detail}</p></article>)}</div>}</section>
    <div className="api-gap compact"><Icon name="warning"/><div><strong>Resolution tracking unavailable</strong><p>The backend does not currently expose an alert resolution state or endpoint.</p></div></div>
  </div><footer className="alert-detail-actions"><button className="secondary-action" onClick={onDevice}>Open device</button>{ticket && <button className="secondary-action" onClick={onTicket}>Open related ticket</button>}{!alert.acknowledged && <button className="primary-action" disabled={busy} onClick={onAcknowledge}>{busy ? "Acknowledging…" : "Acknowledge alert"}</button>}</footer></Modal>;
}
