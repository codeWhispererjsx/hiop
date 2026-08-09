import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { Feedback } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { useRequest } from "../hooks/useRequest";
import { endpoints } from "../lib/api";
import type { Device } from "../lib/types";

export default function DashboardPage() {
  const dashboard = useRequest(endpoints.dashboard, []);
  const inventory = useRequest(endpoints.devices, []);
  const discoveries = useRequest(endpoints.consolidatedDiscoveryDevices, []);
  const alerts = useRequest(endpoints.alerts, []);
  const incidents = useRequest(() => endpoints.incidents({page_size:100}), []);
  const [query, setQuery] = useState("");
  const devices = useMemo(() => inventory.data ?? [], [inventory.data]);
  const visible = useMemo(() => {
    const value = query.trim().toLowerCase();
    if (!value) return devices;
    return devices.filter((device) =>
      [device.hostname, device.ip_address, device.device_type, device.brand, device.location]
        .some((field) => field?.toLowerCase().includes(value)),
    );
  }, [devices, query]);
  const types = summarize(devices, (device) => device.device_type || "Unknown");
  const locations = summarize(devices, (device) => device.location || "Unassigned");
  const d = dashboard.data;

  return <DashboardLayout>
    <div className="asset-dashboard-title">
      <div><p className="page-kicker">Infrastructure inventory</p><h1>Assets</h1><p>Discover, identify, and manage every device from one workspace.</p></div>
      <div className="asset-dashboard-actions">
        <Link className="secondary-action" to="/devices">View inventory</Link>
        <Link className="primary-action" to="/discovery-intelligence"><Icon name="discovery"/>Discover devices</Link>
      </div>
    </div>

    {dashboard.loading || inventory.loading || dashboard.error || inventory.error || !d
      ? <Feedback loading={dashboard.loading || inventory.loading} error={dashboard.error || inventory.error} onRetry={() => { void dashboard.reload(); void inventory.reload(); }}/>
      : <>
        <section className="asset-summary-grid">
          <article className="asset-metric-card"><span>Total assets</span><strong>{d.devices.total}</strong><small>Approved inventory records</small></article>
          <article className="asset-metric-card"><span>Online now</span><strong>{d.devices.online}</strong><small>{d.devices.total ? `${Math.round(d.devices.online / d.devices.total * 100)}% available` : "Waiting for your first discovery"}</small></article>
          <article className="asset-metric-card"><span>Offline devices</span><strong>{d.devices.offline}</strong><small>Require technician attention</small></article>
          <article className="asset-metric-card"><span>Awaiting approval</span><strong>{(discoveries.data?.items??[]).filter(item=>!item.inventory_device_id).length}</strong><small>Review in Discover</small></article>
          <article className="asset-metric-card"><span>Active incidents</span><strong>{(incidents.data?.items??[]).filter(item=>!["resolved","closed","cancelled"].includes(item.status)).length}</strong><small>Open maintenance records</small></article>
          <article className="asset-metric-card"><span>Recent alerts</span><strong>{(alerts.data??[]).filter(item=>!item.acknowledged).length}</strong><small>Unacknowledged events</small></article>
          <article className="asset-insight-card"><header><h2>Types of assets</h2><span>{types.length} types</span></header><Distribution rows={types}/></article>
          <article className="asset-insight-card"><header><h2>Assets by location</h2><span>Top locations</span></header><Distribution rows={locations}/></article>
        </section>

        <section className="asset-inventory-panel">
          <header className="asset-inventory-head">
            <div><h2>Asset inventory</h2><p>{devices.length ? `${devices.length} managed devices` : "Your inventory is clean and ready."}</p></div>
            <label className="asset-search"><Icon name="search"/><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search assets" aria-label="Search assets"/></label>
          </header>
          {visible.length ? <AssetTable devices={visible}/> : <div className="asset-empty">
            <span><Icon name="discovery" size={28}/></span>
            <h3>{query ? "No matching assets" : "Discover your first device"}</h3>
            <p>{query ? "Try another name, IP address, type, vendor, or location." : "Scan your network. HIOP will identify reachable devices and place the results here."}</p>
            {!query && <Link className="primary-action" to="/discovery-intelligence">Start discovery</Link>}
          </div>}
        </section>
      </>}
  </DashboardLayout>;
}

function summarize(devices: Device[], key: (device: Device) => string) {
  const counts = new Map<string, number>();
  devices.forEach((device) => counts.set(key(device), (counts.get(key(device)) ?? 0) + 1));
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4);
}

function Distribution({ rows }: { rows: [string, number][] }) {
  const maximum = Math.max(1, ...rows.map(([, count]) => count));
  if (!rows.length) return <p className="asset-card-empty">No asset data yet</p>;
  return <div className="asset-distribution">{rows.map(([label, count]) => <div key={label}><span>{label}</span><strong>{count}</strong><i><b style={{ width: `${Math.max(8, count / maximum * 100)}%` }}/></i></div>)}</div>;
}

function AssetTable({ devices }: { devices: Device[] }) {
  return <div className="asset-table-wrap"><table className="asset-table"><thead><tr><th>Asset name</th><th>Type</th><th>Vendor / model</th><th>Status</th><th>IP address</th><th>Location</th></tr></thead><tbody>{devices.slice(0, 50).map((device) => <tr key={device.id}>
    <td data-label="Asset"><Link to={`/devices/${device.id}`}><span className="asset-device-icon"><Icon name="devices"/></span><strong>{device.hostname || device.asset_tag || "Unnamed device"}</strong></Link></td>
    <td data-label="Type"><span className="asset-tag">{device.device_type || "Unknown"}</span></td>
    <td>{[device.brand, device.model].filter(Boolean).join(" · ") || "—"}</td>
    <td data-label="Status"><span className={`status-badge ${(device.network_status || "unknown").toLowerCase()}`}>{device.network_status || "Unknown"}</span></td>
    <td className="asset-mono">{device.ip_address || "—"}</td><td>{device.location || "Unassigned"}</td>
  </tr>)}</tbody></table></div>;
}

export function PageTitle({ eyebrow, title, copy, action }: { eyebrow: string; title: string; copy: string; action?: React.ReactNode }) {
  return <div className="page-title"><div><p className="page-kicker">{eyebrow}</p><h1>{title}</h1><p>{copy}</p></div>{action}</div>;
}
