import { formatDateTime } from "../lib/dateTime";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Feedback } from "../components/Feedback";
import { StatusBadge } from "../components/StatusBadge";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import { downloadExportFile } from "../lib/brandedWordExport";
import { PageTitle } from "./DashboardPage";

const reports = [
  "executive",
  "operations",
  "network",
  "assets",
  "lifecycle",
  "incidents",
  "problems",
  "changes",
  "procurement",
  "vendors",
  "knowledge",
  "services",
  "departments",
  "locations",
];

const periods = [
  { id: "today", label: "Today" },
  { id: "7d", label: "Last 7 days" },
  { id: "30d", label: "Last 30 days" },
  { id: "90d", label: "Last 90 days" },
  { id: "month", label: "This month" },
  { id: "quarter", label: "This quarter" },
  { id: "year", label: "This year" },
  { id: "custom", label: "Custom range" },
];

const title = (value: string) =>
  value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (x) => x.toUpperCase());

export default function ReportingPage() {
  const [report, setReport] = useState("executive");
  const [period, setPeriod] = useState("30d");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [serviceId, setServiceId] = useState("");
  const [vendorId, setVendorId] = useState("");
  const [deviceType, setDeviceType] = useState("");
  const [status, setStatus] = useState("");
  const [exportFormat, setExportFormat] = useState<"csv" | "word">("csv");
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  const hierarchy = useRequest(endpoints.hierarchy, []);
  const reportFilterCount = [period !== "30d" ? period : "", start, end, departmentId, locationId, serviceId, vendorId, deviceType, status].filter(Boolean).length;
  const clearReportFilters = () => { setPeriod("30d"); setStart(""); setEnd(""); setDepartmentId(""); setLocationId(""); setServiceId(""); setVendorId(""); setDeviceType(""); setStatus(""); };

  const filters = {
    period,
    start:
      period === "custom" && start
        ? new Date(start).toISOString()
        : undefined,
    end:
      period === "custom" && end
        ? new Date(`${end}T23:59:59`).toISOString()
        : undefined,
    department_id: departmentId || undefined,
    location_id: locationId || undefined,
    service_id: serviceId || undefined,
    vendor_id: vendorId || undefined,
    device_type: deviceType || undefined,
    status: status || undefined,
  };

  const data = useRequest(
    () => endpoints.organizationReport(report, filters),
    [
      report,
      period,
      start,
      end,
      departmentId,
      locationId,
      serviceId,
      vendorId,
      deviceType,
      status,
    ]
  );

  const exportReport = async () => {
    setExporting(true);
    setExportError("");
    try {
      const file = await endpoints.exportOrganizationReport(report, filters);
      await downloadExportFile(exportFormat, `${title(report)} Report`, file.filename, file.blob);
    } catch (error) {
      setExportError(error instanceof Error ? error.message : "The report could not be exported.");
    } finally {
      setExporting(false);
    }
  };

  return (
    <DashboardLayout>
      <PageTitle
        eyebrow="Management intelligence"
        title="Organization reporting"
        copy="Prebuilt, explainable reports calculated from live HIOP organization data."
      />
      <section className="report-export-panel" aria-label="Export report">
        <div>
          <span>Export current view</span>
          <strong>{title(report)} report</strong>
          <p>Downloads include the active reporting period and filters.</p>
        </div>
        <label htmlFor="report-export-format">File format
          <select id="report-export-format" value={exportFormat} onChange={(event) => setExportFormat(event.target.value as "csv" | "word")}>
            <option value="csv">CSV spreadsheet</option>
            <option value="word">Branded Word report (.docx)</option>
          </select>
        </label>
        <button className="primary-action" onClick={() => void exportReport()} disabled={exporting}>
          {exporting ? "Preparing export…" : `Export ${exportFormat === "csv" ? "CSV" : "Word report"}`}
        </button>
      </section>
      {exportError && <p className="form-error" role="alert">{exportError}</p>}
      <nav className="page-actions report-tabs" aria-label="Specialized reports">
        <Link className="secondary-action" to="/reports/system-maintenance">System Maintenance Report</Link>
      </nav>
      <nav className="page-actions report-tabs" aria-label="Common report types">
        {reports.slice(0, 4).map((x) => (
          <button
            key={x}
            className={x === report ? "primary-action" : "secondary-action"}
            onClick={() => setReport(x)}
            aria-current={x === report ? "page" : undefined}
          >
            {title(x)}
          </button>
        ))}
        <details className="advanced-report-menu">
          <summary className="secondary-action">More reports</summary>
          <div className="page-actions">
            {reports.slice(4).map((x) => (
              <button
                key={x}
                className={x === report ? "primary-action" : "secondary-action"}
                onClick={() => setReport(x)}
                aria-current={x === report ? "page" : undefined}
              >
                {title(x)}
              </button>
            ))}
          </div>
        </details>
      </nav>
      <section className="operations-guide report-guide" aria-label="Reporting guide"><div><span>Choose</span><strong>{title(report)} report</strong><p>Select a common report or open More reports for additional options.</p></div><div><span>Filter</span><strong>Choose a date range</strong><p>Start with a preset period or select a custom date range.</p></div><div><span>Act</span><strong>Drill down or export</strong><p>Open underlying records from linked metrics or export the current view as CSV or a branded Word report.</p></div></section>
      <section className="toolbar-panel" aria-label="Report filters">
        <div className="filter-row">
          <label htmlFor="report-period">
            Reporting period
            <select
              id="report-period"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
            >
              {periods.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.label}
                </option>
              ))}
            </select>
          </label>
          {period === "custom" && (
            <>
              <label htmlFor="report-start">
                Start
                <input
                  id="report-start"
                  type="date"
                  value={start}
                  onChange={(e) => setStart(e.target.value)}
                />
              </label>
              <label htmlFor="report-end">
                End
                <input
                  id="report-end"
                  type="date"
                  value={end}
                  onChange={(e) => setEnd(e.target.value)}
                />
              </label>
            </>
          )}
        </div>
        <details className="advanced-report-filters">
          <summary>Advanced filters{reportFilterCount > (period !== "30d" ? 1 : 0) + (start ? 1 : 0) + (end ? 1 : 0) ? ` (${reportFilterCount - (period !== "30d" ? 1 : 0) - (start ? 1 : 0) - (end ? 1 : 0)} active)` : ""}</summary>
          <div className="filter-row">
          <label htmlFor="report-device-type">
            Device type
            <input
              id="report-device-type"
              value={deviceType}
              onChange={(e) => setDeviceType(e.target.value)}
              placeholder="e.g. switch"
            />
          </label>
          <label htmlFor="report-status">
            Status
            <input
              id="report-status"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              placeholder="e.g. active"
            />
          </label>
          <label htmlFor="report-department">
            Department
            <select id="report-department" value={departmentId} onChange={(event) => setDepartmentId(event.target.value)}>
              <option value="">All departments</option>
              {(hierarchy.data?.departments ?? []).filter((item) => item.is_active || item.id === departmentId).map((item) => (
                <option key={item.id} value={item.id}>{item.name}{item.is_active ? "" : " (Inactive)"}</option>
              ))}
            </select>
          </label>
          <label htmlFor="report-location">
            Room / location
            <select id="report-location" value={locationId} onChange={(event) => setLocationId(event.target.value)}>
              <option value="">All locations</option>
              {(hierarchy.data?.rooms ?? []).filter((item) => item.is_active || item.id === locationId).map((item) => (
                <option key={item.id} value={item.id}>{item.name}{item.is_active ? "" : " (Inactive)"}</option>
              ))}
            </select>
          </label>
          <label htmlFor="report-service">
            Service ID
            <input
              id="report-service"
              value={serviceId}
              onChange={(e) => setServiceId(e.target.value)}
              placeholder="Optional"
            />
          </label>
          <label htmlFor="report-vendor">
            Vendor ID
            <input
              id="report-vendor"
              value={vendorId}
              onChange={(e) => setVendorId(e.target.value)}
              placeholder="Optional"
            />
          </label>
          {reportFilterCount > 0 && <button className="filter-reset" type="button" onClick={clearReportFilters}>Reset filters <span>{reportFilterCount}</span></button>}
          </div>
        </details>
        <p className="toolbar-summary">Report scope: <strong>{title(report)}</strong> · {periods.find((item) => item.id === period)?.label}</p>
      </section>
      {data.loading || data.error || !data.data ? (
        <Feedback loading={data.loading} error={data.error} />
      ) : (
        <>
          <section className="report-metric-grid" aria-label="Report metrics">
            {data.data.metrics.map((item) =>
              item.drilldown ? (
                <Link
                  key={item.label}
                  className="panel report-metric"
                  to={item.drilldown}
                  aria-label={`View ${item.label} details`}
                >
                  <small>{item.label}</small>
                  <strong>{item.value}</strong>
                  <span>Open underlying records →</span>
                </Link>
              ) : (
                <article key={item.label} className="panel report-metric">
                  <small>{item.label}</small>
                  <strong>{item.value}</strong>
                  <StatusBadge status={item.quality} />
                </article>
              )
            )}
          </section>
          <section className="report-grid" aria-label="Report breakdowns">
            {Object.entries(data.data.breakdowns).map(([name, rows]) => (
              <article className="panel" key={name}>
                <h2>{title(name)}</h2>
                {!rows.length ? (
                  <Feedback empty="Insufficient data" />
                ) : (
                  <BreakdownChart name={name} rows={rows} />
                )}
              </article>
            ))}
          </section>
          <section className="report-grid" aria-label="Report trends">
            {Object.entries(data.data.trends).map(([name, trend]) => (
              <article className="panel" key={name}>
                <h2>{title(name)}</h2>
                {trend.status !== "available" || !trend.points.length ? (
                  <Feedback empty="Insufficient data" />
                ) : (
                  <div
                    className="trend-chart"
                    role="img"
                    aria-label={`${title(name)} historical trend`}
                  >
                    {trend.points.map((point) => (
                      <div key={point.date}>
                        <span
                          style={{
                            height: `${Math.max(8, Math.min(100, point.value))}%`,
                          }}
                          title={`${point.date}: ${point.value}`}
                        />
                        <small>{point.date.slice(5)}</small>
                      </div>
                    ))}
                  </div>
                )}
              </article>
            ))}
          </section>
          <footer className="settings-note">
            Source: {data.data.source}. Generated{" "}
            {formatDateTime(data.data.generated_at)}. Missing
            observations remain "Insufficient data".
          </footer>
        </>
      )}
    </DashboardLayout>
  );
}

function BreakdownChart({ name, rows }: { name: string; rows: Array<Record<string, unknown>> }) {
  const chartRows = rows.map((row) => ({
    label: String(row.label ?? "Unknown"),
    value: typeof row.value === "number" && Number.isFinite(row.value) ? row.value : null,
  }));
  const maximum = Math.max(0, ...chartRows.map((row) => row.value ?? 0));
  if (maximum === 0 || chartRows.some((row) => row.value === null)) {
    return <div className="report-breakdown">{rows.map((row, index) => (
      <div key={`${String(row.label)}-${index}`}>
        <strong>{String(row.label ?? "Unknown")}</strong>
        <span>{Object.entries(row).filter(([key]) => key !== "label" && key !== "id").map(([key, value]) => `${title(key)}: ${value}`).join(" · ")}</span>
      </div>
    ))}</div>;
  }
  return <div className="report-breakdown-chart" role="group" aria-label={`${title(name)} breakdown chart`}>
    {chartRows.map((row, index) => <div className="report-breakdown-bar" key={`${row.label}-${index}`} role="group" aria-label={`${row.label}: ${row.value}`}>
      <div><strong>{row.label}</strong><span>{row.value}</span></div>
      <span className="report-breakdown-track"><i style={{ width: `${Math.max(0, (row.value ?? 0) / maximum * 100)}%` }} /></span>
    </div>)}
  </div>;
}