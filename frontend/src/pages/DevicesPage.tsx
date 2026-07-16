import { useDeferredValue, useMemo, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { Feedback } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { StatusBadge } from "../components/StatusBadge";
import { Toast } from "../components/Toast";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import type { LiveEvent } from "../lib/types";
import { PageTitle } from "./DashboardPage";

const ROWS_PER_PAGE = 10;

export default function DevicesPage() {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const locationState = location.state as { notice?: string } | null;
  const successNotice = locationState?.notice;
  const { data: devices, loading, error, reload } = useRequest(endpoints.devices);
  const currentUser = useRequest(endpoints.me, []);
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const [status, setStatus] = useState(() => searchParams.get("status") || "All");
  const [department, setDepartment] = useState("All");
  const [page, setPage] = useState(1);
  const visibleDevices = useMemo(() => {
    const query = deferredSearch.trim().toLowerCase();
    if (!query) return devices ?? [];

    return (devices ?? []).filter((device) =>
      [
        device.asset_tag,
        device.hostname,
        device.ip_address,
        device.department,
        device.device_type,
      ].some((field) => field.toLowerCase().includes(query)),
    );
  }, [devices, deferredSearch]);
  const statuses = useMemo(
    () => uniqueValues((devices ?? []).flatMap((device) => [device.inventory_status, device.network_status]).filter((value) => value !== "Unknown")),
    [devices],
  );
  const departments = useMemo(
    () => uniqueValues((devices ?? []).map((device) => device.department)),
    [devices],
  );
  const filteredDevices = useMemo(
    () => visibleDevices.filter((device) =>
      (status === "All" || device.inventory_status.trim() === status || device.network_status.trim() === status)
      && (department === "All" || device.department.trim() === department),
    ),
    [visibleDevices, status, department],
  );
  const totalPages = Math.max(1, Math.ceil(filteredDevices.length / ROWS_PER_PAGE));
  const currentPage = Math.min(page, totalPages);
  const paginatedDevices = filteredDevices.slice(
    (currentPage - 1) * ROWS_PER_PAGE,
    currentPage * ROWS_PER_PAGE,
  );

  const handleLiveEvent = (event: LiveEvent) => {
    if (event.event === "device_status_changed") void reload();
  };

  return (
    <DashboardLayout onLiveEvent={handleLiveEvent}>
      <PageTitle
        eyebrow="Asset inventory"
        title="Devices"
        copy="View every hotel IT asset currently stored in HIOP."
        action={currentUser.data?.role === "admin" ? <Link className="primary-action" to="/devices/new"><Icon name="devices" />Add device</Link> : undefined}
      />

      {successNotice && <Toast message={successNotice} />}

      {loading || error ? (
        <Feedback
          loading={loading}
          error={error}
          onRetry={reload}
        />
      ) : (
        <>
          <section className="toolbar-panel" aria-label="Device search and filters">
            <label className="search-field">
              <Icon name="search" />
              <input
                type="search"
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value);
                  setPage(1);
                }}
                placeholder="Search devices"
                aria-label="Search devices"
              />
            </label>
            <div className="filter-row">
              <select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }} aria-label="Filter devices by status">
                <option value="All">All statuses</option>
                {statuses.map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
              <select value={department} onChange={(event) => { setDepartment(event.target.value); setPage(1); }} aria-label="Filter devices by department">
                <option value="All">All departments</option>
                {departments.map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
            </div>
          </section>

          {filteredDevices.length === 0 ? (
            <Feedback emptyTitle="No devices found" empty={search || status !== "All" || department !== "All" ? "Try different search or filter values." : "No devices have been added to the inventory yet."} />
          ) : (
            <>
              <section className="data-panel" aria-label="Device inventory">
                <div className="data-table device-table">
            <div className="table-row table-head" role="row">
              <span>Device</span>
              <span>Network</span>
              <span>Assignment</span>
              <span>Status</span>
            </div>

            {paginatedDevices.map((device) => (
              <Link className="table-row device-link" role="row" key={device.id} to={`/devices/${device.id}`}>
                <span className="primary-cell">
                  <i className="row-icon" aria-hidden="true">
                    <Icon name="devices" />
                  </i>
                  <span>
                    <strong>{device.hostname}</strong>
                    <small>{device.asset_tag} / {device.device_type}</small>
                  </span>
                </span>
                <span>
                  <strong>{device.ip_address}</strong>
                  <small>{device.mac_address}</small>
                </span>
                <span>
                  <strong>{device.department}</strong>
                  <small>{device.location}</small>
                </span>
                <span>
                  <span className="device-statuses"><StatusBadge status={device.inventory_status} /><StatusBadge status={device.network_status} /></span>
                </span>
              </Link>
            ))}
                </div>
              </section>
              <nav className="pagination" aria-label="Device inventory pages">
                <button className="secondary-action" disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}>Previous</button>
                <div className="page-numbers">
                  {Array.from({ length: totalPages }, (_, index) => index + 1).map((pageNumber) => (
                    <button
                      key={pageNumber}
                      className={pageNumber === currentPage ? "active" : ""}
                      aria-current={pageNumber === currentPage ? "page" : undefined}
                      aria-label={`Page ${pageNumber}`}
                      onClick={() => setPage(pageNumber)}
                    >
                      {pageNumber}
                    </button>
                  ))}
                </div>
                <button className="secondary-action" disabled={currentPage === totalPages} onClick={() => setPage(currentPage + 1)}>Next</button>
              </nav>
            </>
          )}
        </>
      )}
    </DashboardLayout>
  );
}

function uniqueValues(values: string[]) {
  const unique = new Map<string, string>();
  for (const value of values) {
    const trimmed = value.trim();
    if (trimmed && !unique.has(trimmed.toLowerCase())) unique.set(trimmed.toLowerCase(), trimmed);
  }
  return [...unique.values()].sort((a, b) => a.localeCompare(b));
}
