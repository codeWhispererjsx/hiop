import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { Feedback } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { useRequest } from "../hooks/useRequest";
import { endpoints } from "../lib/api";
import type { Device } from "../lib/types";
import "../styles/dashboard-improvements.css";
export { PageTitle } from "../components/PageTitle";

export default function DashboardPage() {
  const dashboard = useRequest(endpoints.dashboard, []);
  const inventory = useRequest(endpoints.devices, []);
  const [query, setQuery] = useState("");
  
  // Handle both array and paginated response structures
  const devices = useMemo(() => {
    if (!inventory.data) return [];
    if (Array.isArray(inventory.data)) return inventory.data;
    if (inventory.data.items && Array.isArray(inventory.data.items)) return inventory.data.items;
    return [];
  }, [inventory.data]);
  
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

  return (
    <DashboardLayout>
      <div className="asset-dashboard-title">
        <div>
          <p className="page-kicker">Infrastructure inventory</p>
          <h1>Assets</h1>
          <p>Discover, identify, and manage every device from one workspace.</p>
        </div>
        <div className="asset-dashboard-actions">
          <Link className="secondary-action" to="/devices">View inventory</Link>
          <Link className="primary-action" to="/discovery-intelligence">
            <Icon name="discovery" aria-hidden="true" />
            Discover devices
          </Link>
        </div>
      </div>

      {dashboard.loading || inventory.loading ? (
        <Feedback loading={true} />
      ) : dashboard.error || inventory.error ? (
        <Feedback error={dashboard.error || inventory.error} />
      ) : !d ? (
        <Feedback loading={true} />
      ) : (
        <>
          <section className="asset-summary-grid" aria-label="Asset metrics">
            <article className="asset-metric-card">
              <span>Total assets</span>
              <strong>{d.devices.total}</strong>
              <small>Approved inventory records</small>
            </article>
            <article className="asset-metric-card">
              <span>Online now</span>
              <strong>{d.devices.online}</strong>
              <small>
                {d.devices.total
                  ? `${Math.round((d.devices.online / d.devices.total) * 100)}% available`
                  : "Waiting for your first discovery"}
              </small>
            </article>
            <article className="asset-metric-card">
              <span>Offline devices</span>
              <strong>{d.devices.offline}</strong>
              <small>Require technician attention</small>
            </article>
            <article className="asset-metric-card">
              <span>Awaiting approval</span>
              <strong>0</strong>
              <small>Review in Discover</small>
            </article>
            <article className="asset-metric-card">
              <span>Active incidents</span>
              <strong>0</strong>
              <small>Open maintenance records</small>
            </article>
            <article className="asset-metric-card">
              <span>Active alerts</span>
              <strong>0</strong>
              <small>Open or acknowledged alerts</small>
            </article>
            <article className="asset-insight-card">
              <header>
                <h2>Types of assets</h2>
                <span>{types.length} types</span>
              </header>
              <Distribution rows={types} />
            </article>
            <article className="asset-insight-card">
              <header>
                <h2>Assets by location</h2>
                <span>Top locations</span>
              </header>
              <Distribution rows={locations} />
            </article>
          </section>

          <section className="asset-inventory-panel" aria-label="Asset inventory">
            <header className="asset-inventory-head">
              <div>
                <h2>Asset inventory</h2>
                <p>
                  {devices.length
                    ? `${devices.length} managed devices`
                    : "Your inventory is clean and ready."}
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
    } catch (e) {
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
            <span className="status-badge">Active</span>
          </div>
        </div>
      ))}
    </div>
  );
}