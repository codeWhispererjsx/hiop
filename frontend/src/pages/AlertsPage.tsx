import { useCallback, useDeferredValue, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { PageTitle } from "./DashboardPage";
import { Feedback } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { StatCard } from "../components/StatCard";
import { StatusBadge } from "../components/StatusBadge";
import { Toast } from "../components/Toast";
import { AlertDetailsPanel } from "../components/AlertDetailsPanel";
import { endpoints } from "../lib/api";
import { useRequest } from "../hooks/useRequest";
import type { Alert, Device, LiveEvent, Ticket } from "../lib/types";

type AlertState = "Active" | "Acknowledged";
type Severity = "Critical" | "Informational";
type ToastState = { id: number; message: string; tone: "success" | "error" };

const alertSeverity = (alert: Alert): Severity => alert.current_status === "Offline" ? "Critical" : "Informational";
const alertState = (alert: Alert): AlertState => alert.acknowledged ? "Acknowledged" : "Active";
const dayValue = (value: string) => new Date(value).toLocaleDateString("en-CA");
const todayValue = () => new Date().toLocaleDateString("en-CA");

export default function AlertsPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const alerts = useRequest(endpoints.alerts, []);
  const devices = useRequest(endpoints.devices, []);
  const tickets = useRequest(endpoints.tickets, []);
  const reloadAlerts = alerts.reload;
  const [selected, setSelected] = useState<Alert | null>(null);
  const [busy, setBusy] = useState("");
  const [socketState, setSocketState] = useState<"connected" | "reconnecting" | "offline">("reconnecting");
  const [toast, setToast] = useState<ToastState | null>(null);
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const [severity, setSeverity] = useState(() => searchParams.get("severity") || "All");
  const [status, setStatus] = useState("All");
  const [department, setDepartment] = useState("All");
  const [deviceId, setDeviceId] = useState("All");
  const [date, setDate] = useState("");

  const deviceMap = useMemo(() => new Map((devices.data ?? []).map(device => [device.id, device])), [devices.data]);
  const ticketByDevice = useMemo(() => {
    const map = new Map<string, Ticket>();
    for (const ticket of tickets.data ?? []) if (ticket.device_id && !map.has(ticket.device_id)) map.set(ticket.device_id, ticket);
    return map;
  }, [tickets.data]);
  const departments = useMemo(() => [...new Set((devices.data ?? []).map(device => device.department.trim()).filter(Boolean))].sort(), [devices.data]);

  const rows = useMemo(() => (alerts.data ?? []).filter(alert => {
    const device = deviceMap.get(alert.device_id);
    const text = `${alert.message} ${alert.previous_status} ${alert.current_status} ${device?.hostname ?? ""} ${device?.asset_tag ?? ""} ${device?.department ?? ""}`.toLowerCase();
    return (!deferredSearch.trim() || text.includes(deferredSearch.trim().toLowerCase()))
      && (severity === "All" || alertSeverity(alert) === severity)
      && (status === "All" || alertState(alert) === status)
      && (department === "All" || device?.department === department)
      && (deviceId === "All" || alert.device_id === deviceId)
      && (!date || dayValue(alert.created_at) === date);
  }), [alerts.data, date, deferredSearch, department, deviceId, deviceMap, severity, status]);

  const notify = (message: string, tone: "success" | "error" = "success") => setToast({id: Date.now(), message, tone});
  const acknowledge = async (alert: Alert) => {
    setBusy(alert.id);
    try {
      await endpoints.acknowledgeAlert(alert.id);
      notify("Alert acknowledged.");
      await reloadAlerts();
      setSelected(current => current?.id === alert.id ? {...current, acknowledged: true} : current);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Unable to acknowledge alert.", "error");
    } finally {
      setBusy("");
    }
  };
  const live = useCallback((event: LiveEvent) => {
    if (event.event === "device_status_changed") {
      setToast({id: Date.now(), message: `${event.hostname ?? "A device"} changed to ${event.current_status ?? "a new state"}.`, tone: "success"});
      void reloadAlerts();
    }
  }, [reloadAlerts]);
  const handleLiveState = useCallback((connected: boolean) => {
    setSocketState(connected ? "connected" : navigator.onLine ? "reconnecting" : "offline");
  }, []);
  const clearFilters = () => { setSearch(""); setSeverity("All"); setStatus("All"); setDepartment("All"); setDeviceId("All"); setDate(""); };
  const allAlerts = alerts.data ?? [];
  const initialLoading = alerts.loading || devices.loading || tickets.loading;
  const initialError = alerts.error || devices.error || tickets.error;

  return <DashboardLayout onLiveEvent={live} onLiveStateChange={handleLiveState}>
    <PageTitle eyebrow="Enterprise response centre" title="Alerts management" copy="Triage persistent infrastructure events, correlate affected assets and coordinate operational response." action={<div className="alerts-page-actions"><span className={`socket-state ${socketState}`}><i/>{socketState}</span><button className="secondary-action" onClick={() => void Promise.all([alerts.reload(), devices.reload(), tickets.reload()])}><Icon name="network"/>Refresh</button></div>}/>
    {toast && <Toast key={toast.id} message={toast.message} tone={toast.tone}/>}
    {initialLoading || initialError ? <Feedback loading={initialLoading} error={initialError} onRetry={() => void Promise.all([alerts.reload(), devices.reload(), tickets.reload()])}/> : <>
      <section className="alerts-summary">
        <StatCard label="Total alerts" value={allAlerts.length} detail="All persisted monitoring events" icon="alerts" trend="Recorded"/>
        <StatCard label="Active alerts" value={allAlerts.filter(item => !item.acknowledged).length} detail="Awaiting acknowledgement" icon="warning" tone="danger" trend="Action"/>
        <StatCard label="Acknowledged" value={allAlerts.filter(item => item.acknowledged).length} detail="Reviewed by operations" icon="check" tone="success" trend="Triaged"/>
        <StatCard label="Resolved alerts" value="—" detail="Resolution is not yet tracked by the API" icon="check" trend="API gap"/>
        <StatCard label="Critical alerts" value={allAlerts.filter(item => alertSeverity(item) === "Critical").length} detail="Current status is Offline" icon="warning" tone="danger" trend="Critical"/>
        <StatCard label="Today's alerts" value={allAlerts.filter(item => dayValue(item.created_at) === todayValue()).length} detail="Created in the local calendar day" icon="clock" trend="Today"/>
      </section>

      <section className="toolbar-panel alerts-toolbar">
        <label className="search-field"><Icon name="search" size={16}/><input aria-label="Search alerts" placeholder="Search alerts, devices or asset tags" value={search} onChange={event => setSearch(event.target.value)}/></label>
        <select aria-label="Severity" value={severity} onChange={event => setSeverity(event.target.value)}><option>All</option><option>Critical</option><option>Informational</option></select>
        <select aria-label="Status" value={status} onChange={event => setStatus(event.target.value)}><option>All</option><option>Active</option><option>Acknowledged</option></select>
        <select aria-label="Department" value={department} onChange={event => setDepartment(event.target.value)}><option>All</option>{departments.map(item => <option key={item}>{item}</option>)}</select>
        <select aria-label="Device" value={deviceId} onChange={event => setDeviceId(event.target.value)}><option value="All">All devices</option>{(devices.data ?? []).map(device => <option key={device.id} value={device.id}>{device.hostname}</option>)}</select>
        <input className="alerts-date" aria-label="Alert date" type="date" value={date} onChange={event => setDate(event.target.value)}/>
        <button className="secondary-action" onClick={clearFilters}>Clear</button>
      </section>

      <section className="panel alerts-table-panel">
        <header className="section-head"><div><h2>Alert queue</h2><p>{rows.length} of {allAlerts.length} alerts match the current view.</p></div></header>
        {!rows.length ? <Feedback emptyTitle="No alerts found" empty="No alerts match the selected filters."/> : <AlertsTable alerts={rows} devices={deviceMap} busy={busy} onSelect={setSelected} onAcknowledge={acknowledge} onDevice={id => navigate(`/devices/${id}`)}/>}
      </section>
    </>}
    {selected && <AlertDetailsPanel key={selected.id} alert={selected} device={deviceMap.get(selected.device_id)} ticket={ticketByDevice.get(selected.device_id)} busy={busy === selected.id} onClose={() => setSelected(null)} onAcknowledge={() => void acknowledge(selected)} onDevice={() => navigate(`/devices/${selected.device_id}`)} onTicket={() => navigate("/tickets")}/>}
  </DashboardLayout>;
}

function AlertsTable({alerts, devices, busy, onSelect, onAcknowledge, onDevice}: {alerts: Alert[]; devices: Map<string, Device>; busy: string; onSelect: (alert: Alert) => void; onAcknowledge: (alert: Alert) => Promise<void>; onDevice: (id: string) => void}) {
  return <div className="alerts-table-wrap"><table className="alerts-table"><thead><tr><th>Timestamp</th><th>Device</th><th>Asset tag</th><th>Department</th><th>Alert type</th><th>Severity</th><th>Previous</th><th>Current</th><th>Message</th><th>Assigned ticket</th><th>State</th><th>Actions</th></tr></thead><tbody>{alerts.map(alert => { const device = devices.get(alert.device_id); return <tr key={alert.id} className={!alert.acknowledged ? "active-alert" : ""}><td>{new Date(alert.created_at).toLocaleString()}</td><td><button className="table-link" onClick={() => onDevice(alert.device_id)}>{device?.hostname ?? "Unknown device"}</button></td><td>{device?.asset_tag ?? "—"}</td><td>{device?.department || "Unassigned"}</td><td>Device status change</td><td><span className={`severity-badge ${alertSeverity(alert).toLowerCase()}`}>{alertSeverity(alert)}</span></td><td><StatusBadge status={alert.previous_status}/></td><td><StatusBadge status={alert.current_status}/></td><td><button className="alert-message-link" onClick={() => onSelect(alert)}>{alert.message}</button></td><td>Not linked by API</td><td><span className={`alert-state ${alert.acknowledged ? "acknowledged" : "active"}`}>{alertState(alert)}</span></td><td><div className="row-actions"><button onClick={() => onSelect(alert)}>Details</button>{!alert.acknowledged && <button disabled={busy === alert.id} onClick={() => void onAcknowledge(alert)}>{busy === alert.id ? "Saving…" : "Acknowledge"}</button>}</div></td></tr>; })}</tbody></table></div>;
}
