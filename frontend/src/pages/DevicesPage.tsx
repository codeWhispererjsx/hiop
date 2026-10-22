import { useCallback, useDeferredValue, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import * as XLSX from "xlsx";
import { Feedback } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { StatusBadge } from "../components/StatusBadge";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints, getPaginatedItems } from "../lib/api";
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
        (department === "All" || row.department === department) &&
        (location === "All" || row.location === location) &&
        (health === "All" || row.health === health) &&
        (vendor === "All" || row.vendor === vendor) &&
        (condition === "All" || row.condition === condition) &&
        (warranty === "All" || row.warranty_status === warranty)
      );
    }), [query, status, type, department, location, health, vendor, condition, warranty]);
  const rows = useMemo(
    () => filterAssets(all),
    [all, filterAssets]
  );
  const admin = me.data?.role === "admin";
  const activeFilters = [status, type, department, location, health, vendor, condition, warranty].filter((item) => item !== "All").length;
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
    const escape = (text: unknown) => String(text ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    const rowsHtml = selectedRows.map((row) => `<tr>
      <td><strong>${escape(row.name)}</strong><br><span>${escape(row.asset_number || "No asset number")}</span></td>
      <td>${escape(row.hostname || "No hostname")}</td>
      <td>${escape(row.ip_address || "Not available")}</td>
      <td>${escape(row.device_type || "Unknown")}</td>
      <td>${escape(row.department || "Unassigned")}<br><span>${escape(row.location || "No location")}</span></td>
      <td>${escape(row.status || "Unknown")}<br><span>${escape(row.health || "Unknown")}</span></td>
      <td>${escape(row.mac_address || "Not recorded")}<br><span>${escape(row.serial_number || "Serial not verified")}</span></td>
    </tr>`).join("");
    const exportedAt = escape(new Date().toLocaleString());
    const documentHtml = `<!doctype html>
      <html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word">
      <head><meta charset="utf-8"><title>HIOP device inventory</title>
      <style>
        @page Section1 { size: 11in 8.5in; mso-page-orientation: landscape; margin: .42in .35in .48in .35in; }
        div.Section1 { page: Section1; }
        body { margin: 0; color: darkslategray; font-family: Calibri, Arial, sans-serif; font-size: 9pt; }
        h1 { margin: 0 0 4pt; color: navy; font-size: 19pt; }
        .meta { margin: 0 0 15pt; color: slategray; font-size: 9pt; }
        table { width: 100%; border-collapse: collapse; table-layout: fixed; mso-table-lspace: 0pt; mso-table-rspace: 0pt; }
        thead { display: table-header-group; }
        tr { page-break-inside: avoid; }
        th { padding: 7pt 6pt; background: navy; color: white; border: 1px solid navy; font-size: 8pt; font-weight: 700; text-align: left; text-transform: uppercase; }
        td { padding: 7pt 6pt; border: 1px solid lightgray; line-height: 1.25; vertical-align: top; overflow-wrap: anywhere; word-wrap: break-word; }
        td strong { color: darkslategray; } td span { color: slategray; font-size: 8pt; }
        th:nth-child(1) { width: 17%; } th:nth-child(2) { width: 15%; } th:nth-child(3) { width: 11%; }
        th:nth-child(4) { width: 12%; } th:nth-child(5) { width: 16%; } th:nth-child(6) { width: 13%; } th:nth-child(7) { width: 16%; }
      </style></head><body><div class="Section1">
      <h1>HIOP Device Inventory</h1>
      <p class="meta">Exported ${exportedAt} · ${selectedRows.length} managed asset${selectedRows.length === 1 ? "" : "s"} · Search and active inventory filters applied</p>
      <table><thead><tr><th>Asset</th><th>Hostname</th><th>IP address</th><th>Type</th><th>Department / location</th><th>Lifecycle / health</th><th>MAC / serial</th></tr></thead><tbody>${rowsHtml}</tbody></table>
      </div></body></html>`;
    const blob = new Blob(["\ufeff", documentHtml], { type: "application/msword;charset=utf-8" });
        saveBlob(blob, `${filename}.doc`);
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
        action={<div className="page-actions"><label>Export count<select value={exportCount} onChange={(event) => setExportCount(event.target.value as "50" | "100" | "all")}><option value="50">First 50 filtered</option><option value="100">First 100 filtered</option><option value="all">All filtered</option></select></label><label>Format<select value={exportFormat} onChange={(event) => setExportFormat(event.target.value as "word" | "csv" | "excel")}><option value="word">Word report</option><option value="csv">CSV</option><option value="excel">Excel workbook</option></select></label><button className="secondary-action" type="button" onClick={() => void exportFile()} disabled={!rows.length || exporting}>{exporting ? exportProgress || "Preparing export…" : `Export ${exportCount === "all" ? "all filtered" : `first ${exportCount}`}`}</button>{admin ? (
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
              <Filter label="lifecycle" value={status} set={setStatus} rows={unique(all, (x) => x.status)} />
              <Filter label="condition" value={condition} set={setCondition} rows={unique(all, (x) => x.condition)} />
              <Filter label="warranty" value={warranty} set={setWarranty} rows={unique(all, (x) => x.warranty_status)} />
              <Filter label="type" value={type} set={setType} rows={unique(all, (x) => x.device_type)} />
              <Filter label="department" value={department} set={setDepartment} rows={unique(all, (x) => x.department)} />
              <Filter label="location" value={location} set={setLocation} rows={unique(all, (x) => x.location)} />
              <Filter label="health" value={health} set={setHealth} rows={unique(all, (x) => x.health)} />
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
