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
import type { Device, DeviceHealth, LiveEvent, ManagedAsset, V3ATopologyNeighbors, V3BDeviceConnection, V3BSwitchInterfaces, V3CDeviceVlan, V3CVlan } from "../lib/types";
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
  const [topologyNeighbors, setTopologyNeighbors] = useState<V3ATopologyNeighbors>();
  const [portConnection, setPortConnection] = useState<V3BDeviceConnection>();
  const [switchInterfaces, setSwitchInterfaces] = useState<V3BSwitchInterfaces>();
  const [segmentation, setSegmentation] = useState<V3CDeviceVlan>();
  const [switchVlans, setSwitchVlans] = useState<V3CVlan[]>([]);
  const [health,setHealth]=useState<DeviceHealth>();
  const [asset,setAsset]=useState<ManagedAsset>();
  const [refreshingPorts, setRefreshingPorts] = useState(false);
  const [portNotice, setPortNotice] = useState("");
  useEffect(() => {
    let active = true;
    endpoints.inventoryDiscoveryIdentity(id).then((value) => { if (active) setDiscoveryIdentity(value); }).catch(() => { if (active) setDiscoveryIdentity(undefined); });
    return () => { active = false; };
  }, [id]);
  useEffect(()=>{let active=true;endpoints.deviceAsset(id).then(value=>{if(active)setAsset(value)}).catch(()=>{if(active)setAsset(undefined)});return()=>{active=false}},[id]);
  useEffect(() => {
    let active = true;
    endpoints.v3bDeviceConnection(id).then((value) => { if (active) setPortConnection(value); }).catch(() => { if (active) setPortConnection(undefined); });
    endpoints.v3bSwitchInterfaces(id).then((value) => { if (active) setSwitchInterfaces(value); }).catch(() => { if (active) setSwitchInterfaces(undefined); });
    endpoints.v3cDeviceVlan(id).then((value) => { if (active) setSegmentation(value); }).catch(() => { if (active) setSegmentation(undefined); });
    endpoints.v3cVlans({switch:device?.hostname}).then((value) => { if (active) setSwitchVlans(value.items); }).catch(() => { if (active) setSwitchVlans([]); });
    endpoints.deviceHealth(id,"24h").then(value=>{if(active)setHealth(value)}).catch(()=>{if(active)setHealth(undefined)});
    return () => { active = false; };
  }, [id,device?.hostname]);
  useEffect(() => {
    let active = true;
    endpoints.v3aDeviceNeighbors(id).then((value) => { if (active) setTopologyNeighbors(value); }).catch(() => { if (active) setTopologyNeighbors(undefined); });
    return () => { active = false; };
  }, [id]);
  const hierarchy = useRequest(endpoints.hierarchy, []);
  const currentUser = useRequest(endpoints.me, []);
  const [activeTab, setActiveTab] = useState<DetailsTab>("overview");
  const [confirmingRetirement, setConfirmingRetirement] = useState(false);
  const [retiring, setRetiring] = useState(false);
  const [retireError, setRetireError] = useState("");
  const [retireNotice, setRetireNotice] = useState("");

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
  const refreshPorts = async () => {
    setRefreshingPorts(true); setPortNotice("");
    try {
      const result = await endpoints.refreshV3BSwitch(id);
      setPortNotice(result.message);
      setSwitchInterfaces(await endpoints.v3bSwitchInterfaces(id));
      setPortConnection(await endpoints.v3bDeviceConnection(id));
    } catch (requestError) {
      setPortNotice(requestError instanceof Error ? requestError.message : "Port intelligence refresh failed.");
    } finally { setRefreshingPorts(false); }
  };

  return (
    <DashboardLayout onLiveEvent={handleLiveEvent}>
      <PageTitle
        eyebrow="Asset inventory"
        title={device?.hostname ?? "Device details"}
        copy="Complete device information and operational history from HIOP."
        action={<div className="page-actions">
          <Link className="secondary-action" to="/devices">Back to devices</Link>
          {device && !isRetired && currentUser.data?.role === "admin" && <>
            <Link className="primary-action" to={`/devices/${id}/edit`}>Edit device</Link>
            {currentUser.data?.role === "admin" && <button className="danger-action" onClick={() => { setRetireError(""); setConfirmingRetirement(true); }}>Retire device</button>}
          </>}
        </div>}
      />

      {(retireNotice || successNotice) && <Toast message={retireNotice || successNotice || "Device updated successfully."} />}

      {loading || error ? (
        <Feedback loading={loading} error={error} onRetry={reload} />
      ) : !device ? (
        <Feedback emptyTitle="Device not found" empty="No device information is available." />
      ) : (
        <>
          {isRetired && <div className="retired-banner"><StatusBadge status="Retired" /><span>This asset is retired. Its details and operational history remain available.</span></div>}
          {asset&&<section className="panel"><header className="section-head"><div><span>Managed asset</span><h2>{asset.asset_number}</h2><p>{asset.asset_tag||"No human-readable asset tag assigned"} · {asset.ci_category}</p></div>{currentUser.data?.role==="admin"&&<Link className="secondary-action" to={`/assets/${asset.id}/edit`}>Edit asset metadata</Link>}</header><dl className="settings-readonly"><div><dt>Lifecycle status</dt><dd>{asset.status.replace("_"," ")}</dd></div><div><dt>Business owner</dt><dd>{asset.business_owner||"Unknown"}</dd></div><div><dt>Technical owner</dt><dd>{asset.technical_owner||"Unknown"}</dd></div><div><dt>Metadata source</dt><dd>{asset.source}</dd></div></dl></section>}
          <nav className="detail-tabs" aria-label="Device detail sections">
            {tabs.map((tab) => <button key={tab.id} className={activeTab === tab.id ? "active" : ""} aria-current={activeTab === tab.id ? "page" : undefined} onClick={() => setActiveTab(tab.id)}>{tab.label}</button>)}
          </nav>

          {activeTab === "overview" ? <DeviceOverview device={device} health={health} discoveryIdentity={discoveryIdentity} topologyNeighbors={topologyNeighbors} portConnection={portConnection} switchInterfaces={switchInterfaces} segmentation={segmentation} switchVlans={switchVlans} canRefreshPorts={currentUser.data?.role==="admin"} refreshingPorts={refreshingPorts} portNotice={portNotice} onRefreshPorts={()=>void refreshPorts()} networkZone={hierarchy.data?.network_zones.find((zone) => zone.id === device.network_zone_id)?.name ?? ""} /> : <DeviceHistory device={device} section={activeTab} />}
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

function DeviceOverview({ device, health, networkZone, discoveryIdentity, topologyNeighbors, portConnection, switchInterfaces, segmentation, switchVlans, canRefreshPorts, refreshingPorts, portNotice, onRefreshPorts }: { device: Device; health?:DeviceHealth; networkZone: string; discoveryIdentity?: Record<string, unknown>; topologyNeighbors?: V3ATopologyNeighbors; portConnection?:V3BDeviceConnection; switchInterfaces?:V3BSwitchInterfaces; segmentation?:V3CDeviceVlan; switchVlans:V3CVlan[]; canRefreshPorts:boolean; refreshingPorts:boolean; portNotice:string; onRefreshPorts:()=>void }) {
  const [portSearch,setPortSearch]=useState("");
  const [portFilter,setPortFilter]=useState<"all"|"active"|"unknown">("all");
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
      <Detail label="Serial Number" value={device.serial_number} />
      <Detail label="Department" value={device.department} />
      <Detail label="Location" value={device.location} />
      <Detail label="Network Zone" value={networkZone} />
      <Detail label="IP Address" value={device.ip_address} />
      <Detail label="MAC Address" value={device.mac_address || "Unknown"} />
      <Detail label="Inventory Status" value={device.inventory_status} />
      <Detail label="Network Status" value={device.network_status} />
    </dl>
    <h2>Current health</h2>
    {!health?<div className="port-unknown"><strong>Health: Unknown</strong><span>Monitoring data is unavailable.</span></div>:<><dl><Detail label="Health" value={health.health}/><Detail label="Current status" value={health.status}/><Detail label="Availability (24h)" value={health.availability_percent==null?"Not enough historical data yet.":`${health.availability_percent}%`}/><Detail label="Current latency" value={health.latency?.current==null?"Not available":`${health.latency.current} ms`}/><Detail label="Average / min / max latency" value={!health.latency?"Not enough historical data yet.":`${health.latency.average} / ${health.latency.minimum} / ${health.latency.maximum} ms`}/><Detail label="Packet loss" value={health.packet_loss_percent==null?"Not enough historical data yet.":`${health.packet_loss_percent}%`}/><Detail label="Last check" value={health.last_check?new Date(health.last_check).toLocaleString():"Never"}/><Detail label="Evidence confidence" value={health.confidence}/><Detail label="Evidence" value={health.reasons.join("; ")}/><Detail label="ICMP source" value={health.source_status.icmp}/><Detail label="SNMP source" value={health.source_status.snmp}/></dl><h2>Hardware / system telemetry</h2><dl>{(["cpu","memory","temperature","uptime"] as const).map(key=><Detail key={key} label={key[0].toUpperCase()+key.slice(1)} value={health.telemetry[key]?`${health.telemetry[key]!.current} ${health.telemetry[key]!.unit}`:"Not available"}/>)}</dl><h2>Latency history</h2>{health.observations.length<2?<p>Not enough historical data yet.</p>:<div className="health-bars" aria-label="Latency history chart">{health.observations.map(point=><i key={point.id} title={`${new Date(point.timestamp).toLocaleString()}: ${point.latency_ms??"no response"}`} style={{height:`${Math.max(4,Math.min(100,point.latency_ms??4))}%`}}/>)}</div>}</>}
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
      <Detail label="Last Logon" value={device.ad_last_logon_at ? new Date(device.ad_last_logon_at).toLocaleString() : "Not available"} />
      <Detail label="Distinguished Name" value={device.ad_distinguished_name || "Not available"} />
    </dl>
    <h2>Network connection</h2>
    {!portConnection||!portConnection.current?<div className="port-unknown"><strong>Port: Unknown</strong><span>{portConnection?.message||"Port-level information unavailable."}</span></div>:<div className="device-port-connection"><dl>
      <Detail label="Connected switch" value={portConnection.current.switch.hostname}/>
      <Detail label="Port" value={portConnection.current.interface?.name||"Unknown"}/>
      <Detail label="Interface description" value={portConnection.current.interface?.description||"Not available"}/>
      <Detail label="Administrative status" value={portConnection.current.interface?.admin_status||"Unknown"}/>
      <Detail label="Operational status" value={portConnection.current.interface?.operational_status||"Unknown"}/>
      <Detail label="Speed" value={formatSpeed(portConnection.current.interface?.speed_bps)}/>
      <Detail label="Duplex" value={portConnection.current.interface?.duplex||"Unknown"}/>
      <Detail label="Last verified" value={new Date(portConnection.current.last_observed_at).toLocaleString()}/>
      <Detail label="Confidence" value={`${portConnection.current.confidence}% · ${portConnection.current.confidence_level}`}/>
      <Detail label="Evidence" value={portConnection.current.evidence.map(item=>item.source.replaceAll("_"," ")).join(", ")}/>
    </dl>{portConnection.history.length>0&&<p>{portConnection.history.length} historical/stale port association(s) preserved.</p>}</div>}
    <h2>Segmentation</h2>
    {!segmentation?.current.length?<div className="port-unknown"><strong>VLAN: Unknown</strong><span>{segmentation?.message||"Port-level VLAN information unavailable."}</span></div>:<>{segmentation.current.map((row,index)=><dl key={`${row.vlan.id}-${index}`}><Detail label="VLAN" value={String(row.vlan.vlan_id)}/><Detail label="VLAN Name" value={row.vlan.name}/><Detail label="Subnet" value={row.vlan.subnet||"Unknown"}/><Detail label="Gateway" value={row.vlan.gateway||"Unknown"}/><Detail label="Switch" value={row.switch.hostname}/><Detail label="Port" value={row.interface.name||"Unknown"}/><Detail label="Mode" value={row.port_mode}/><Detail label="Confidence" value={`${row.confidence}% · ${row.confidence_level}`}/><Detail label="Evidence" value={row.evidence.map(item=>item.source.replaceAll("_"," ")).join(", ")}/><Detail label="Last verified" value={new Date(row.last_observed_at).toLocaleString()}/></dl>)}{segmentation.history.length>0&&<p>{segmentation.history.length} historical/stale VLAN relationship(s) preserved.</p>}</>}
    <h2>Network connections</h2>
    {!topologyNeighbors?<p>Topology data unavailable.</p>:topologyNeighbors.connections.length===0?<p>{topologyNeighbors.message || "No connections found for this device."}</p>:<div className="device-topology-connections">{topologyNeighbors.connections.map(connection=><article key={connection.id}><div><strong>{connection.neighbor.label}</strong><span>{connection.relationship_type.replaceAll("_"," ")} · {connection.confidence}% confidence</span><small>{connection.evidence_source.replaceAll("_"," ")} · last verified {new Date(connection.last_verified_at).toLocaleString()}</small></div><Link to={`/devices/${connection.neighbor.device_id}`}>Open connected device</Link></article>)}</div>}
    <Link className="secondary-action" to="/topology">Open network topology</Link>
    {switchVlans.length>0&&<section className="switch-interface-section"><header><div><h2>VLANs</h2><p>Observed switch segmentation. Read-only.</p></div><Link className="secondary-action" to="/segmentation">Open segmentation</Link></header><div className="port-table-wrap"><table><thead><tr><th>VLAN</th><th>Name</th><th>Subnet</th><th>Status</th><th>Ports</th></tr></thead><tbody>{switchVlans.map(vlan=><tr key={vlan.id}><td>{vlan.vlan_id}</td><td>{vlan.name}</td><td>{vlan.subnet||"Unknown"}</td><td><StatusBadge status={vlan.status}/></td><td>{vlan.port_count}</td></tr>)}</tbody></table></div></section>}
    {switchInterfaces&&(/switch|bridge/i.test(device.device_type)||switchInterfaces.items.length>0)&&<section className="switch-interface-section" aria-label={`Interfaces for ${device.hostname}`}>
      <header><div><h2>Interfaces / ports</h2><p>Cached, read-only switch observations. HIOP cannot change port configuration.</p></div>{canRefreshPorts&&<button className="secondary-action" onClick={onRefreshPorts} disabled={refreshingPorts}>{refreshingPorts?"Refreshing…":"Refresh port intelligence"}</button>}</header>
      {portNotice&&<p role="status" className="port-notice">{portNotice}</p>}
      <div className="port-filters"><input aria-label="Search switch ports" placeholder="Find port, description, device, or MAC" value={portSearch} onChange={event=>setPortSearch(event.target.value)}/><select aria-label="Filter switch ports" value={portFilter} onChange={event=>setPortFilter(event.target.value as "all"|"active"|"unknown")}><option value="all">All ports</option><option value="active">Active ports</option><option value="unknown">Unknown endpoints</option></select></div>
      {switchInterfaces.items.length===0?<div className="port-unknown"><strong>Port information unavailable</strong><span>{switchInterfaces.message||"No interface inventory has been collected."}</span></div>:<div className="port-table-wrap"><table><thead><tr><th>Port</th><th>Status</th><th>Description</th><th>Speed</th><th>Connected device</th><th>Confidence</th></tr></thead><tbody>{switchInterfaces.items.filter(item=>{const text=`${item.name} ${item.description} ${item.mac_address} ${item.associations.map(row=>`${row.connected_device?.hostname} ${row.observed_mac}`).join(" ")}`.toLowerCase();return text.includes(portSearch.toLowerCase())&&(portFilter!=="active"||item.operational_status==="up")&&(portFilter!=="unknown"||item.endpoint_state!=="known")}).map(item=><tr key={item.id}><td><strong>{item.name||`Interface ${item.interface_index}`}</strong><small>Admin: {item.admin_status}</small></td><td><StatusBadge status={item.operational_status}/></td><td>{item.description||"—"}</td><td>{formatSpeed(item.speed_bps)}</td><td>{item.associations.length===0?<span>Unknown</span>:item.associations.length>1?<span>Multiple/Unknown endpoint ({item.associations.length} MACs)</span>:item.associations[0].connected_device?<Link to={`/devices/${item.associations[0].connected_device.id}`}>{item.associations[0].connected_device.hostname}</Link>:<span>Unknown · {item.associations[0].observed_mac}</span>}</td><td>{item.associations[0]?`${item.associations[0].confidence}% · ${item.associations[0].confidence_level}`:"—"}</td></tr>)}</tbody></table></div>}
    </section>}
  </section>;
}

function formatSpeed(value?:number|null){if(!value)return "Unknown";if(value>=1_000_000_000)return `${value/1_000_000_000} Gbps`;if(value>=1_000_000)return `${value/1_000_000} Mbps`;return `${value} bps`}

function Detail({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value || "Not recorded"}</dd></div>;
}
