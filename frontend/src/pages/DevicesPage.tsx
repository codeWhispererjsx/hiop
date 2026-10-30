import { useCallback, useDeferredValue, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import * as XLSX from "xlsx";
import { Feedback } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { StatusBadge } from "../components/StatusBadge";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints, getPaginatedItems } from "../lib/api";
import { downloadBrandedWordReport } from "../lib/brandedWordExport";
import type { ManagedAsset } from "../lib/types";
import { PageTitle } from "./DashboardPage";

const value = (text: string | null | undefined) => text || "Unknown";
const unique = (rows: ManagedAsset[], key: (row: ManagedAsset) => string | null) => 
  [...new Set(rows.map(key).filter(Boolean) as string[])].sort();

export default function DevicesPage() {
  const [pageSize, setPageSize] = useState("all");
  const assets = useRequest(
    () => endpoints.assets({ page_size: pageSize === "all" ? "5000" : pageSize }),
    [pageSize]
  );
  const hierarchy = useRequest(endpoints.hierarchy, []);
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
  const [exportCount, setExportCount] = useState<"50" | "100" | "all">("50");
  const [exportFormat, setExportFormat] = useState<"word" | "csv" | "excel">("word");
  const [exporting, setExporting] = useState(false);
  const [exportProgress, setExportProgress] = useState("");
  const [exportError, setExportError] = useState("");

  const all = useMemo(() => getPaginatedItems(assets.data), [assets.data]);
  const departmentOptions = useMemo(
    () => [...new Set([
      ...(hierarchy.data?.departments.filter((item) => item.is_active).map((item) => item.name) ?? []),
      ...unique(all, (item) => item.department),
    ])].sort(),
    [all, hierarchy.data],
  );
  const activeDepartment = departmentOptions.includes(department) ? department : "All";
  const filterAssets = useCallback((items: ManagedAsset[]) => items.filter((row) => {
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
        (activeDepartment === "All" || row.department === activeDepartment) &&
        (location === "All" || row.location === location) &&
        (health === "All" || row.health === health) &&
        (vendor === "All" || row.vendor === vendor) &&
        (condition === "All" || row.condition === condition) &&
        (warranty === "All" || row.warranty_status === warranty)
      );
    }), [query, status, type, activeDepartment, location, health, vendor, condition, warranty]);
  const rows = useMemo(
    () => filterAssets(all),
    [all, filterAssets]
  );
  const locationOptions = useMemo(
    () => [...new Set([
      ...(hierarchy.data?.rooms.filter((item) => item.is_active).map((item) => item.name) ?? []),
      ...unique(all, (item) => item.location),
    ])].sort(),
    [all, hierarchy.data],
  );
  const admin = me.data?.role === "admin";
  const activeFilters = [status, type, activeDepartment, location, health, vendor, condition, warranty].filter((item) => item !== "All").length;
  const exportFile = async () => {
    if (exporting) return;
    setExporting(true);
    setExportProgress("Loading filtered inventory…");
    setExportError("");
    try {
      const firstPage = await endpoints.assetPage({ page: "1", page_size: "5000" });
      const pageItems = getPaginatedItems(firstPage);
      const firstPageInfo = Array.isArray(firstPage) ? { total: pageItems.length, page_size: pageItems.length } : firstPage;
      const pageCount = Math.max(1, Math.ceil(firstPageInfo.total / Math.max(firstPageInfo.page_size, 1)));
      const inventory = [...pageItems];
      for (let page = 2; page <= pageCount; page += 1) {
        setExportProgress(`Loading inventory page ${page} of ${pageCount}…`);
        const result = await endpoints.assetPage({ page: String(page), page_size: "5000" });
        inventory.push(...getPaginatedItems(result));
      }
      const filteredRows = filterAssets(inventory);
      const selectedRows =
        exportCount === "all" ? filteredRows : filteredRows.slice(0, Number(exportCount));
      if (!selectedRows.length) throw new Error("There are no filtered assets to export.");
      setExportProgress(`Preparing ${selectedRows.length} ${selectedRows.length === 1 ? "record" : "records"}…`);
      const columns = [
        ["Asset number", "asset_number"], ["Asset tag", "asset_tag"], ["Name", "name"],
        ["Hostname", "hostname"], ["IP address", "ip_address"], ["MAC address", "mac_address"],
        ["Device type", "device_type"], ["Vendor", "vendor"], ["Model", "model"],
        ["Serial number", "serial_number"], ["Department", "department"], ["Location", "location"],
        ["Assigned to", "business_owner"],
        ["Lifecycle status", "status"], ["Health", "health"], ["Warranty status", "warranty_status"],
      ] as const;
      const exportRows = selectedRows.map((row) =>
        Object.fromEntries(columns.map(([label, key]) => [label, row[key] ?? ""])),
      );
      const filename = `HIOP-device-inventory-${new Date().toISOString().slice(0, 10)}`;
      if (exportFormat === "csv") {
        const quote = (value: unknown) => `"${String(value ?? "").replace(/"/g, '""')}"`;
        const csv = [
          columns.map(([label]) => quote(label)).join(","),
          ...exportRows.map((row) => columns.map(([label]) => quote(row[label])).join(",")),
        ].join("\r\n");
        saveBlob(new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" }), `${filename}.csv`);
      } else if (exportFormat === "excel") {
        const worksheet = XLSX.utils.json_to_sheet(exportRows);
        worksheet["!cols"] = columns.map(([label]) => ({ wch: Math.max(label.length + 2, 16) }));
        const workbook = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(workbook, worksheet, "Device inventory");
        const bytes = XLSX.write(workbook, { bookType: "xlsx", type: "array" });
        saveBlob(new Blob([bytes], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }), `${filename}.xlsx`);
      } else {
        const wordRows = [
          ["Asset", "Device", "Assignment", "Technical details", "Network", "Health & lifecycle"],
          ...selectedRows.map((row) => [
            `Asset number: ${value(row.asset_number)}\nAsset tag: ${value(row.asset_tag)}`,
            `Name: ${value(row.name)}\nHostname: ${value(row.hostname)}\nType: ${value(row.device_type)}`,
            `Assigned to: ${value(row.business_owner)}\nDepartment: ${value(row.department)}\nLocation: ${value(row.location)}`,
            `Vendor: ${value(row.vendor)}\nModel: ${value(row.model)}\nSerial: ${value(row.serial_number)}`,
            `IP address: ${value(row.ip_address)}\nMAC address: ${value(row.mac_address)}`,
            `Lifecycle: ${value(row.status)}\nHealth: ${value(row.health)}\nWarranty: ${value(row.warranty_status)}`,
          ]),
        ];
        await downloadBrandedWordReport(
          "Managed Asset Inventory",
          filename,
          wordRows,
        );
      }
    } catch (error) {
      setExportError(error instanceof Error ? error.message : "The device export could not be created.");
    } finally {
      setExporting(false);
      setExportProgress("");
    }
  };
  const saveBlob = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const clearFilters = () => {
    setStatus("All"); setType("All"); setDepartment("All"); setLocation("All");
    setHealth("All"); setVendor("All"); setCondition("All"); setWarranty("All");
  };

  return (
    <DashboardLayout>
      <PageTitle 
        eyebrow="CMDB & asset intelligence" 
        title="Managed assets" 
        copy="Organizational asset identity joined to authoritative device, health, and network evidence." 
        action={<div className="page-actions"><label>Export count<select value={exportCount} onChange={(event) => setExportCount(event.target.value as "50" | "100" | "all")}><option value="50">First 50 filtered</option><option value="100">First 100 filtered</option><option value="all">All filtered</option></select></label><label>Format<select value={exportFormat} onChange={(event) => setExportFormat(event.target.value as "word" | "csv" | "excel")}><option value="word">Word report (.docx)</option><option value="csv">CSV</option><option value="excel">Excel workbook</option></select></label><button className="secondary-action" type="button" onClick={() => void exportFile()} disabled={!rows.length || exporting}>{exporting ? exportProgress || "Preparing export…" : `Export ${exportCount === "all" ? "all filtered" : `first ${exportCount}`}`}</button>{admin ? (
          <Link className="primary-action" to="/assets/new">
            <Icon name="devices" aria-hidden="true" />
            Add Asset
          </Link>
        ) : null}</div>}
      />
      {assets.loading || assets.error ? (
        <Feedback 
          loading={assets.loading} 
          error={assets.error} 
          onRetry={assets.reload} 
        />
      ) : (
        <>
          {exportError && <p role="alert" className="form-error">{exportError}</p>}
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
              <Filter label="lifecycle" allLabel="All lifecycle stages" value={status} set={setStatus} rows={unique(all, (x) => x.status)} />
              <Filter label="condition" value={condition} set={setCondition} rows={unique(all, (x) => x.condition)} />
              <Filter label="warranty" allLabel="All warranty statuses" value={warranty} set={setWarranty} rows={unique(all, (x) => x.warranty_status)} />
              <Filter label="type" value={type} set={setType} rows={unique(all, (x) => x.device_type)} />
              <Filter label="department" value={activeDepartment} set={setDepartment} rows={departmentOptions} />
              <Filter label="location" value={location} set={setLocation} rows={locationOptions} />
              <Filter label="health" allLabel="All health states" value={health} set={setHealth} rows={unique(all, (x) => x.health)} />
              <Filter label="vendor" value={vendor} set={setVendor} rows={unique(all, (x) => x.vendor)} />
              {activeFilters > 0 && <button className="filter-reset" type="button" onClick={clearFilters}>Clear filters <span>{activeFilters}</span></button>}
            </div>
            <label className="asset-page-size">
              Show
              <select value={pageSize} onChange={(event) => setPageSize(event.target.value)} aria-label="Number of managed assets to load">
                <option value="50">50 devices</option>
                <option value="100">100 devices</option>
                <option value="all">All devices</option>
              </select>
            </label>
            <p className="toolbar-summary" aria-live="polite">Showing <strong>{rows.length}</strong> of <strong>{all.length}</strong> loaded managed assets{query ? ` matching “${search}”` : ""}{pageSize === "all" ? ". All devices are loaded." : "."}</p>
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
  rows,
  allLabel,
}: {
  label: string;
  value: string;
  set: (value: string) => void;
  rows: string[];
  allLabel?: string;
}) {
  return (
    <select 
      value={value} 
      onChange={(e) => set(e.target.value)} 
      aria-label={`Filter assets by ${label}`}
    >
      <option value="All">{allLabel ?? `All ${label}s`}</option>
      {rows.map((row) => (
        <option key={row} value={row}>{row.replaceAll("_", " ")}</option>
      ))}
    </select>
  );
}
