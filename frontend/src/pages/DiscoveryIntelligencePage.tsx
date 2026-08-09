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
  const [enriching, setEnriching] = useState(false);
  const [adEnriching, setAdEnriching] = useState(false);

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
  const enrich = async () => {
    const result=(detail?.result||{}) as Record<string,unknown>;if(!result.id)return;
    setEnriching(true);setError("");
    try{const response=await endpoints.enrichDiscoveryResult(String(result.id));setDetail(await endpoints.discoveryResult(String(result.id)));setMessage(response.status==="unavailable"?`SNMP unavailable: ${response.warnings[0]||"No response."}`:`Enrichment ${response.status.replaceAll("_"," ")}. ${response.found.length} attributes found.`);setDevices(current=>current.map(item=>item.result_id===String(result.id)?{...item,...response.device}:item));}
    catch(caught){setError(caught instanceof Error?caught.message:"Device enrichment failed.");}
    finally{setEnriching(false);}
  };
  const enrichFromAD = async () => {
    const result=(detail?.result||{}) as Record<string,unknown>;if(!result.id)return;
    setAdEnriching(true);setError("");
    try{const response=await endpoints.enrichDiscoveryResultFromAD(String(result.id));setDetail(await endpoints.discoveryResult(String(result.id)));setMessage(response.status==="unavailable"?`AD enrichment unavailable: ${response.warnings[0]||"No matching computer object."}`:`AD enrichment ${response.status.replaceAll("_"," ")}. ${response.found.length} attributes found.`);setDevices(current=>current.map(item=>item.result_id===String(result.id)?{...item,...response.device}:item));}
    catch(caught){setError(caught instanceof Error?caught.message:"Active Directory enrichment failed.");}
    finally{setAdEnriching(false);}
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
    {detail && <Evidence data={detail} close={() => setDetail(undefined)} enrich={enrich} enriching={enriching} enrichFromAD={enrichFromAD} adEnriching={adEnriching}/>}
  </DashboardLayout>;
}

function Metric({ label, value, detail }: { label: string; value: number; detail: string }) {
  return <article className="discovery-metric"><small>{label}</small><strong>{value}</strong><span>{detail}</span></article>;
}

function DeviceTable({ rows, inspect, approve, approving }: { rows: ConsolidatedDiscoveryDevice[]; inspect: (device: ConsolidatedDiscoveryDevice) => void; approve: (device: ConsolidatedDiscoveryDevice) => void; approving: string }) {
  if (!rows.length) return <Feedback empty="No devices in this view."/>;
  return <div className="table-wrap quick-device-table"><table><thead><tr><th>Friendly Name</th><th>Hostname</th><th>IP</th><th>MAC</th><th>Device Type</th><th>Department</th><th>Vendor</th><th>Confidence</th><th>Status / Review</th><th>Seen</th><th>Actions</th></tr></thead><tbody>{rows.map((device) => <tr key={device.result_id}><td data-label="Friendly Name"><strong>{device.friendly_name || "Unknown"}</strong></td><td data-label="Hostname">{device.primary_hostname || "—"}</td><td data-label="IP"><code>{device.ip_address}</code></td><td data-label="MAC">{device.mac_address || "—"}</td><td data-label="Device Type">{device.classification || device.device_type || "Unknown"}</td><td data-label="Department">{device.department || "—"}</td><td data-label="Vendor">{device.vendor || "Unknown"}</td><td data-label="Confidence"><b>{device.confidence_score}%</b></td><td data-label="Status / Review"><StatusBadge status={device.review_status}/></td><td data-label="Seen">{new Date(device.last_seen_at).toLocaleString()}</td><td data-label="Actions"><div className="row-actions"><button onClick={() => inspect(device)}>View details</button>{device.review_status !== "manually_verified" && <button disabled={approving === device.result_id} onClick={() => void approve(device)}>{approving === device.result_id ? "Approving..." : "Approve"}</button>}</div></td></tr>)}</tbody></table></div>;
}

function Evidence({ data, close, enrich, enriching, enrichFromAD, adEnriching }: { data: Record<string, unknown>; close: () => void; enrich:()=>void; enriching:boolean; enrichFromAD:()=>void; adEnriching:boolean }) {
  const result = (data.result || {}) as Record<string, unknown>;
  const evidence = (data.evidence || []) as Array<Record<string, unknown>>;
  const interfaces=(()=>{try{return JSON.parse(String(result.interface_information||"[]")) as Array<Record<string,unknown>>}catch{return []}})();const uptime=result.uptime_seconds?`${Math.floor(Number(result.uptime_seconds)/86400)}d ${Math.floor(Number(result.uptime_seconds)%86400/3600)}h`:"Not available";
  return <section className="discovery-detail"><header><div><small>Why HIOP identified this device</small><h3>{String(result.friendly_name || result.primary_hostname || result.ip_address || "Device evidence")}</h3></div><div className="row-actions"><button className="primary-action" disabled={enriching} onClick={()=>void enrich()}>{enriching?"Enriching…":"Enrich Device"}</button><button disabled={adEnriching} onClick={()=>void enrichFromAD()}>{adEnriching?"Checking AD…":"Enrich from Active Directory"}</button><button onClick={close}>Close</button></div></header><div className="enrichment-statuses"><p className="enrichment-status"><b>SNMP:</b> {String(result.snmp_enrichment_status||"not_attempted").replaceAll("_"," ")}</p><p className="enrichment-status"><b>Active Directory:</b> {String(result.ad_enrichment_status||"not_attempted").replaceAll("_"," ")}</p></div><div className="detail-grid"><article><h4>Device identity</h4><p><b>Friendly Name:</b> {String(result.friendly_name || "Unknown")}</p><p><b>Hostname:</b> {String(result.primary_hostname || "—")}</p><p><b>FQDN:</b> {String(result.fqdn || "—")}</p><p><b>IP:</b> {String(result.ip_address)}</p><p><b>MAC:</b> {String(result.mac_address || "—")}</p></article><article><h4>Classification</h4><p><b>Device Type:</b> {String(result.classification || result.device_type || "Unknown")}</p><p><b>Department:</b> {String(result.department || "—")}</p><p><b>Suggested Department:</b> {String(result.suggested_department || "Not available")}</p><p><b>Vendor:</b> {String(result.vendor || "Unknown")}</p><p><b>Model:</b> {String(result.model || "Not available")}</p></article><article><h4>Technical</h4><p><b>Serial Number:</b> {String(result.serial_number || "Not available")}</p><p><b>Firmware:</b> {String(result.firmware || "Not available")}</p><p><b>Uptime:</b> {uptime}</p><p><b>sysObjectID:</b> {String(result.sys_object_id || "Not available")}</p><p><b>Interfaces:</b> {String(result.interface_count??"Not available")}</p>{interfaces.slice(0,8).map((item,index)=><small key={index}>{String(item.name||item.description||`Interface ${item.index}`)} — {String(item.oper_status||"Unknown")}</small>)}</article><article><h4>Windows / Active Directory</h4><p><b>Domain:</b> {String(result.ad_domain||"Not available")}</p><p><b>Computer:</b> {String(result.ad_computer_name||"Not available")}</p><p><b>Operating System:</b> {String(result.ad_operating_system||"Not available")}</p><p><b>OS Version:</b> {String(result.ad_operating_system_version||"Not available")}</p><p><b>OU:</b> {String(result.ad_organizational_unit||"Not available")}</p><p><b>AD Status:</b> {result.ad_enabled===true?"Enabled":result.ad_enabled===false?"Disabled":"Not available"}</p><p><b>Last Logon:</b> {result.ad_last_logon_at?new Date(String(result.ad_last_logon_at)).toLocaleString():"Not available"}</p><p><b>Description:</b> {String(result.ad_description||"Not available")}</p><p><b>Distinguished Name:</b> {String(result.ad_distinguished_name||"Not available")}</p></article></div><h4>Evidence</h4><div className="evidence-cards">{evidence.length ? evidence.map((item, index) => <article key={String(item.id || index)}><span>+{String(item.weight || 0)}%</span><strong>{String(item.evidence_type || "evidence").replaceAll("_", " ")}</strong><small>{String(item.source || "network")}</small></article>) : <p>Not available</p>}</div></section>;
}
