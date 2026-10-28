import { useState, type FormEvent } from "react";
import { Feedback } from "../components/Feedback";
import Modal from "../components/Modal";
import { useRequest } from "../hooks/useRequest";
import { endpoints } from "../lib/api";
import { downloadExportFile } from "../lib/brandedWordExport";
import { formatDateTime } from "../lib/dateTime";
import type { MaintenanceRule } from "../lib/types";
import DashboardLayout from "../layouts/DashboardLayout";
import { PageTitle } from "./DashboardPage";
import "../styles/system-maintenance.css";

type Range = "7d" | "30d" | "custom";
type RuleInput = Omit<MaintenanceRule, "id" | "last_run_at" | "affected_count" | "created_at" | "updated_at">;
type RuleDraft = {
  id?: string;
  name: string;
  description: string;
  property_id: string;
  action: RuleInput["action"];
  enabled: boolean;
  uptime_hours: string;
  update_age_days: string;
  department: string;
  location: string;
  hostname_contains: string;
  frequency: "daily" | "weekly";
  time: string;
  weekday: number;
  timezone: string;
};

const emptyDraft = (): RuleDraft => ({
  name: "",
  description: "",
  property_id: "",
  action: "RESTART",
  enabled: false,
  uptime_hours: "",
  update_age_days: "",
  department: "",
  location: "",
  hostname_contains: "",
  frequency: "daily",
  time: "21:00",
  weekday: 0,
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
});

const weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export default function SystemMaintenancePage() {
  const [range, setRange] = useState<Range>("7d");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [exportFormat, setExportFormat] = useState<"csv" | "word">("csv");
  const [exporting, setExporting] = useState(false);
  const [draft, setDraft] = useState<RuleDraft>();
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
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
  const properties = useRequest(endpoints.managedProperties, []);
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

  const draftFromRule = (rule: MaintenanceRule): RuleDraft => ({
    id: rule.id,
    name: rule.name,
    description: rule.description ?? "",
    property_id: rule.property_id ?? "",
    action: rule.action,
    enabled: rule.enabled,
    uptime_hours: rule.criteria.uptime_hours?.toString() ?? "",
    update_age_days: rule.criteria.update_age_days?.toString() ?? "",
    department: rule.criteria.department?.toString() ?? "",
    location: rule.criteria.location?.toString() ?? "",
    hostname_contains: rule.criteria.hostname_contains?.toString() ?? "",
    frequency: rule.schedule.frequency,
    time: rule.schedule.time,
    weekday: rule.schedule.weekday ?? 0,
    timezone: rule.schedule.timezone,
  });

  const rulePayload = (value: RuleDraft): RuleInput => {
    const criteria: RuleInput["criteria"] = {};
    if (value.uptime_hours) criteria.uptime_hours = Number(value.uptime_hours);
    if (value.update_age_days) criteria.update_age_days = Number(value.update_age_days);
    if (value.department.trim()) criteria.department = value.department.trim();
    if (value.location.trim()) criteria.location = value.location.trim();
    if (value.hostname_contains.trim()) criteria.hostname_contains = value.hostname_contains.trim();
    return {
      name: value.name.trim(),
      description: value.description.trim() || null,
      property_id: value.property_id || null,
      criteria,
      schedule: {
        frequency: value.frequency,
        time: value.time,
        timezone: value.timezone.trim(),
        ...(value.frequency === "weekly" ? { weekday: value.weekday } : {}),
      },
      action: value.action,
      enabled: value.enabled,
    };
  };

  const saveRule = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!draft) return;
    setSaving(true);
    setError("");
    try {
      const body = rulePayload(draft);
      if (draft.id) await endpoints.updateMaintenanceRule(draft.id, body);
      else await endpoints.createMaintenanceRule(body);
      setDraft(undefined);
      setNotice(draft.id ? "Maintenance rule updated." : "Maintenance rule created.");
      await Promise.all([rules.reload(), health.reload()]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save this maintenance rule.");
    } finally {
      setSaving(false);
    }
  };

  const setRuleEnabled = async (rule: MaintenanceRule, enabled: boolean) => {
    setError("");
    try {
      await endpoints.updateMaintenanceRule(rule.id, { ...rulePayload(draftFromRule(rule)), enabled });
      setNotice(enabled ? `Rule “${rule.name}” enabled.` : `Rule “${rule.name}” disabled.`);
      await rules.reload();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not update this rule.");
    }
  };

  const deleteRule = async (rule: MaintenanceRule) => {
    if (!window.confirm(`Delete the maintenance rule “${rule.name}”? This cannot be undone.`)) return;
    setError("");
    try {
      await endpoints.deleteMaintenanceRule(rule.id);
      setNotice(`Rule “${rule.name}” deleted.`);
      await rules.reload();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not delete this rule.");
    }
  };

  return (
    <DashboardLayout>
      <PageTitle
        eyebrow="Manage · Reports"
        title="System Maintenance Report"
        copy="Review managed endpoint health and maintenance history, then define the rules that fit your property’s operating schedule."
        action={
          <div className="maintenance-page-actions">
            <button type="button" className="secondary-action" onClick={() => window.print()}>Print</button>
            <label>Format<select value={exportFormat} onChange={(event) => setExportFormat(event.target.value as "csv" | "word")}><option value="csv">CSV</option><option value="word">Word report (.docx)</option></select></label>
            <button type="button" className="secondary-action" onClick={() => void downloadMaintenanceReport()} disabled={exporting || (range === "custom" && !customRangeValid)}>{exporting ? "Preparing export…" : `Export ${exportFormat === "csv" ? "CSV" : "Word report"}`}</button>
          </div>
        }
      />
      {notice && <p className="maintenance-notice" role="status">{notice}</p>}
      {error && !draft && <Feedback error={error} />}

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
              <SummaryCard label="Restart / cool-off actions this week" value={weekItems.filter((item) => ["RESTART", "SHUTDOWN"].includes(item.action)).length} detail={`${weekItems.filter((item) => item.action === "TRIGGER_WINDOWS_UPDATE").length} update scans this week`} />
              <SummaryCard label="Systems needing restart" value={health.data.summary.restarts_needed} detail="Uptime exceeds 48 hours" tone={health.data.summary.restarts_needed > 5 ? "danger" : health.data.summary.restarts_needed ? "warning" : "good"} />
              <SummaryCard label="Cooled off last night" value={health.data.summary.cooled_off_last_night} detail="Shutdowns between 21:00 and 06:00 local time" tone="info" />
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
          <div><p className="page-kicker">Custom schedules</p><h2 id="maintenance-rules-title">Automation rules</h2><p>Rules are disabled by default. Review the affected-device count before enabling a scheduled action.</p></div>
          <button type="button" className="primary-action" onClick={() => setDraft(emptyDraft())}>Create rule</button>
        </header>
        {rules.loading || rules.error ? <Feedback loading={rules.loading} error={rules.error} onRetry={rules.reload} /> : (
          <div className="maintenance-rule-list">
            {rules.data?.items.map((rule) => <article className="maintenance-rule-card" key={rule.id}>
              <div className="maintenance-rule-main">
                <div className="maintenance-rule-name"><h3>{rule.name}</h3><span className={`maintenance-status ${rule.enabled ? "status-good" : "status-neutral"}`}>{rule.enabled ? "Enabled" : "Disabled"}</span></div>
                <p>{rule.description || "No description provided."}</p>
                <small>{describeRule(rule)} · {rule.schedule.frequency === "weekly" ? `${weekdays[rule.schedule.weekday ?? 0]} ` : ""}{rule.schedule.time} {rule.schedule.timezone}</small>
                <small>Action: {rule.action.replaceAll("_", " ")} · Affects {rule.affected_count} device{rule.affected_count === 1 ? "" : "s"} · Last run: {rule.last_run_at ? formatDateTime(rule.last_run_at) : "Never"}</small>
              </div>
              <div className="maintenance-rule-actions">
                <button type="button" className="secondary-action" onClick={() => setDraft(draftFromRule(rule))}>Edit</button>
                <button type="button" className="secondary-action" onClick={() => void setRuleEnabled(rule, !rule.enabled)}>{rule.enabled ? "Disable" : "Enable"}</button>
                <button type="button" className="danger-action" onClick={() => void deleteRule(rule)}>Delete</button>
              </div>
            </article>)}
            {!rules.data?.items.length && <p className="maintenance-empty">No rules yet. Add a rule that reflects how your hotel wants to maintain its endpoints.</p>}
          </div>
        )}
      </section>

      {draft && <Modal title={draft.id ? "Edit maintenance rule" : "Create maintenance rule"} onClose={() => { if (!saving) setDraft(undefined); }}>
        <form className="maintenance-rule-form" onSubmit={(event) => void saveRule(event)}>
          {error && <p className="maintenance-form-error" role="alert">{error}</p>}
          <label>Rule name<input required minLength={2} maxLength={160} value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
          <label>Description<textarea maxLength={2000} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label>
          <label>Property scope<select value={draft.property_id} onChange={(event) => setDraft({ ...draft, property_id: event.target.value })}><option value="">All permitted properties</option>{properties.data?.filter((property) => property.status === "active").map((property) => <option key={property.id} value={property.id}>{property.name}</option>)}</select></label>
          {properties.error && <Feedback error={properties.error} onRetry={properties.reload} />}
          <fieldset><legend>Run when matching conditions are met</legend>
            <label>Uptime exceeds (hours)<input type="number" min={1} max={8760} value={draft.uptime_hours} onChange={(event) => setDraft({ ...draft, uptime_hours: event.target.value })} /></label>
            <label>Update is older than (days)<input type="number" min={1} max={8760} value={draft.update_age_days} onChange={(event) => setDraft({ ...draft, update_age_days: event.target.value })} /></label>
            <label>Department<input maxLength={120} value={draft.department} onChange={(event) => setDraft({ ...draft, department: event.target.value })} /></label>
            <label>Location<input maxLength={120} value={draft.location} onChange={(event) => setDraft({ ...draft, location: event.target.value })} /></label>
            <label>Hostname contains<input maxLength={120} value={draft.hostname_contains} onChange={(event) => setDraft({ ...draft, hostname_contains: event.target.value })} /></label>
          </fieldset>
          <div className="maintenance-rule-form-grid">
            <label>Action<select value={draft.action} onChange={(event) => setDraft({ ...draft, action: event.target.value as RuleDraft["action"] })}><option value="RESTART">Restart</option><option value="SHUTDOWN">Shutdown / cool off</option><option value="TRIGGER_WINDOWS_UPDATE">Trigger Windows Update scan</option><option value="WAKE_ON_LAN">Wake-on-LAN</option></select></label>
            <label>Schedule<select value={draft.frequency} onChange={(event) => setDraft({ ...draft, frequency: event.target.value as RuleDraft["frequency"] })}><option value="daily">Daily</option><option value="weekly">Weekly</option></select></label>
            <label>Time<input type="time" required value={draft.time} onChange={(event) => setDraft({ ...draft, time: event.target.value })} /></label>
            {draft.frequency === "weekly" && <label>Day of week<select value={draft.weekday} onChange={(event) => setDraft({ ...draft, weekday: Number(event.target.value) })}>{weekdays.map((day, index) => <option value={index} key={day}>{day}</option>)}</select></label>}
            <label>Timezone<input required maxLength={100} value={draft.timezone} onChange={(event) => setDraft({ ...draft, timezone: event.target.value })} placeholder="Africa/Lagos" /></label>
          </div>
          <label className="maintenance-enable-check"><input type="checkbox" checked={draft.enabled} onChange={(event) => setDraft({ ...draft, enabled: event.target.checked })} />Enable this rule after saving</label>
          <p className="maintenance-form-note">Only these fixed, allowlisted endpoint actions are available. Rules cannot run arbitrary commands. Disruptive actions should be scheduled for a suitable maintenance window.</p>
          <div className="modal-footer"><button type="button" onClick={() => setDraft(undefined)} disabled={saving}>Cancel</button><button type="submit" className="primary-action" disabled={saving || properties.loading}>{saving ? "Saving..." : draft.id ? "Save changes" : "Create rule"}</button></div>
        </form>
      </Modal>}
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
