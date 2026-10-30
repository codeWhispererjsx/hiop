import { formatDateOnly, formatDateTime } from "../lib/dateTime";
import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { ConfirmationModal } from "../components/ConfirmationModal";
import { DeviceHistory, type HistorySection } from "../components/DeviceHistory";
import { Feedback } from "../components/Feedback";
import { StatusBadge } from "../components/StatusBadge";
import { Toast } from "../components/Toast";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import { isDesktopMode } from "../lib/appMode";
import type { Device, DeviceHealth, LiveEvent, ManagedAsset, User } from "../lib/types";
import { PageTitle } from "./DashboardPage";
import "../styles/port-intelligence.css";

type DetailsTab = "overview" | HistorySection;
const tabs: Array<{ id: DetailsTab; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "scans", label: "Scan History" },
  { id: "alerts", label: "Alerts" },
  { id: "tickets", label: "Tickets" },
  { id: "audit", label: "Audit Trail" },
];

export default function DeviceDetailsPage() {
  const { id = "" } = useParams();
  const location = useLocation();
  const successNotice = (location.state as { notice?: string } | null)?.notice;
  const { data: device, loading, error, reload } = useRequest(() => endpoints.device(id));
  const [discoveryIdentity, setDiscoveryIdentity] = useState<Record<string, unknown>>();
  const [health,setHealth]=useState<DeviceHealth>();
  const [asset,setAsset]=useState<ManagedAsset>();
  useEffect(() => {
    let active = true;
    endpoints.inventoryDiscoveryIdentity(id).then((value) => { if (active) setDiscoveryIdentity(value); }).catch(() => { if (active) setDiscoveryIdentity(undefined); });
    return () => { active = false; };
  }, [id]);
  useEffect(()=>{let active=true;endpoints.deviceAsset(id).then(value=>{if(active)setAsset(value)}).catch(()=>{if(active)setAsset(undefined)});return()=>{active=false}},[id]);
  useEffect(() => {
    let active = true;
    endpoints.deviceHealth(id,"24h").then(value=>{if(active)setHealth(value)}).catch(()=>{if(active)setHealth(undefined)});
    return () => { active = false; };
  }, [id]);
  const hierarchy = useRequest(endpoints.hierarchy, []);
  const currentUser = useRequest(endpoints.me, []);
  const [activeTab, setActiveTab] = useState<DetailsTab>("overview");
  const [confirmingRetirement, setConfirmingRetirement] = useState(false);
  const [retiring, setRetiring] = useState(false);
  const [retireError, setRetireError] = useState("");
  const [retireNotice, setRetireNotice] = useState("");
  const [actionNotice, setActionNotice] = useState("");
  const [actionError, setActionError] = useState("");
  const showActionNotice = (message: string) => { setActionError(""); setActionNotice(message); };
  const showActionError = (message: string) => { setActionNotice(""); setActionError(message); };

  const handleLiveEvent = (event: LiveEvent) => {
    if (event.event === "device_status_changed" && event.device_id === id) void reload();
  };

  const retire = async () => {
    if (!device || retiring) return;
    setRetiring(true);
    setRetireError("");
    try {
      await endpoints.retireDevice(device.id);
      await reload();
      setConfirmingRetirement(false);
      setRetireNotice(`${device.hostname} was retired successfully.`);
    } catch (requestError) {
      setRetireError(requestError instanceof Error ? requestError.message : "Unable to retire this device.");
    } finally {
      setRetiring(false);
    }
  };

  const isRetired = device?.inventory_status.toLowerCase() === "retired";
  return (
    <DashboardLayout onLiveEvent={handleLiveEvent}>
      <PageTitle
        eyebrow="Asset inventory"
        title={device?.hostname ?? "Device details"}
        copy="Complete device information and operational history from HIOP."
        action={<div className="page-actions">
          <Link className="secondary-action" to="/devices">Back to devices</Link>
          {device && <DeviceActions device={device} role={currentUser.data?.role} onNotice={showActionNotice} onError={showActionError} onRescan={async () => {
            await endpoints.scanDevice(device.id);
            showActionNotice("Connectivity rescan started. HIOP will update this device when the check completes.");
          }} />}
          {device && !isRetired && currentUser.data?.role === "admin" && <>
            <Link className="primary-action" to={`/devices/${id}/edit`}>Edit device</Link>
            {currentUser.data?.role === "admin" && <button className="danger-action" onClick={() => { setRetireError(""); setConfirmingRetirement(true); }}>Retire device</button>}
          </>}
        </div>}
      />

      {(retireNotice || successNotice || actionNotice) && <Toast message={retireNotice || successNotice || actionNotice || "Device updated successfully."} />}
      {actionError && <Toast message={actionError} tone="error" />}

      {loading || error ? (
        <Feedback loading={loading} error={error} onRetry={reload} />
      ) : !device ? (
        <Feedback emptyTitle="Device not found" empty="No device information is available." />
      ) : (
        <>
          {isRetired && <div className="retired-banner"><StatusBadge status="Retired" /><span>This asset is retired. Its details and operational history remain available.</span></div>}
          <section className="identity-summary" aria-label="Device identity summary">
            <header>
              <div><span className="section-kicker">At a glance</span><h2>{device.hostname || "Device identity needs review"}</h2><p>Use this summary to decide what needs attention before opening the detailed evidence below.</p></div>
              <StatusBadge status={device.network_status || "unknown"} />
            </header>
            <div className="identity-summary-grid">
              <div><span>Technical identity</span><strong>{device.hostname || "Not recorded"}</strong><small>{device.ip_address || "IP address not recorded"}</small></div>
              <div><span>Device type</span><strong>{device.device_type || "Not classified"}</strong><small>{device.brand || "Manufacturer not recorded"}{device.model ? ` · ${device.model}` : ""}</small></div>
              <div><span>Operational state</span><strong>{device.inventory_status || "Not recorded"}</strong><small>{device.network_status || "Network status not recorded"}</small></div>
              <div><span>Ownership & location</span><strong>{device.department || "Department not assigned"}</strong><small>{device.location || "Location not assigned"}</small></div>
            </div>
          </section>
          {asset&&<section className="panel"><header className="section-head"><div><span>Managed asset and lifecycle</span><h2>{asset.asset_number}</h2><p>{asset.asset_tag||"No human-readable asset tag assigned"} · {asset.ci_category} · Lifecycle {asset.status.replaceAll("_"," ")}</p></div>{currentUser.data?.role==="admin"&&<Link className="secondary-action" to={`/assets/${asset.id}/edit`}>Edit asset metadata</Link>}</header><dl className="settings-readonly"><div><dt>Serial number</dt><dd>{asset.serial_number||"Not recorded"}</dd></div><div><dt>Condition</dt><dd>{asset.condition||"Not recorded"}</dd></div><div><dt>Acquired / received</dt><dd>{formatDateOnly(asset.acquisition_date)} / {formatDateOnly(asset.received_date)}</dd></div><div><dt>Deployed</dt><dd>{formatDateOnly(asset.deployment_date)}</dd></div><div><dt>Warranty</dt><dd>{asset.warranty_status}{asset.warranty_end?` · ends ${formatDateOnly(asset.warranty_end)}`:""}</dd></div><div><dt>Expected replacement</dt><dd>{formatDateOnly(asset.expected_replacement_date)}</dd></div><div><dt>Business owner</dt><dd>{asset.business_owner||"Unknown"}</dd></div><div><dt>Technical owner</dt><dd>{asset.technical_owner||"Unknown"}</dd></div><div><dt>Vendor / procurement</dt><dd>{asset.supplier?.name||"Not recorded"}{asset.acquisition?` · ${asset.acquisition.procurement_number}`:""}</dd></div><div><dt>Metadata source</dt><dd>{asset.source}</dd></div></dl>{asset.lifecycle_history.length>0&&<><h3>Lifecycle history</h3><ol className="lifecycle-timeline">{asset.lifecycle_history.map(event=><li key={event.id}><strong>{event.new_status.replaceAll("_"," ")}</strong><span>{formatDateTime(event.created_at)} · {event.changed_by_name}</span>{event.reason&&<p>{event.reason}</p>}{event.notes&&<p>{event.notes}</p>}</li>)}</ol></>}</section>}
          <nav className="detail-tabs" aria-label="Device detail sections">
            {tabs.map((tab) => <button key={tab.id} className={activeTab === tab.id ? "active" : ""} aria-current={activeTab === tab.id ? "page" : undefined} onClick={() => setActiveTab(tab.id)}>{tab.label}</button>)}
          </nav>

          {activeTab === "overview" ? <DeviceOverview device={device} health={health} discoveryIdentity={discoveryIdentity} networkZone={hierarchy.data?.network_zones.find((zone) => zone.id === device.network_zone_id)?.name ?? ""} /> : <DeviceHistory device={device} section={activeTab} />}
        </>
      )}

      {confirmingRetirement && device && <ConfirmationModal
        title="Retire device"
        confirmLabel="Confirm retirement"
        busyLabel="Retiring..."
        busy={retiring}
        error={retireError}
        onCancel={() => setConfirmingRetirement(false)}
        onConfirm={() => void retire()}
      >
        <p>Retire <strong>{device.hostname}</strong>? The device record and all historical scans, alerts, tickets, and audit activity will remain available.</p>
        <p className="confirmation-warning">This action should only be used when the asset has been permanently removed from service.</p>
      </ConfirmationModal>}
    </DashboardLayout>
  );
}

type DesktopDeviceAction = "ping" | "trace" | "http" | "https";

function DeviceActions({ device, role, onNotice, onError, onRescan }: { device: Device; role?: User["role"]; onNotice: (message: string) => void; onError: (message: string) => void; onRescan: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const target = device.ip_address || device.hostname;
  const validTarget = Boolean(target && /^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$/.test(target) && !target.includes(".."));
  const canManageNetwork = role === "admin" || role === "technician";
  const canOpenWeb = validTarget;
  const hasActions = canOpenWeb || (isDesktopMode && validTarget && canManageNetwork) ||
    (canManageNetwork && Boolean(device.ip_address)) ||
    Boolean(device.ip_address || device.hostname || device.mac_address);
  const run = async (action: DesktopDeviceAction, label: string) => {
    if (!validTarget) { onError("This device has no usable hostname or IP address to use."); return; }
    setBusy(true);
    try {
      const desktop = (window as Window & { hiopDesktop?: { runDeviceAction?: (action: DesktopDeviceAction, target: string) => Promise<{ ok: boolean }> } }).hiopDesktop;
      if (desktop?.runDeviceAction) await desktop.runDeviceAction(action, target);
      else if (action === "http" || action === "https") {
        if (!window.open(`${action}://${target}`, "_blank", "noopener,noreferrer")) {
          throw new Error("The browser blocked the device address. Allow pop-ups and try again.");
        }
      }
      else throw new Error("This action is available in HIOP Desktop on Windows.");
      onNotice(`${label} opened for ${target}.`); setOpen(false);
    } catch (error) { onError(error instanceof Error ? error.message : "The device action could not be started."); }
    finally { setBusy(false); }
  };
  const copy = async (label: string, value?: string | null) => {
    if (!value) { onNotice(`No ${label.toLowerCase()} is recorded for this device.`); return; }
    try { await navigator.clipboard.writeText(value); onNotice(`${label} copied.`); setOpen(false); }
    catch { onError(`Could not copy the ${label.toLowerCase()}.`); }
  };
  const rescan = async () => {
    setBusy(true);
    try { await onRescan(); setOpen(false); }
    catch (error) { onError(error instanceof Error ? error.message : "The rescan could not be started."); }
    finally { setBusy(false); }
  };
  if (!hasActions) return null;
  return <div className="device-actions-menu">
    <button className="secondary-action" type="button" onClick={() => setOpen(value => !value)} aria-expanded={open} aria-haspopup="menu">Device actions</button>
    {open && <div className="device-actions-popover" role="menu" aria-label={`Actions for ${device.hostname || "device"}`}>
      {(isDesktopMode && validTarget && canManageNetwork) && <>
        <p>Network tools</p>
        <div><button type="button" role="menuitem" disabled={busy} onClick={() => void run("ping", "Ping")}>Ping</button><button type="button" role="menuitem" disabled={busy} onClick={() => void run("trace", "Trace route")}>Trace route</button></div>
      </>}
      {canOpenWeb && <div><button type="button" role="menuitem" disabled={busy} onClick={() => void run("http", "HTTP")}>Open HTTP</button><button type="button" role="menuitem" disabled={busy} onClick={() => void run("https", "HTTPS")}>Open HTTPS</button></div>}
      {canManageNetwork && device.ip_address && <button type="button" role="menuitem" onClick={() => void rescan()} disabled={busy}>Rescan connectivity</button>}
      {(device.ip_address || device.hostname || device.mac_address) && <>
        <p>Copy identity</p>
        <div>
          {device.ip_address && <button type="button" role="menuitem" onClick={() => void copy("IP address", device.ip_address)}>Copy IP</button>}
          {device.hostname && <button type="button" role="menuitem" onClick={() => void copy("Hostname", device.hostname)}>Copy hostname</button>}
          {device.mac_address && <button type="button" role="menuitem" onClick={() => void copy("MAC address", device.mac_address)}>Copy MAC</button>}
        </div>
      </>}
    </div>}
  </div>;
}

function DeviceOverview({ device, health, networkZone, discoveryIdentity }: { device: Device; health?:DeviceHealth; networkZone: string; discoveryIdentity?: Record<string, unknown> }) {
  const identity=(discoveryIdentity?.result||{}) as Record<string,unknown>;
  const evidence=(discoveryIdentity?.evidence||[]) as Array<Record<string,unknown>>;
  const conflicts=(discoveryIdentity?.conflicts||[]) as Array<Record<string,unknown>>;
  const history=(discoveryIdentity?.identity_history||[]) as Array<Record<string,unknown>>;
  return <section className="device-details" aria-label={`Details for ${device.hostname}`}>
    <header><div className="overview-statuses"><span>Inventory</span><StatusBadge status={device.inventory_status} /><span>Network</span><StatusBadge status={device.network_status} /></div></header>
    <dl>
      <Detail label="Device ID" value={device.id} />
      <Detail label="Asset Tag" value={device.asset_tag} />
      <Detail label="Hostname" value={device.hostname} />
      <Detail label="Device Type" value={device.device_type} />
      <Detail label="Brand" value={device.brand} />
      <Detail label="Model" value={device.model} />
      <Detail label="Serial Number" value={device.serial_number || "Not verified"} />
      <Detail label="Department" value={device.department} />
      <Detail label="Location" value={device.location} />
      <Detail label="Network Zone" value={networkZone} />
      <Detail label="IP Address" value={device.ip_address} />
      <Detail label="MAC Address" value={device.mac_address || "Unknown"} />
      <Detail label="Inventory Status" value={device.inventory_status} />
      <Detail label="Network Status" value={device.network_status} />
    </dl>
    <h2>Current health</h2>
    {!health?<div className="port-unknown"><strong>Health: Unknown</strong><span>Monitoring data is unavailable.</span></div>:<><dl><Detail label="Health" value={health.health}/><Detail label="Current status" value={health.status}/><Detail label="Availability (24h)" value={health.availability_percent==null?"Not enough historical data yet.":`${health.availability_percent}%`}/><Detail label="Current latency" value={health.latency?.current==null?"Not available":`${health.latency.current} ms`}/><Detail label="Average / min / max latency" value={!health.latency?"Not enough historical data yet.":`${health.latency.average} / ${health.latency.minimum} / ${health.latency.maximum} ms`}/><Detail label="Packet loss" value={health.packet_loss_percent==null?"Not enough historical data yet.":`${health.packet_loss_percent}%`}/><Detail label="Last check" value={health.last_check?formatDateTime(health.last_check):"Never"}/><Detail label="Evidence confidence" value={health.confidence}/><Detail label="Evidence" value={health.reasons.join("; ")}/><Detail label="ICMP source" value={health.source_status.icmp}/></dl><h2>Latency history</h2>{health.observations.length<2?<p>Not enough historical data yet.</p>:<div className="health-bars" aria-label="Latency history chart">{health.observations.map(point=><i key={point.id} title={`${formatDateTime(point.timestamp)}: ${point.latency_ms??"no response"}`} style={{height:`${Math.max(4,Math.min(100,point.latency_ms??4))}%`}}/>)}</div>}</>}
    {discoveryIdentity && <>
      <h2>Discovery identity</h2>
      <dl>
        <Detail label="Friendly Name" value={String(identity.friendly_name||"Unknown")} />
        <Detail label="Original Hostname" value={String(identity.primary_hostname||"Not available")} />
        <Detail label="FQDN" value={String(identity.fqdn||"Not available")} />
        <Detail label="Device Role" value={String(identity.device_type||identity.classification||"Unknown")} />
        <Detail label="Technical Classification" value={String(identity.classification||"Not available")} />
        <Detail label="Department" value={String(identity.department||"Not available")} />
        <Detail label="Vendor / Model" value={`${String(identity.vendor||"Unknown")} / ${String(identity.model||"Not available")}`} />
        <Detail label="Confidence" value={`${String(identity.confidence_score||0)}% · ${String(identity.confidence_level||"low").replaceAll("_"," ")}`} />
        <Detail label="Confidence reason" value={String(identity.confidence_reason||"Insufficient identifying evidence.")} />
        <Detail label="Evidence sources" value={[...new Set(evidence.map(item=>String(item.source||"Discovery")))].join(", ")||"Not available"} />
        <Detail label="Conflicts" value={conflicts.filter(item=>item.status==="open").length?`${conflicts.filter(item=>item.status==="open").length} conflict(s) require review`:"None detected"} />
        <Detail label="Identity history" value={history.length?`${history.length} recorded change(s)`:"No identity changes recorded"} />
      </dl>
    </>}
    <h2>Windows / Active Directory</h2>
    <dl>
      <Detail label="Domain" value={device.ad_domain || "Not available"} />
      <Detail label="Computer" value={device.ad_computer_name || "Not available"} />
      <Detail label="Operating System" value={device.ad_operating_system || "Not available"} />
      <Detail label="OS Version" value={device.ad_operating_system_version || "Not available"} />
      <Detail label="Organizational Unit" value={device.ad_organizational_unit || "Not available"} />
      <Detail label="AD Description" value={device.ad_description || "Not available"} />
      <Detail label="AD Status" value={device.ad_enabled === true ? "Enabled" : device.ad_enabled === false ? "Disabled" : "Not available"} />
      <Detail label="Last Logon" value={device.ad_last_logon_at ? formatDateTime(device.ad_last_logon_at) : "Not available"} />
      <Detail label="Distinguished Name" value={device.ad_distinguished_name || "Not available"} />
    </dl>
  </section>;
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value || "Not recorded"}</dd></div>;
}
