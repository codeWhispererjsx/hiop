import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { Feedback } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { PageTitle } from "../components/PageTitle";
import { StatusBadge } from "../components/StatusBadge";
import { useRequest } from "../hooks/useRequest";
import { endpoints, getPaginatedItems } from "../lib/api";
import type { Device } from "../lib/types";
import "../styles/dashboard-improvements.css";
export { PageTitle } from "../components/PageTitle";

export default function DashboardPage() {
  const dashboard = useRequest(endpoints.dashboard, []);
  const inventory = useRequest(endpoints.devices, []);
  const managedAssets = useRequest(() => endpoints.assetPage({ page_size: "1" }), []);
  const systemHealth = useRequest(endpoints.systemHealthReport, []);
  const serviceSummary = useRequest(endpoints.serviceManagementSummary, []);
  const alerts = useRequest(endpoints.alerts, []);
  const activeAlerts = alerts.data?.filter((alert) => !alert.acknowledged).length;
  const [query, setQuery] = useState("");
  
  const devices = useMemo(() => getPaginatedItems(inventory.data), [inventory.data]);
  
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
  const totalAssets = Array.isArray(managedAssets.data)
    ? managedAssets.data.length
    : managedAssets.data?.total ?? 0;

  return (
    <DashboardLayout>
      <PageTitle
        eyebrow="Infrastructure inventory"
        title="Overview"
        copy="Discover, identify, and manage every device from one workspace."
        action={<div className="asset-dashboard-actions">
          <Link className="secondary-action" to="/devices">View inventory</Link>
          <Link className="primary-action" to="/discovery-intelligence">
            <Icon name="discovery" aria-hidden="true" />
            Discover devices
          </Link>
        </div>}
      />

      {dashboard.loading || inventory.loading || managedAssets.loading ? (
        <Feedback loading={true} />
      ) : dashboard.error || inventory.error || managedAssets.error ? (
        <Feedback error={dashboard.error || inventory.error || managedAssets.error} />
      ) : !d ? (
        <Feedback loading={true} />
      ) : (
        <>
          <section className="asset-summary-grid" aria-label="Asset metrics">
            <Link className="asset-metric-card" to="/devices">
              <span>Total assets</span>
              <strong>{totalAssets}</strong>
              <small>Approved managed-asset records</small>
            </Link>
            <Link className="asset-metric-card" to="/network">
              <span>Online now</span>
              <strong>{d.devices.online}</strong>
              <small>
                {d.devices.total
                  ? `${Math.round((d.devices.online / d.devices.total) * 100)}% available`
                  : "Waiting for your first discovery"}
              </small>
            </Link>
            <Link className="asset-metric-card" to="/network">
              <span>Offline devices</span>
              <strong>{d.devices.offline}</strong>
              <small>Require technician attention</small>
            </Link>
            <Link className="asset-metric-card" to="/discovery-intelligence">
              <span>Awaiting approval</span>
              <strong className="asset-metric-action">Review</strong>
              <small>New discoveries waiting in Discover</small>
            </Link>
            <Link className="asset-metric-card" to="/incidents">
              <span>Active incidents</span>
              <strong>{serviceSummary.data?.open ?? "–"}</strong>
              <small>Open incident records</small>
            </Link>
            <Link className="asset-metric-card" to="/alerts">
              <span>Active alerts</span>
              <strong>{activeAlerts ?? "–"}</strong>
              <small>Unacknowledged alerts</small>
            </Link>
            <article className="asset-insight-card">
              <header>
                <h2>Devices by type</h2>
                <span>{types.length} types</span>
              </header>
              <Distribution rows={types} />
            </article>
            <article className="asset-insight-card">
              <header>
                <h2>Devices by location</h2>
                <span>Top locations</span>
              </header>
              <Distribution rows={locations} />
            </article>
          </section>

          <section className="asset-inventory-panel" aria-label="Device inventory">
            <header className="asset-inventory-head">
              <div>
                <h2>Device inventory</h2>
                <p>
                  {devices.length
                    ? `${devices.length} managed devices${devices.length > 10 ? " · showing 10" : ""}`
                    : "No devices yet. Run a discovery scan to add them."}
                </p>
              </div>
              <label className="asset-search" htmlFor="asset-search">
                <Icon name="search" aria-hidden="true" />
                <input
                  id="asset-search"
                  type="search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search assets"
                  aria-label="Search assets"
                />
              </label>
            </header>
            {visible.length ? (
              <AssetTable devices={visible} />
            ) : (
              <div className="asset-empty">
                <span>
                  <Icon name="discovery" size={28} aria-hidden="true" />
                </span>
                <h3>{query ? "No matching assets" : "Discover your first device"}</h3>
                <p>
                  {query
                    ? "Try adjusting your search terms"
                    : "Run a discovery scan to populate your inventory"}
                </p>
                <Link className="primary-action" to="/discovery-intelligence">
                  <Icon name="discovery" aria-hidden="true" />
                  Discover devices
                </Link>
              </div>
            )}
          </section>

          <section className="system-health-overview" aria-label="System Health - Update and Cool Off Status">
            <header>
              <div><p className="page-kicker">System health</p><h2>Update &amp; Cool Off Status</h2></div>
              <Link className="secondary-action" to="/reports/system-maintenance">Open maintenance report</Link>
            </header>
            {systemHealth.loading || systemHealth.error || !systemHealth.data ? (
              <Feedback loading={systemHealth.loading} error={systemHealth.error} onRetry={systemHealth.reload} />
            ) : (
              <div className="system-health-cards">
                <Link to="/reports/system-maintenance" className="system-health-card tone-warning"><span>Systems needing update</span><strong>{systemHealth.data.summary.updates_needed}</strong><small>Windows update older than 7 days</small></Link>
                <Link to="/reports/system-maintenance" className={`system-health-card ${systemHealth.data.summary.restarts_needed > 5 ? "tone-danger" : systemHealth.data.summary.restarts_needed ? "tone-warning" : "tone-good"}`}><span>Endpoints with uptime over 48 hours</span><strong>{systemHealth.data.summary.restarts_needed}</strong><small>Review heartbeat and update health</small></Link>
                <Link to="/reports/system-maintenance" className="system-health-card tone-info"><span>Legacy cool-off records</span><strong>{systemHealth.data.summary.cooled_off_last_night}</strong><small>Historical data only; controls are disabled</small></Link>
                <Link to="/reports/system-maintenance" className={`system-health-card ${systemHealth.data.summary.hygiene_score > 80 ? "tone-good" : systemHealth.data.summary.hygiene_score >= 50 ? "tone-warning" : "tone-danger"}`}><span>System hygiene score</span><strong>{systemHealth.data.summary.hygiene_score}%</strong><small>Online, recently restarted, and updated</small><i><b style={{ width: `${systemHealth.data.summary.hygiene_score}%` }} /></i></Link>
              </div>
            )}
          </section>
        </>
      )}
    </DashboardLayout>
  );
}

function summarize(devices: Device[], key: (device: Device) => string) {
  if (!Array.isArray(devices)) return [];
  const counts = new Map<string, number>();
  devices.forEach((device) => {
    try {
      const keyValue = key(device);
      counts.set(keyValue, (counts.get(keyValue) ?? 0) + 1);
    } catch {
      // Skip if key function fails
    }
  });
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4);
}

function Distribution({ rows }: { rows: [string, number][] }) {
  const maximum = Math.max(1, ...rows.map(([, count]) => count));
  if (!rows.length) return <p className="asset-card-empty">No asset data yet</p>;
  return (
    <div className="asset-distribution">
      {rows.map(([label, count]) => (
        <div key={label}>
          <span>{label}</span>
          <strong>{count}</strong>
          <i>
            <div style={{ width: `${(count / maximum) * 100}%` }} />
          </i>
        </div>
      ))}
    </div>
  );
}

function AssetTable({ devices }: { devices: Device[] }) {
  return (
    <div className="data-table">
      <div className="table-row table-head">
        <div>Device</div>
        <div>IP Address</div>
        <div>Type</div>
        <div>Status</div>
      </div>
      {devices.slice(0, 10).map((device) => (
        <div className="table-row" key={device.id}>
          <div className="primary-cell">
            <div className="row-icon">
              <Icon name="devices" size={16} aria-hidden="true" />
            </div>
            <strong>{device.hostname || device.ip_address}</strong>
          </div>
          <div>{device.ip_address}</div>
          <div>{device.device_type || "Unknown"}</div>
          <div>
            <StatusBadge status={device.network_status || device.status || "unknown"} />
          </div>
        </div>
      ))}
    </div>
  );
}
