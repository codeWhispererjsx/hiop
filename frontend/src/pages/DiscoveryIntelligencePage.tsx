import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { Feedback } from "../components/Feedback";
import { StatusBadge } from "../components/StatusBadge";
import { endpoints } from "../lib/api";
import type { ConsolidatedDiscoveryDevice } from "../lib/types";
import "../styles/discovery-intelligence.css";
import "../styles/discovery-evidence.css";

const tabs = [
  ["Quick Scan", "/discovery-intelligence"],
  ["Devices", "/discovery-intelligence/devices"],
  ["Needs Review", "/discovery-intelligence/review"],
] as const;

export default function DiscoveryIntelligencePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const mode = location.pathname.endsWith("/devices") ? "devices" : location.pathname.endsWith("/review") ? "review" : "scan";
  const [devices, setDevices] = useState<ConsolidatedDiscoveryDevice[]>([]);
  const [range, setRange] = useState("");
  const [scanning, setScanning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [detail, setDetail] = useState<Record<string, unknown>>();
  const [approving, setApproving] = useState("");

  useEffect(() => {
    let active = true;
    endpoints.consolidatedDiscoveryDevices()
      .then((response) => { if (active) setDevices(response.items); })
      .catch((caught: unknown) => { if (active) setError(caught instanceof Error ? caught.message : "Devices could not be loaded."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  const visible = useMemo(() => mode === "review" ? devices.filter((device) => device.confidence_score < 40 || device.review_status === "needs_review") : devices, [devices, mode]);
  const scan = async (event: FormEvent) => {
    event.preventDefault();
    setScanning(true); setError(""); setMessage("Scanning safely. Devices will appear when the scan completes.");
    try {
      const response = await endpoints.quickDiscoveryScan(range);
      setDevices(response.devices);
      setMessage(`Found ${response.summary.found} device${response.summary.found === 1 ? "" : "s"}.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The scan could not be completed.");
      setMessage("");
    } finally { setScanning(false); }
  };
  const inspect = async (device: ConsolidatedDiscoveryDevice) => {
    try { setDetail(await endpoints.discoveryResult(device.result_id)); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Device evidence could not be loaded."); }
  };
  const approve = async (device: ConsolidatedDiscoveryDevice) => {
    setApproving(device.result_id); setError("");
    try {
      await endpoints.approveDiscoveryResult(device.result_id);
      setDevices((current) => current.map((item) => item.result_id === device.result_id ? {...item, review_status: "manually_verified"} : item));
      setMessage(`${device.primary_hostname || device.ip_address} was approved into managed inventory.`);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Device approval failed."); }
    finally { setApproving(""); }
  };

  return <DashboardLayout>
    <header className="page-title discovery-title"><div><span className="eyebrow">Discover</span><h1>Network discovery</h1><p>Scan a private network and build a clean inventory of real devices.</p></div></header>
    <nav className="discovery-tabs" aria-label="Discovery sections">{tabs.map(([label, path]) => <button key={path} className={location.pathname === path ? "active" : ""} onClick={() => navigate(path)}>{label}</button>)}</nav>
    {error && <Feedback error={error}/>}
    {mode === "scan" && <>
      <section className="quick-scan-hero"><div><span className="eyebrow">Simple network scan</span><h2>Find devices on your network</h2><p>Enter one private IP address or subnet. No credentials are required.</p></div><form onSubmit={scan}><label>Network address or range<input value={range} onChange={(event) => setRange(event.target.value)} placeholder="192.168.1.0/24" required/></label><button className="primary-action" disabled={scanning}>{scanning ? "Scanning…" : "Scan network"}</button></form>{message && <p role="status" className="quick-scan-status">{message}</p>}</section>
      <section className="discovery-metrics"><Metric label="Devices found" value={devices.length} detail="One row per device"/><Metric label="Identified" value={devices.filter((device) => device.confidence_score >= 80).length} detail="Strong evidence"/><Metric label="Partially identified" value={devices.filter((device) => device.confidence_score >= 40 && device.confidence_score < 80).length} detail="Useful details found"/><Metric label="Needs review" value={devices.filter((device) => device.confidence_score < 40).length} detail="Name or type unknown"/></section>
    </>}
    {(mode !== "scan" || devices.length > 0) && <section className="discovery-panel"><header><div><h2>{mode === "review" ? "Needs review" : "Devices"}</h2><p>{mode === "review" ? "Only devices that still need identification." : "Discovered devices from your network."}</p></div></header>{loading ? <Feedback loading/> : <DeviceTable rows={visible} inspect={inspect} approve={approve} approving={approving}/>}</section>}
    {detail && <Evidence data={detail} close={() => setDetail(undefined)}/>}
  </DashboardLayout>;
}

function Metric({ label, value, detail }: { label: string; value: number; detail: string }) {
  return <article className="discovery-metric"><small>{label}</small><strong>{value}</strong><span>{detail}</span></article>;
}

function DeviceTable({ rows, inspect, approve, approving }: { rows: ConsolidatedDiscoveryDevice[]; inspect: (device: ConsolidatedDiscoveryDevice) => void; approve: (device: ConsolidatedDiscoveryDevice) => void; approving: string }) {
  if (!rows.length) return <Feedback empty="No devices in this view."/>;
  return <div className="table-wrap quick-device-table"><table><thead><tr><th>Device</th><th>IP address</th><th>Type</th><th>Vendor / OS</th><th>Confidence</th><th>Status</th><th>Last seen</th><th>Actions</th></tr></thead><tbody>{rows.map((device) => <tr key={device.result_id}><td data-label="Device"><strong>{device.primary_hostname || "Unknown"}</strong><small>{device.mac_address || "Unknown"}</small></td><td data-label="IP address"><code>{device.ip_address}</code></td><td data-label="Type">{device.classification || device.device_type || "Unknown"}</td><td data-label="Vendor / OS">{device.vendor || "Unknown"}<small>{device.operating_system || "Unknown"}</small></td><td data-label="Confidence"><b>{device.confidence_score}%</b></td><td data-label="Status"><StatusBadge status={device.review_status}/></td><td data-label="Last seen">{new Date(device.last_seen_at).toLocaleString()}</td><td data-label="Actions"><div className="row-actions"><button onClick={() => inspect(device)}>View details</button>{device.review_status !== "manually_verified" && <button disabled={approving === device.result_id} onClick={() => void approve(device)}>{approving === device.result_id ? "Approving..." : "Approve"}</button>}</div></td></tr>)}</tbody></table></div>;
}

function Evidence({ data, close }: { data: Record<string, unknown>; close: () => void }) {
  const result = (data.result || {}) as Record<string, unknown>;
  const evidence = (data.evidence || []) as Array<Record<string, unknown>>;
  return <section className="discovery-detail"><header><div><small>Why HIOP identified this device</small><h3>{String(result.primary_hostname || result.ip_address || "Device evidence")}</h3></div><button onClick={close}>Close</button></header><div className="evidence-cards">{evidence.map((item, index) => <article key={String(item.id || index)}><span>+{String(item.weight || 0)}%</span><strong>{String(item.evidence_type || "evidence").replaceAll("_", " ")}</strong><small>{String(item.source || "network")}</small></article>)}</div></section>;
}
