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
  const [confirming, setConfirming] = useState(false);
  const [query, setQuery] = useState("");
  const [departmentFilter, setDepartmentFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [vendorFilter, setVendorFilter] = useState("");

  useEffect(() => {
    let active = true;
    endpoints.consolidatedDiscoveryDevices()
      .then((response) => { if (active) setDevices(response.items); })
      .catch((caught: unknown) => { if (active) setError(caught instanceof Error ? caught.message : "Devices could not be loaded."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  const visible = useMemo(() => {
    const term=query.trim().toLowerCase();
    return devices.filter((device) => {
      if (mode === "review" && device.conflict_status !== "open" && device.confidence_score >= 60) return false;
      if (departmentFilter && device.department !== departmentFilter) return false;
      if (typeFilter && (device.device_type || device.classification) !== typeFilter) return false;
      if (vendorFilter && device.vendor !== vendorFilter) return false;
      return !term || [device.friendly_name,device.primary_hostname,device.ip_address,device.mac_address,device.department,device.classification,device.device_type,device.vendor].some(value=>value?.toLowerCase().includes(term));
    });
  }, [devices, mode, query, departmentFilter, typeFilter, vendorFilter]);
  const options=(field:(device:ConsolidatedDiscoveryDevice)=>string|null|undefined)=>[...new Set(devices.map(field).filter((value):value is string=>Boolean(value)))].sort();
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
      const managed=await endpoints.approveDiscoveryResult(device.result_id);
      setDevices((current) => current.map((item) => item.result_id === device.result_id ? {...item, inventory_device_id: managed.id} : item));
      setDetail(current=>current?{...current,inventory_device_id:managed.id}:current);
      setMessage(`${device.primary_hostname || device.ip_address} was approved into managed inventory.`);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Device approval failed."); }
    finally { setApproving(""); }
  };
  const approveDetail=async()=>{const result=(detail?.result||{}) as Record<string,unknown>;if(!result.id)return;await approve(devices.find(item=>item.result_id===String(result.id))||{...result,result_id:String(result.id),inventory_device_id:null} as ConsolidatedDiscoveryDevice)};
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
  const confirmIdentity = async (values:{friendly_name?:string;department?:string;device_type?:string}) => {
    const result=(detail?.result||{}) as Record<string,unknown>;if(!result.id)return;
    setConfirming(true);setError("");
    try{const confirmed=await endpoints.confirmDiscoveryIdentity(String(result.id),values);setDetail(await endpoints.discoveryResult(String(confirmed.id)));setDevices(current=>current.map(item=>item.result_id===String(confirmed.id)?{...item,...confirmed}:item));setMessage(`${confirmed.friendly_name||confirmed.primary_hostname||confirmed.ip_address} was manually confirmed.`);}
    catch(caught){setError(caught instanceof Error?caught.message:"Identity confirmation failed.");}
    finally{setConfirming(false);}
  };

  return <DashboardLayout>
    <header className="page-title discovery-title"><div><span className="eyebrow">Discover</span><h1>Network discovery</h1><p>Scan a private network and build a clean inventory of real devices.</p></div></header>
    <nav className="discovery-tabs" aria-label="Discovery sections">{tabs.map(([label, path]) => <button key={path} className={location.pathname === path ? "active" : ""} onClick={() => navigate(path)}>{label}</button>)}</nav>
    {error && <Feedback error={error}/>}
    {mode === "scan" && <>
      <section className="quick-scan-hero"><div><span className="eyebrow">Simple network scan</span><h2>Find devices on your network</h2><p>Enter one private IP address or subnet. No credentials are required.</p></div><form onSubmit={scan}><label>Network address or range<input value={range} onChange={(event) => setRange(event.target.value)} placeholder="192.168.1.0/24" required/></label><button className="primary-action" disabled={scanning}>{scanning ? "Scanning…" : "Scan network"}</button></form>{message && <p role="status" className="quick-scan-status">{message}</p>}</section>
      <section className="discovery-metrics"><Metric label="Devices found" value={devices.length} detail="One row per device"/><Metric label="Identified" value={devices.filter((device) => device.confidence_score >= 60 && device.conflict_status !== "open").length} detail="Strong, consistent evidence"/><Metric label="Needs review" value={devices.filter((device) => device.confidence_score < 60 || device.conflict_status === "open").length} detail="Weak or conflicting evidence"/><Metric label="Approved" value={devices.filter((device) => Boolean(device.inventory_device_id)).length} detail="In managed inventory"/></section>
    </>}
    {(mode !== "scan" || devices.length > 0) && <section className="discovery-panel"><header><div><h2>{mode === "review" ? "Needs review" : "Devices"}</h2><p>{mode === "review" ? "Devices with weak or conflicting identification evidence." : "Discovered devices from your network."}</p></div></header><div className="discovery-filters"><label>Search<input value={query} onChange={event=>setQuery(event.target.value)} placeholder="Name, hostname, IP, MAC, department, type, or vendor"/></label><label>Department<select value={departmentFilter} onChange={event=>setDepartmentFilter(event.target.value)}><option value="">All departments</option>{options(device=>device.department).map(value=><option key={value}>{value}</option>)}</select></label><label>Device type<select value={typeFilter} onChange={event=>setTypeFilter(event.target.value)}><option value="">All device types</option>{options(device=>device.device_type||device.classification).map(value=><option key={value}>{value}</option>)}</select></label><label>Vendor<select value={vendorFilter} onChange={event=>setVendorFilter(event.target.value)}><option value="">All vendors</option>{options(device=>device.vendor).map(value=><option key={value}>{value}</option>)}</select></label></div>{loading ? <Feedback loading/> : <DeviceTable rows={visible} filtered={Boolean(query||departmentFilter||typeFilter||vendorFilter)} inspect={inspect} approve={approve} approving={approving}/>}</section>}
    {detail && <Evidence data={detail} close={() => setDetail(undefined)} enrich={enrich} enriching={enriching} enrichFromAD={enrichFromAD} adEnriching={adEnriching} confirmIdentity={confirmIdentity} confirming={confirming} approve={approveDetail} approving={Boolean(approving)}/>}
  </DashboardLayout>;
}

function Metric({ label, value, detail }: { label: string; value: number; detail: string }) {
  return <article className="discovery-metric"><small>{label}</small><strong>{value}</strong><span>{detail}</span></article>;
}

function DeviceTable({ rows, filtered, inspect, approve, approving }: { rows: ConsolidatedDiscoveryDevice[]; filtered:boolean; inspect: (device: ConsolidatedDiscoveryDevice) => void; approve: (device: ConsolidatedDiscoveryDevice) => void; approving: string }) {
  if (!rows.length) return <Feedback emptyTitle={filtered?"No matching devices":"No devices discovered yet."} empty={filtered?"Try a different name, address, department, type, or vendor.":"Run a network scan to discover your first device."}/>;
  return <div className="table-wrap quick-device-table"><table><thead><tr><th>Friendly Name</th><th>Hostname</th><th>IP</th><th>MAC</th><th>Device Type</th><th>Department</th><th>Vendor</th><th>Confidence</th><th>Status / Review</th><th>Seen</th><th>Actions</th></tr></thead><tbody>{rows.map((device) => {const review=device.conflict_status==="open"||device.confidence_score<60;return <tr key={device.result_id}><td data-label="Friendly Name"><strong>{device.friendly_name || "Unknown"}</strong></td><td data-label="Hostname">{device.primary_hostname || "—"}</td><td data-label="IP"><code>{device.ip_address}</code></td><td data-label="MAC">{device.mac_address || "—"}</td><td data-label="Device Type">{device.device_type || device.classification || "Unknown"}</td><td data-label="Department">{device.department || "—"}</td><td data-label="Vendor">{device.vendor || "Unknown"}</td><td data-label="Confidence"><b>{device.confidence_score}%</b><small>{device.confidence_level?.replaceAll("_"," ")}</small></td><td data-label="Status / Review"><StatusBadge status={device.inventory_device_id?"Approved":device.conflict_status==="open"?"Conflict":review?"Review":device.review_status}/></td><td data-label="Seen">{new Date(device.last_seen_at).toLocaleString()}</td><td data-label="Actions"><div className="row-actions">{review?<button onClick={() => inspect(device)}>Review</button>:<><button onClick={() => inspect(device)}>View details</button>{!device.inventory_device_id && <button disabled={approving === device.result_id} onClick={() => void approve(device)}>{approving === device.result_id ? "Approving..." : "Approve Device"}</button>}</>}</div></td></tr>})}</tbody></table></div>;
}

function Evidence({ data, close, enrich, enriching, enrichFromAD, adEnriching, confirmIdentity, confirming, approve, approving }: { data: Record<string, unknown>; close: () => void; enrich:()=>void; enriching:boolean; enrichFromAD:()=>void; adEnriching:boolean; confirmIdentity:(values:{friendly_name?:string;department?:string;device_type?:string})=>void; confirming:boolean; approve:()=>Promise<void>; approving:boolean }) {
  const result = (data.result || {}) as Record<string, unknown>;
  const evidence = (data.evidence || []) as Array<Record<string, unknown>>;
  const conflicts=(data.conflicts||[]) as Array<Record<string,unknown>>;const history=(data.identity_history||[]) as Array<Record<string,unknown>>;
  const [friendlyName,setFriendlyName]=useState(String(result.friendly_name||""));const [department,setDepartment]=useState(String(result.department||""));const [deviceType,setDeviceType]=useState(String(result.device_type||result.classification||""));
  const interfaces=(()=>{try{return JSON.parse(String(result.interface_information||"[]")) as Array<Record<string,unknown>>}catch{return []}})();const uptime=result.uptime_seconds?`${Math.floor(Number(result.uptime_seconds)/86400)}d ${Math.floor(Number(result.uptime_seconds)%86400/3600)}h`:"Not available";
  const openConflicts=conflicts.filter(item=>item.status==="open");const approved=Boolean(data.inventory_device_id);const strong=Number(result.confidence_score||0)>=60&&!openConflicts.length;
  const explanations=[...new Set(evidence.map(item=>explainEvidence(String(item.source||""),String(item.evidence_type||""))))].filter(Boolean);
  return <section className="discovery-detail"><header><div><small>Why HIOP identified this device</small><h3>{String(result.friendly_name || result.primary_hostname || result.ip_address || "Unable to identify this device")}</h3></div><div className="row-actions"><button className="primary-action" disabled={enriching} onClick={()=>void enrich()}>{enriching?"Enriching…":"Enrich Device"}</button><button disabled={adEnriching} onClick={()=>void enrichFromAD()}>{adEnriching?"Checking AD…":"Enrich from Active Directory"}</button><button onClick={close}>Close</button></div></header>
    <div className="enrichment-statuses"><p className="enrichment-status"><b>DNS:</b> {dnsMessage(String(result.dns_status||""),String(result.fqdn||""),evidence)}</p><p className="enrichment-status"><b>SNMP:</b> {enrichmentMessage("SNMP",String(result.snmp_enrichment_status||"not_attempted"))}</p><p className="enrichment-status"><b>Active Directory:</b> {enrichmentMessage("Active Directory",String(result.ad_enrichment_status||"not_attempted"))}</p></div>
    <div className="detail-grid"><article><h4>Identity</h4><p><b>Friendly Name:</b> {String(result.friendly_name || "Unknown")}</p><p><b>Original Hostname:</b> {String(result.primary_hostname || "—")}</p><p><b>FQDN:</b> {String(result.fqdn || "—")}</p><p><b>IP:</b> {String(result.ip_address)}</p><p><b>MAC:</b> {String(result.mac_address || "—")}</p></article><article><h4>Classification</h4><p><b>Device Type:</b> {String(result.device_type || result.classification || "Unknown")}</p>{Boolean(result.classification)&&result.classification!==result.device_type&&<p><b>Technical Classification:</b> {String(result.classification)}</p>}<p><b>Department:</b> {String(result.department || "—")}</p><p><b>Suggested Department:</b> {String(result.suggested_department || "Not available")}</p><p><b>Location:</b> {String(result.location || "—")}</p><p><b>Identification:</b> {result.identity_confirmed?"Manually confirmed":"Automatic suggestion"}</p></article><article><h4>Technical</h4><p><b>Vendor:</b> {String(result.vendor || "Unknown")}</p><p><b>Model:</b> {String(result.model || "Not available")}</p><p><b>Serial Number:</b> {String(result.serial_number || "Not available")}</p><p><b>Operating System:</b> {String(result.operating_system||result.ad_operating_system||"Not available")}</p><p><b>Firmware:</b> {String(result.firmware || "Not available")}</p><p><b>Uptime:</b> {uptime}</p><p><b>Interfaces:</b> {String(result.interface_count??"Not available")}</p>{interfaces.slice(0,8).map((item,index)=><small key={index}>{String(item.name||item.description||`Interface ${item.index}`)} — {String(item.oper_status||"Unknown")}</small>)}</article><article><h4>Windows / Active Directory</h4><p><b>Domain:</b> {String(result.ad_domain||"Not available")}</p><p><b>Computer:</b> {String(result.ad_computer_name||"Not available")}</p><p><b>OS Version:</b> {String(result.ad_operating_system_version||"Not available")}</p><p><b>OU:</b> {String(result.ad_organizational_unit||"Not available")}</p><p><b>AD Status:</b> {result.ad_enabled===true?"Enabled":result.ad_enabled===false?"Disabled":"Not available"}</p><p><b>Last Logon:</b> {result.ad_last_logon_at?new Date(String(result.ad_last_logon_at)).toLocaleString():"Not available"}</p><p><b>Description:</b> {String(result.ad_description||result.description||"Not available")}</p><p><b>Distinguished Name:</b> {String(result.ad_distinguished_name||"Not available")}</p></article></div>
    <article className="identity-confidence"><h4>Identification confidence</h4><strong>{String(result.confidence_score||0)}% · {String(result.confidence_level||"low").replaceAll("_"," ")}</strong><p>{String(result.confidence_reason||"Insufficient evidence.")}</p>{explanations.length?<ul>{explanations.map(item=><li key={item}>✓ {item}</li>)}</ul>:<p>Unable to identify this device: no corroborating identity evidence is available.</p>}<small>{result.identity_confirmed?"Manually confirmed":"Automatic assessment"} · {String(data.correlated_observations||1)} correlated observation(s)</small></article>
    {openConflicts.length>0&&<section className="identity-conflicts"><h4>Conflict detected</h4>{openConflicts.map((item,index)=><article key={String(item.id||index)}><StatusBadge status="Review"/><strong>{String(item.attribute)}</strong><p>⚠ {String(item.left_source)}: {String(item.left_value)} ↔ {String(item.right_source)}: {String(item.right_value)}</p></article>)}</section>}
    <form className="identity-confirmation" onSubmit={event=>{event.preventDefault();confirmIdentity({friendly_name:friendlyName,department,device_type:deviceType})}}><h4>Manual correction</h4><p>Confirm or correct the suggested identity. Manually confirmed values are preserved during future discovery.</p><label>Friendly Name<input value={friendlyName} onChange={event=>setFriendlyName(event.target.value)}/></label><label>Department<input value={department} onChange={event=>setDepartment(event.target.value)}/></label><label>Device Type<input value={deviceType} onChange={event=>setDeviceType(event.target.value)}/></label><button className="primary-action" disabled={confirming}>{confirming?"Confirming…":"Confirm Identification"}</button></form>
    <section className="identity-evidence"><h4>Evidence</h4><div className="evidence-cards">{evidence.length ? evidence.map((item, index) => <article key={String(item.id || index)}><strong>{String(item.evidence_type || "evidence").replaceAll("_", " ")}</strong><p>{String(item.value||"Observed")}</p><small>{sourceLabel(String(item.source||"network"))} · {item.verified?"confirmed":"observed"}</small></article>) : <p>Not available</p>}</div></section>
    <section className="identity-history"><h4>Identity history</h4>{history.length?history.map((item,index)=><p key={String(item.id||index)}><b>{String(item.attribute)}</b>: {String(item.previous_value||"Unknown")} → {String(item.current_value)} <small>{sourceLabel(String(item.source))}</small></p>):<p>No identity changes have been recorded.</p>}</section>
    <footer className="identity-review-actions">{approved?<><StatusBadge status="Approved"/><span>This device exists once in managed inventory.</span></>:strong?<button className="primary-action" disabled={approving} onClick={()=>void approve()}>{approving?"Approving…":"Approve Device"}</button>:<><StatusBadge status="Review"/><span>Review conflicts or confirm the identity before approval.</span></>}</footer>
  </section>;
}

function sourceLabel(source:string){const value=source.toLowerCase();if(value.includes("active_directory")||value==="ad")return "Active Directory";if(value.includes("hostname_rule"))return "Hostname Rules";if(value.includes("dns"))return "DNS";if(value.includes("dhcp"))return "DHCP";if(value.includes("snmp"))return "SNMP";if(value.includes("arp"))return "ARP";if(value.includes("icmp")||value.includes("ping"))return "Network Discovery";if(value.includes("manual")||value.includes("administrator"))return "Manual Confirmation";return source.replaceAll("_"," ");}
function explainEvidence(source:string,type:string){const label=sourceLabel(source);const attribute=type.replaceAll("_"," ");return label&&attribute?`${label} supplied ${attribute} evidence`:"";}
function enrichmentMessage(provider:string,status:string){if(status==="not_attempted")return "Enrichment has not been performed.";if(status==="unavailable")return provider==="Active Directory"?"Active Directory unavailable.":"SNMP unavailable.";return status.replaceAll("_"," ");}
function dnsMessage(status:string,fqdn:string,evidence:Array<Record<string,unknown>>){const confirmed=evidence.some(item=>String(item.source||"").toLowerCase().includes("dns")&&item.verified!==false);return ["ptr_found","forward_confirmed","resolved","verified","success"].includes(status)||Boolean(fqdn)||confirmed?"DNS information available.":"DNS information unavailable.";}
