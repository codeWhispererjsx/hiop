import { useState } from "react";
import { Feedback } from "../components/Feedback";
import { useRequest } from "../hooks/useRequest";
import { endpoints } from "../lib/api";
import { downloadExportFile } from "../lib/brandedWordExport";
import { formatDateTime } from "../lib/dateTime";
import type { MaintenanceRule } from "../lib/types";
import DashboardLayout from "../layouts/DashboardLayout";
import { PageTitle } from "./DashboardPage";
import "../styles/system-maintenance.css";

type Range = "7d" | "30d" | "custom";
const weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export default function SystemMaintenancePage() {
  const [range, setRange] = useState<Range>("7d");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [exportFormat, setExportFormat] = useState<"csv" | "word">("csv");
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");
  const customRangeValid = Boolean(startDate && endDate && startDate <= endDate);

  const health = useRequest(endpoints.systemHealthReport, []);
  const logs = useRequest(
    async () => {
      const current = range === "custom"
        ? customRangeValid
          ? await endpoints.maintenanceLog(range, startDate, endDate)
          : { items: [] }
        : await endpoints.maintenanceLog(range);
      const weekly = range === "7d" ? current : await endpoints.maintenanceLog("7d");
      return { items: current.items, weekItems: weekly.items };
    },
    [range, startDate, endDate, customRangeValid],
  );
  const rules = useRequest(endpoints.maintenanceRules, []);
  const logItems = logs.data?.items ?? [];
  const weekItems = logs.data?.weekItems ?? [];
  const uptimeValues = health.data?.devices
    .map((device) => device.uptime_seconds)
    .filter((value): value is number => value !== null);
  const averageUptime = uptimeValues?.length
    ? uptimeValues.reduce((sum, value) => sum + value, 0) / uptimeValues.length
    : null;

  const downloadMaintenanceReport = async () => {
    setExporting(true);
    setError("");
    try {
      const file = range === "custom"
        ? await endpoints.exportMaintenanceLog(range, startDate, endDate)
        : await endpoints.exportMaintenanceLog(range);
      await downloadExportFile(exportFormat, "System Maintenance Report", file.filename, file.blob);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not export the maintenance report.");
    } finally {
      setExporting(false);
    }
  };

  return (
    <DashboardLayout>
      <PageTitle
        eyebrow="Manage · Reports"
        title="System Maintenance Report"
        copy="Review endpoint health and historical maintenance records. HIOP never restarts, shuts down, updates, or wakes computers remotely."
        action={
          <div className="maintenance-page-actions">
            <button type="button" className="secondary-action" onClick={() => window.print()}>Print</button>
            <label>Format<select value={exportFormat} onChange={(event) => setExportFormat(event.target.value as "csv" | "word")}><option value="csv">CSV</option><option value="word">Word report (.docx)</option></select></label>
            <button type="button" className="secondary-action" onClick={() => void downloadMaintenanceReport()} disabled={exporting || (range === "custom" && !customRangeValid)}>{exporting ? "Preparing export…" : `Export ${exportFormat === "csv" ? "CSV" : "Word report"}`}</button>
          </div>
        }
      />
      {error && <Feedback error={error} />}
      <p className="maintenance-notice" role="status">This report is read-only. End-of-day shutdown and screen lock run on each computer through the HIOP agent; see Local Agents for live status, power events, and admin notices.</p>

      <section className="maintenance-section" aria-labelledby="maintenance-summary-title">
        <header className="maintenance-section-heading">
          <div><p className="page-kicker">Endpoint health</p><h2 id="maintenance-summary-title">System health overview</h2></div>
          <button type="button" className="secondary-action" onClick={() => void health.reload()}>Refresh</button>
        </header>
        {health.loading || health.error || !health.data ? (
          <Feedback loading={health.loading} error={health.error} onRetry={health.reload} />
        ) : (
          <>
            <div className="maintenance-summary-grid">
              <SummaryCard label="Total devices" value={health.data.summary.total_devices} detail={`${health.data.summary.online} online`} />
              <SummaryCard label="Average uptime" value={averageUptime === null ? "—" : formatUptime(averageUptime)} detail="Across endpoints reporting uptime" />
              <SummaryCard label="Updates needed" value={health.data.summary.updates_needed} detail="Last Windows update is older than 7 days" tone={health.data.summary.updates_needed ? "warning" : "good"} />
              <SummaryCard label="Legacy restart / shutdown history" value={weekItems.filter((item) => ["RESTART", "SHUTDOWN"].includes(item.action)).length} detail={`${weekItems.filter((item) => item.action === "TRIGGER_WINDOWS_UPDATE").length} historical update scans`} />
              <SummaryCard label="Systems needing restart" value={health.data.summary.restarts_needed} detail="Uptime exceeds 48 hours" tone={health.data.summary.restarts_needed > 5 ? "danger" : health.data.summary.restarts_needed ? "warning" : "good"} />
              <SummaryCard label="Legacy cool-off records" value={health.data.summary.cooled_off_last_night} detail="Historical shutdowns from 21:00–06:00; controls are disabled" tone="info" />
              <article className={`maintenance-summary-card tone-${hygieneTone(health.data.summary.hygiene_score)}`}>
                <span>System hygiene score</span><strong>{health.data.summary.hygiene_score}%</strong>
                <div className={`hygiene-track tone-${hygieneTone(health.data.summary.hygiene_score)}`} role="progressbar" aria-valuenow={health.data.summary.hygiene_score} aria-valuemin={0} aria-valuemax={100}><i style={{ width: `${health.data.summary.hygiene_score}%` }} /></div>
                <small>Online, uptime under 48 hours, and updated within 7 days</small>
              </article>
            </div>

            <section className="maintenance-table-panel">
              <header><h2>Device health</h2><p>Health status is based on the latest agent heartbeat and update data.</p></header>
              <div className="maintenance-table-scroll">
                <table>
                  <thead><tr><th>Hostname</th><th>Assigned to</th><th>Department</th><th>Location / floor</th><th>Last restart</th><th>Uptime</th><th>Last update</th><th>Last cool off</th><th>Status</th></tr></thead>
                  <tbody>
                    {health.data.devices.map((device) => (
                      <tr key={device.device_id}>
                        <td>{device.hostname}</td><td>{device.assigned_to || "—"}</td><td>{device.department || "—"}</td>
                        <td>{[device.location, device.floor].filter(Boolean).join(" · ") || "—"}</td>
                        <td>{device.last_restart ? formatDateTime(device.last_restart) : "—"}</td>
                        <td>{device.uptime_seconds === null ? "—" : formatUptime(device.uptime_seconds)}</td>
                        <td>{device.last_update ? formatDateTime(device.last_update) : "No data"}</td>
                        <td>{device.last_cool_off ? formatDateTime(device.last_cool_off) : "—"}</td>
                        <td><span className={`maintenance-status ${statusClass(device.status)}`}>{device.status}</span></td>
                      </tr>
                    ))}
                    {!health.data.devices.length && <tr><td colSpan={9} className="maintenance-empty">No managed devices are available in this property scope.</td></tr>}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </section>

      <section className="maintenance-section" aria-labelledby="maintenance-log-title">
        <header className="maintenance-section-heading">
          <div><p className="page-kicker">Audit trail</p><h2 id="maintenance-log-title">Automation and maintenance log</h2></div>
          <label className="maintenance-range">Date range
            <select value={range} onChange={(event) => setRange(event.target.value as Range)}>
              <option value="7d">Last 7 days</option><option value="30d">Last 30 days</option><option value="custom">Custom range</option>
            </select>
          </label>
        </header>
        {range === "custom" && <div className="maintenance-custom-range">
          <label>From <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></label>
          <label>To <input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label>
          {!customRangeValid && <small>Choose a start and end date; the end date must not be earlier than the start date.</small>}
        </div>}
        {logs.loading || logs.error ? <Feedback loading={logs.loading} error={logs.error} onRetry={logs.reload} /> : (
          <div className="maintenance-table-panel">
            <div className="maintenance-table-scroll">
              <table>
                <thead><tr><th>Date / time</th><th>Hostname</th><th>Action</th><th>Triggered by</th><th>Result</th><th>Notes</th></tr></thead>
                <tbody>
                  {logItems.map((item, index) => <tr key={`${item.date_time}-${item.hostname}-${index}`}>
                    <td>{formatDateTime(item.date_time)}</td><td>{item.hostname}</td><td>{item.action.replaceAll("_", " ")}</td><td>{item.triggered_by}</td><td><span className={`maintenance-status ${statusClass(item.result)}`}>{item.result}</span></td><td>{item.notes || "—"}</td>
                  </tr>)}
                  {!logItems.length && <tr><td colSpan={6} className="maintenance-empty">{range === "custom" && !customRangeValid ? "Select a valid custom date range to view events." : "No maintenance actions were recorded in this period."}</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

      <section className="maintenance-section" aria-labelledby="maintenance-rules-title">
        <header className="maintenance-section-heading">
          <div><p className="page-kicker">Legacy rules</p><h2 id="maintenance-rules-title">Scheduled endpoint controls</h2><p>Rules from earlier versions are kept for audit history. They no longer run and cannot be edited.</p></div>
        </header>
        {rules.loading || rules.error ? <Feedback loading={rules.loading} error={rules.error} onRetry={rules.reload} /> : (
          <div className="maintenance-rule-list">
            {rules.data?.items.map((rule) => <article className="maintenance-rule-card" key={rule.id}>
              <div className="maintenance-rule-main">
                <div className="maintenance-rule-name"><h3>{rule.name}</h3><span className="maintenance-status status-neutral">Disabled</span></div>
                <p>{rule.description || "No description provided."}</p>
                <small>{describeRule(rule)} · {rule.schedule.frequency === "weekly" ? `${weekdays[rule.schedule.weekday ?? 0]} ` : ""}{rule.schedule.time} {rule.schedule.timezone}</small>
                <small>Action: {rule.action.replaceAll("_", " ")} · Affects {rule.affected_count} device{rule.affected_count === 1 ? "" : "s"} · Legacy enabled setting: {rule.enabled ? "yes (ignored)" : "no"}</small>
              </div>
            </article>)}
            {!rules.data?.items.length && <p className="maintenance-empty">No legacy endpoint-control rules are configured.</p>}
          </div>
        )}
      </section>

    </DashboardLayout>
  );
}

function SummaryCard({ label, value, detail, tone = "neutral" }: { label: string; value: string | number; detail: string; tone?: string }) {
  return <article className={`maintenance-summary-card tone-${tone}`}><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>;
}

function formatUptime(seconds: number) {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  return days ? `${days}d ${hours}h` : `${hours}h`;
}

function statusClass(value: string) {
  const status = value.toLowerCase();
  if (status.includes("healthy") || status.includes("complete") || status === "online") return "status-good";
  if (status.includes("need") || status.includes("update") || status.includes("stale")) return "status-warning";
  if (status.includes("offline") || status.includes("failed") || status.includes("error")) return "status-danger";
  return "status-neutral";
}

function hygieneTone(score: number) {
  return score > 80 ? "good" : score >= 50 ? "warning" : "danger";
}

function describeRule(rule: MaintenanceRule) {
  const conditions = Object.entries(rule.criteria).map(([key, value]) => `${key.replaceAll("_", " ")}: ${value}`);
  return conditions.join(" · ");
}
