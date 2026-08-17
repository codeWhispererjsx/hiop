import { useState } from "react";
import { Link } from "react-router-dom";
import { Feedback } from "../components/Feedback";
import { StatusBadge } from "../components/StatusBadge";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
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

  const exportCsv = async () => {
    const file = await endpoints.exportOrganizationReport(report, filters);
    const url = URL.createObjectURL(file.blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = file.filename;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <DashboardLayout>
      <PageTitle
        eyebrow="Management intelligence"
        title="Organization reporting"
        copy="Prebuilt, explainable reports calculated from live HIOP organization data."
        action={
          <button
            className="secondary-action"
            onClick={() => void exportCsv()}
            aria-label="Export report as CSV"
          >
            Export CSV
          </button>
        }
      />
      <nav className="page-actions report-tabs" aria-label="Report types">
        {reports.map((x) => (
          <button
            key={x}
            className={x === report ? "primary-action" : "secondary-action"}
            onClick={() => setReport(x)}
            aria-current={x === report ? "page" : undefined}
          >
            {title(x)}
          </button>
        ))}
      </nav>
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
            Department ID
            <input
              id="report-department"
              value={departmentId}
              onChange={(e) => setDepartmentId(e.target.value)}
              placeholder="Optional"
            />
          </label>
          <label htmlFor="report-location">
            Location ID
            <input
              id="report-location"
              value={locationId}
              onChange={(e) => setLocationId(e.target.value)}
              placeholder="Optional"
            />
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
        </div>
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
                  <div className="report-breakdown">
                    {rows.map((row, index) => (
                      <div key={`${String(row.label)}-${index}`}>
                        <strong>{String(row.label ?? "Unknown")}</strong>
                        <span>
                          {Object.entries(row)
                            .filter(([key]) => key !== "label" && key !== "id")
                            .map(([key, value]) => `${title(key)}: ${value}`)
                            .join(" · ")}
                        </span>
                      </div>
                    ))}
                  </div>
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
            {new Date(data.data.generated_at).toLocaleString()}. Missing
            observations remain "Insufficient data".
          </footer>
        </>
      )}
    </DashboardLayout>
  );
}