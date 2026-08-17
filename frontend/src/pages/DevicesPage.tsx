import { useDeferredValue, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Feedback } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { StatusBadge } from "../components/StatusBadge";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import type { ManagedAsset } from "../lib/types";
import { PageTitle } from "./DashboardPage";

const value = (text: string | null | undefined) => text || "Unknown";
const unique = (rows: ManagedAsset[], key: (row: ManagedAsset) => string | null) => 
  [...new Set(rows.map(key).filter(Boolean) as string[])].sort();

export default function DevicesPage() {
  const assets = useRequest(() => endpoints.assets({}), []);
  const me = useRequest(endpoints.me, []);
  const [search, setSearch] = useState("");
  const query = useDeferredValue(search).trim().toLowerCase();
  
  const [status, setStatus] = useState("All");
  const [type, setType] = useState("All");
  const [department, setDepartment] = useState("All");
  const [location, setLocation] = useState("All");
  const [health, setHealth] = useState("All");
  const [vendor, setVendor] = useState("All");
  const [condition, setCondition] = useState("All");
  const [warranty, setWarranty] = useState("All");

  const rows = useMemo(() => 
    (assets.data ?? []).filter((row) => {
      const searchable = [
        row.asset_number,
        row.asset_tag,
        row.name,
        row.hostname,
        row.ip_address,
        row.mac_address,
        row.serial_number,
      ].some((item) => item?.toLowerCase().includes(query));
      
      return (
        (!query || searchable) &&
        (status === "All" || row.status === status) &&
        (type === "All" || row.device_type === type) &&
        (department === "All" || row.department === department) &&
        (location === "All" || row.location === location) &&
        (health === "All" || row.health === health) &&
        (vendor === "All" || row.vendor === vendor) &&
        (condition === "All" || row.condition === condition) &&
        (warranty === "All" || row.warranty_status === warranty)
      );
    }), 
    [assets.data, query, status, type, department, location, health, vendor, condition, warranty]
  );
  
  const all = assets.data ?? [];
  const admin = me.data?.role === "admin";

  return (
    <DashboardLayout>
      <PageTitle 
        eyebrow="CMDB & asset intelligence" 
        title="Managed assets" 
        copy="Organizational asset identity joined to authoritative device, health, and network evidence." 
        action={admin ? (
          <Link className="primary-action" to="/assets/new">
            <Icon name="devices" aria-hidden="true" />
            Add Asset
          </Link>
        ) : undefined}
      />
      {assets.loading || assets.error ? (
        <Feedback 
          loading={assets.loading} 
          error={assets.error} 
          onRetry={assets.reload} 
        />
      ) : (
        <>
          <section className="toolbar-panel" aria-label="Asset search and filters">
            <label className="search-field" htmlFor="asset-search-input">
              <Icon name="search" aria-hidden="true" />
              <input 
                id="asset-search-input"
                type="search" 
                value={search} 
                onChange={(e) => setSearch(e.target.value)} 
                placeholder="Asset ID, tag, hostname, IP, MAC, serial, or name" 
                aria-label="Search managed assets"
              />
            </label>
            <div className="filter-row">
              <Filter label="lifecycle" value={status} set={setStatus} rows={unique(all, (x) => x.status)} />
              <Filter label="condition" value={condition} set={setCondition} rows={unique(all, (x) => x.condition)} />
              <Filter label="warranty" value={warranty} set={setWarranty} rows={unique(all, (x) => x.warranty_status)} />
              <Filter label="type" value={type} set={setType} rows={unique(all, (x) => x.device_type)} />
              <Filter label="department" value={department} set={setDepartment} rows={unique(all, (x) => x.department)} />
              <Filter label="location" value={location} set={setLocation} rows={unique(all, (x) => x.location)} />
              <Filter label="health" value={health} set={setHealth} rows={unique(all, (x) => x.health)} />
              <Filter label="vendor" value={vendor} set={setVendor} rows={unique(all, (x) => x.vendor)} />
            </div>
          </section>
          {!rows.length ? (
            <Feedback 
              emptyTitle="No managed assets yet." 
              empty="Add an asset manually, or approve a discovered device into managed inventory." 
            />
          ) : (
            <section className="data-panel" aria-label="Managed asset inventory">
              <div className="data-table device-table">
                <div className="table-row table-head" role="row">
                  <span>Asset</span>
                  <span>Technical identity</span>
                  <span>Ownership & location</span>
                  <span>Lifecycle & health</span>
                </div>
                {rows.map((row) => (
                  <Link 
                    className="table-row device-link" 
                    role="row" 
                    key={row.id} 
                    to={`/assets/${row.id}`}
                  >
                    <span className="primary-cell">
                      <i className="row-icon">
                        <Icon name="devices" aria-hidden="true" />
                      </i>
                      <span>
                        <strong>{row.name}</strong>
                        <small>{row.asset_number} · {row.asset_tag || "No asset tag"}</small>
                      </span>
                    </span>
                    <span>
                      <strong>{row.hostname || "No network identity"}</strong>
                      <small>{row.ip_address || "IP not available"} · {row.device_type}</small>
                    </span>
                    <span>
                      <strong>{value(row.department)}</strong>
                      <small>{value(row.location)} · Owner: {value(row.business_owner)}</small>
                    </span>
                    <span>
                      <span className="device-statuses">
                        <StatusBadge status={row.status.replace("_", " ")} />
                        <StatusBadge status={row.health} />
                      </span>
                      <small>
                        Warranty: {row.warranty_status.replace("_", " ")} ·{" "}
                        {row.acquisition_date 
                          ? `Acquired ${new Date(`${row.acquisition_date}T00:00:00`).toLocaleDateString()}` 
                          : "Acquisition unknown"}
                      </small>
                    </span>
                  </Link>
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </DashboardLayout>
  );
}

function Filter({ 
  label, 
  value, 
  set, 
  rows 
}: { 
  label: string; 
  value: string; 
  set: (value: string) => void; 
  rows: string[] 
}) {
  return (
    <select 
      value={value} 
      onChange={(e) => set(e.target.value)} 
      aria-label={`Filter assets by ${label}`}
    >
      <option value="All">All {label}s</option>
      {rows.map((row) => (
        <option key={row}>{row}</option>
      ))}
    </select>
  );
}
