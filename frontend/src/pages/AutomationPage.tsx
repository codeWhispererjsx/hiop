import { useEffect, useState } from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import { Feedback } from "../components/Feedback";
import { PageTitle } from "./DashboardPage";
import { endpoints } from "../lib/api";
import { formatDateTime } from "../lib/dateTime";
import type { AutomationFeatureStatus, AutomationStatus, SettingsBundle } from "../lib/types";

export default function AutomationPage() {
  const [settings, setSettings] = useState<SettingsBundle>();
  const [status, setStatus] = useState<AutomationStatus>();
  const [error, setError] = useState("");
  const [statusError, setStatusError] = useState("");
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);

  const refreshStatus = async () => {
    try {
      setStatus(await endpoints.automationStatus());
      setStatusError("");
    } catch (caught) {
      setStatusError(caught instanceof Error ? caught.message : "Automation status could not be loaded.");
    }
  };

  useEffect(() => {
    let active = true;
    endpoints.settings()
      .then((value) => { if (active) setSettings(value); })
      .catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : "Settings could not be loaded."); });
    endpoints.automationStatus()
      .then((value) => { if (active) setStatus(value); })
      .catch((caught) => { if (active) setStatusError(caught instanceof Error ? caught.message : "Automation status could not be loaded."); });
    return () => { active = false; };
  }, []);

  const saveNetwork = async () => {
    if (!settings) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const next = await endpoints.updateNetworkSettings(settings.network);
      setSettings(next);
      setNotice("Network automation settings saved.");
      await refreshStatus();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Network settings could not be saved.");
    } finally {
      setSaving(false);
    }
  };

  const saveNotifications = async () => {
    if (!settings) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const next = await endpoints.updateNotificationSettings(settings.notifications);
      setSettings(next);
      setNotice("Email automation settings saved.");
      await refreshStatus();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Email settings could not be saved.");
    } finally {
      setSaving(false);
    }
  };

  if (error && !settings) {
    return <DashboardLayout><PageTitle eyebrow="Automate" title="Automation" copy="Configure and verify recurring operations." /><Feedback loading={false} error={error} /></DashboardLayout>;
  }
  if (!settings) {
    return <DashboardLayout><PageTitle eyebrow="Automate" title="Automation" copy="Configure and verify recurring operations." /><Feedback loading empty="Loading automation settings." /></DashboardLayout>;
  }

  const network = settings.network;
  const notifications = settings.notifications;

  return (
    <DashboardLayout>
      <PageTitle eyebrow="Automate" title="Automation" copy="Configure routine checks and see whether each enabled feature is actually operating." />
      {error && <p className="form-error" role="alert">{error}</p>}
      {notice && <p className="inline-notice" role="status">{notice}</p>}

      <section className="panel automation-panel">
        <header className="section-head">
          <div><h2>Network monitoring</h2><p>Scheduled monitoring runs scans from this HIOP installation against the configured device inventory.</p></div>
        </header>
        <div className="settings-toggles">
          <Toggle label="Scheduled network scans" detail={`Scan every ${network.scan_interval_minutes} minutes`} checked={network.automatic_scanning} onChange={(checked) => setSettings({ ...settings, network: { ...network, automatic_scanning: checked } })} />
          <Toggle label="Automatic offline incidents" detail="Create an incident after the configured consecutive offline checks" checked={network.automatic_offline_tickets} onChange={(checked) => setSettings({ ...settings, network: { ...network, automatic_offline_tickets: checked } })} />
        </div>
        <div className="automation-controls">
          <label><span>Scan interval</span><small>Minutes between scheduled scans</small><input type="number" min="5" max="1440" value={network.scan_interval_minutes} onChange={(event) => setSettings({ ...settings, network: { ...network, scan_interval_minutes: Number(event.target.value) } })} /></label>
          <label><span>Offline threshold</span><small>Consecutive failed checks before creating an incident</small><input type="number" min="1" max="20" value={network.offline_threshold} onChange={(event) => setSettings({ ...settings, network: { ...network, offline_threshold: Number(event.target.value) } })} /></label>
          <button className="primary-action" disabled={saving} onClick={() => void saveNetwork()}>{saving ? "Saving…" : "Save monitoring settings"}</button>
        </div>
        {status && <div className="automation-status-grid">
          <StatusCard title="Automatic offline incidents" status={status.automatic_offline_incidents} />
        </div>}
      </section>

      <section className="panel automation-panel">
        <header className="section-head">
          <div><h2>Email notifications and audit delivery</h2><p>SMTP is supplied by the server administrator; the settings below select what HIOP sends and where.</p></div>
        </header>
        <div className="settings-toggles">
          <Toggle label="Email notifications" detail="Send supported operational notifications to the configured recipient" checked={notifications.email_notifications} onChange={(checked) => setSettings({ ...settings, notifications: { ...notifications, email_notifications: checked } })} />
          <Toggle label="Daily audit log email" detail="Send a daily digest of this organization's audit activity" checked={notifications.daily_audit_email} onChange={(checked) => setSettings({ ...settings, notifications: { ...notifications, daily_audit_email: checked } })} />
        </div>
        <div className="automation-controls">
          <label><span>Recipient email</span><small>Used for operational and audit messages</small><input type="email" value={notifications.recipient_email ?? ""} onChange={(event) => setSettings({ ...settings, notifications: { ...notifications, recipient_email: event.target.value || null } })} /></label>
          <label><span>Daily audit delivery time</span><small>Uses the organization's configured time zone</small><input type="time" value={notifications.daily_audit_time} onChange={(event) => setSettings({ ...settings, notifications: { ...notifications, daily_audit_time: event.target.value } })} /></label>
          <button className="primary-action" disabled={saving} onClick={() => void saveNotifications()}>{saving ? "Saving…" : "Save email settings"}</button>
        </div>
        {statusError && <p className="form-error" role="alert">Settings were loaded, but live automation status is unavailable: {statusError}</p>}
        {status && <div className="automation-status-grid">
          <StatusCard title="Email notifications" status={status.email_notifications} />
          <StatusCard title="Daily audit email" status={status.daily_audit_email} />
        </div>}
      </section>
    </DashboardLayout>
  );
}

function StatusCard({ title, status }: { title: string; status: AutomationFeatureStatus }) {
  return (
    <article className="automation-status-card">
      <header><h3>{title}</h3><strong className={`status-${status.state}`}>{status.state.replaceAll("_", " ")}</strong></header>
      <p>{status.details}</p>
      <dl>
        <div><dt>Last successful run</dt><dd>{status.last_success ? formatDateTime(status.last_success) : "None recorded"}</dd></div>
        <div><dt>Last attempt</dt><dd>{status.last_attempt ? formatDateTime(status.last_attempt) : "None recorded"}</dd></div>
      </dl>
      {status.last_error && <p className="form-error" role="alert">{status.last_error}</p>}
    </article>
  );
}

function Toggle({ label, detail, checked, onChange }: { label: string; detail: string; checked: boolean; onChange: (checked: boolean) => void }) {
  return <label className="settings-toggle"><input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} /><i aria-hidden="true" /><span><strong>{label}</strong><small>{detail}</small></span></label>;
}
