import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { PageTitle } from "./DashboardPage";
import { Icon } from "../components/Icon";
import { Feedback } from "../components/Feedback";
import { StatCard } from "../components/StatCard";
import { StatusBadge } from "../components/StatusBadge";
import { endpoints } from "../lib/api";
import { useRequest } from "../hooks/useRequest";
import type { Alert, Device, LiveEvent, Scan } from "../lib/types";

type ScanState = "idle" | "running" | "completed" | "failed";

const formatDate = (value?: string | null) => value ? new Date(value).toLocaleString() : "Never";
const latency = (value?: number | null) => value == null ? "No response" : `${Math.round(value * 100) / 100} ms`;

export default function NetworkPage() {
  const navigate = useNavigate();
  const devices = useRequest(endpoints.devices, []);
  const scans = useRequest(() => endpoints.scanHistory(100), []);
  const alerts = useRequest(endpoints.alerts, []);
  const reloadDevices = devices.reload;
  const reloadScans = scans.reload;
  const reloadAlerts = alerts.reload;
  const [scanState, setScanState] = useState<ScanState>("idle");
  const [scanningDevice, setScanningDevice] = useState("");
  const [message, setMessage] = useState("");
  const [socketConnected, setSocketConnected] = useState<boolean | null>(null);

  const refresh = useCallback(async () => {
    await Promise.all([reloadDevices(), reloadScans(), reloadAlerts()]);
  }, [reloadDevices, reloadScans, reloadAlerts]);

  const live = useCallback((event: LiveEvent) => {
    if (event.event === "device_status_changed") {
      setMessage(`${event.hostname ?? "A device"} changed to ${event.current_status ?? "an unknown state"}.`);
      void refresh();
    }
  }, [refresh]);

  const runScan = async (device?: Device) => {
    setMessage("");
    setScanState("running");
    setScanningDevice(device?.id ?? "all");
    try {
      if (device) {
        const result = await endpoints.scanDevice(device.id);
        setMessage(`${device.hostname} scan completed: ${result.status}, ${latency(result.response_time)}.`);
      } else {
        const result = await endpoints.scanAll();
        setMessage(`Scan completed for ${result.total_devices} devices: ${result.online} online, ${result.offline} offline.`);
      }
      setScanState("completed");
      await refresh();
    } catch (error) {
      setScanState("failed");
      setMessage(error instanceof Error ? error.message : "The scan request failed.");
    } finally {
      setScanningDevice("");
    }
  };

  const latestByDevice = useMemo(() => {
    const latest = new Map<string, Scan>();
    for (const scan of scans.data ?? []) if (!latest.has(scan.device_id)) latest.set(scan.device_id, scan);
    return latest;
  }, [scans.data]);
  const activeDevices = (devices.data ?? []).filter(device => device.inventory_status !== "Retired");
  const averageResponse = useMemo(() => {
    const values = activeDevices.map(device => latestByDevice.get(device.id)?.response_time).filter((value): value is number => value != null);
    return values.length ? values.reduce((total, value) => total + value, 0) / values.length : null;
  }, [activeDevices, latestByDevice]);
  const lastScan = scans.data?.[0]?.scanned_at ?? null;
  const activeAlerts = (alerts.data ?? []).filter(alert => !alert.acknowledged);
  const running = scanState === "running";
  const initialLoading = devices.loading || scans.loading || alerts.loading;
  const initialError = devices.error || scans.error || alerts.error;

  return <DashboardLayout onLiveEvent={live} onLiveStateChange={setSocketConnected}>
    <PageTitle eyebrow="Network operations centre" title="Live network command" copy="Monitor reachability, run authenticated checks and respond to infrastructure changes in real time." action={<div className="noc-actions"><button className="secondary-action" disabled={running} onClick={() => void refresh()}><Icon name="network"/>Refresh status</button><button className="primary-action" disabled={running || !activeDevices.length} onClick={() => void runScan()}><Icon name="wifi"/>{running && scanningDevice === "all" ? "Scanning…" : "Scan all devices"}</button></div>}/>
    {socketConnected === false && <div className="noc-connection-error" role="alert"><Icon name="warning"/><div><strong>Live connection interrupted</strong><span>Status changes may be delayed. HIOP is reconnecting automatically.</span></div></div>}
    {message && <div className={`inline-notice ${scanState === "failed" ? "notice-error" : ""}`} role={scanState === "failed" ? "alert" : "status"}>{message}</div>}
    {scanState !== "idle" && <ScanProgress state={scanState}/>}

    {initialLoading || initialError ? <Feedback loading={initialLoading} error={initialError} onRetry={refresh}/> : <>
      <section className="noc-summary">
        <StatCard label="Total devices" value={devices.data?.length ?? 0} detail="Registered inventory, including retired" icon="devices" trend="Inventory"/>
        <StatCard label="Online devices" value={activeDevices.filter(d => d.network_status === "Online").length} detail="Responding to the latest check" icon="check" tone="success" trend="Live"/>
        <StatCard label="Offline devices" value={activeDevices.filter(d => d.network_status === "Offline").length} detail="Currently unreachable" icon="warning" tone="danger" trend="Action"/>
        <StatCard label="Unknown devices" value={activeDevices.filter(d => !["Online", "Offline"].includes(d.network_status)).length} detail="Awaiting a confirmed result" icon="wifi" tone="warning" trend="Pending"/>
        <StatCard label="Last scan time" value={lastScan ? new Date(lastScan).toLocaleTimeString([], {hour:"2-digit", minute:"2-digit"}) : "Never"} detail={formatDate(lastScan)} icon="clock" trend="Latest"/>
        <StatCard label="Average response" value={averageResponse == null ? "—" : latency(averageResponse)} detail="Latest responsive device checks" icon="network" trend="Latency"/>
        <StatCard label="Active alerts" value={activeAlerts.length} detail="Unacknowledged network events" icon="alerts" tone={activeAlerts.length ? "danger" : "success"} trend="Attention"/>
      </section>

      <section className="panel noc-device-panel">
        <header className="section-head"><div><h2>Network devices</h2><p>Current inventory state joined with each device's latest persisted scan.</p></div><span className={`live-pill ${socketConnected ? "connected" : ""}`}>{socketConnected ? "Live updates" : "Reconnecting"}</span></header>
        {!devices.data?.length ? <Feedback emptyTitle="No network devices" empty="Add a device with an IP address before running network checks."/> : <NetworkDeviceTable devices={devices.data} latest={latestByDevice} busy={running} scanningDevice={scanningDevice} onOpen={id => navigate(`/devices/${id}`)} onScan={runScan}/>}
      </section>

      <section className="noc-lower-grid">
        <section className="panel">
          <header className="section-head"><div><h2>Recent scan history</h2><p>Latest results persisted by the FastAPI monitoring service.</p></div></header>
          {scans.error || !scans.data?.length ? <Feedback error={scans.error} empty="No scan history has been recorded." onRetry={reloadScans}/> : <div className="noc-history-list">{scans.data.slice(0, 12).map(scan => { const device = devices.data?.find(item => item.id === scan.device_id); return <button key={scan.id} onClick={() => navigate(`/devices/${scan.device_id}`)}><span className={`pulse ${scan.status.toLowerCase()}`}/><span><strong>{device?.hostname ?? scan.ip_address}</strong><small>{formatDate(scan.scanned_at)}</small></span><StatusBadge status={scan.status}/><span>{latency(scan.response_time)}</span></button>; })}</div>}
        </section>
        <section className="panel">
          <header className="section-head"><div><h2>Recent network alerts</h2><p>Status changes requiring operational awareness.</p></div></header>
          {alerts.error || !alerts.data?.length ? <Feedback error={alerts.error} empty="No network alerts have been recorded." onRetry={reloadAlerts}/> : <div className="noc-alert-list">{alerts.data.slice(0, 8).map(alert => <AlertRow key={alert.id} alert={alert} device={devices.data?.find(item => item.id === alert.device_id)} onOpen={() => navigate(`/devices/${alert.device_id}`)}/>)}</div>}
        </section>
      </section>
    </>}
  </DashboardLayout>;
}

function ScanProgress({state}: {state: ScanState}) {
  const content = state === "running" ? ["Scan running", "HIOP is checking device reachability. Controls are disabled until the request completes."] : state === "completed" ? ["Scan completed", "Latest device states and history have been refreshed."] : ["Scan failed", "The request did not complete. Review the error and try again."];
  return <section className={`scan-progress ${state}`} aria-live="polite"><span className={state === "running" ? "spinner" : "scan-progress-icon"}><Icon name={state === "completed" ? "check" : "warning"}/></span><div><strong>{content[0]}</strong><p>{content[1]}</p></div>{state === "running" && <div className="scan-progress-track"><i/></div>}</section>;
}

function NetworkDeviceTable({devices, latest, busy, scanningDevice, onOpen, onScan}: {devices: Device[]; latest: Map<string, Scan>; busy: boolean; scanningDevice: string; onOpen: (id: string) => void; onScan: (device: Device) => Promise<void>}) {
  return <div className="noc-table-wrap"><table className="noc-table"><thead><tr><th>Device</th><th>Asset tag</th><th>IP address</th><th>Department</th><th>Type</th><th>Status</th><th>Response</th><th>Last scan</th><th>Actions</th></tr></thead><tbody>{devices.map(device => { const scan = latest.get(device.id); const status = device.inventory_status === "Retired" ? "Retired" : device.network_status || scan?.status || "Unknown"; return <tr key={device.id}><td><button className="noc-device-link" onClick={() => onOpen(device.id)}>{device.hostname}</button></td><td>{device.asset_tag}</td><td>{device.ip_address}</td><td>{device.department || "Unassigned"}</td><td>{device.device_type}</td><td><StatusBadge status={status}/></td><td>{latency(scan?.response_time)}</td><td>{formatDate(scan?.scanned_at)}</td><td><div className="row-actions"><button disabled={busy || device.inventory_status === "Retired"} onClick={() => void onScan(device)}>{scanningDevice === device.id ? "Scanning…" : "Scan"}</button><button onClick={() => onOpen(device.id)}>View</button></div></td></tr>; })}</tbody></table></div>;
}

function AlertRow({alert, device, onOpen}: {alert: Alert; device?: Device; onOpen: () => void}) {
  return <button className={alert.acknowledged ? "acknowledged" : ""} onClick={onOpen}><span className={`pulse ${alert.current_status.toLowerCase()}`}/><span><strong>{alert.message}</strong><small>{device?.hostname ?? "Related device"} · {formatDate(alert.created_at)}</small></span><StatusBadge status={alert.current_status}/></button>;
}
