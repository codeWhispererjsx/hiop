import { useEffect, useState } from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import { PageTitle } from "./DashboardPage";
import { Feedback } from "../components/Feedback";
import { endpoints } from "../lib/api";
import type { MonitoringSettings } from "../lib/types";

const labels: Record<keyof MonitoringSettings, string> = { network: "Approved network range", ping: "Ping interval (seconds)", scan: "Scan interval (minutes)", threshold: "Offline threshold (failed checks)" };
export default function SettingsPage() {
  const [draft, setDraft] = useState<MonitoringSettings>({ network: "", ping: "", scan: "", threshold: "" });
  const [busy, setBusy] = useState(true);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  useEffect(() => { endpoints.settings().then(setDraft).catch((error) => setNotice(error instanceof Error ? error.message : "Unable to load settings")).finally(() => setBusy(false)); }, []);
  const save = async () => { setSaving(true); setNotice(""); try { setDraft(await endpoints.updateSettings(draft)); setNotice("Settings saved for this backend session."); } catch (error) { setNotice(error instanceof Error ? error.message : "Save failed"); } finally { setSaving(false); } };
  return <DashboardLayout><PageTitle eyebrow="System configuration" title="Settings" copy="Monitoring configuration exposed by the local operations service."/>{busy ? <Feedback loading/> : <section className="settings-card"><div className="form-grid">{(Object.keys(draft) as Array<keyof MonitoringSettings>).map((key) => <label key={key}>{labels[key]}<input value={draft[key]} onChange={(event) => setDraft({ ...draft, [key]: event.target.value })}/></label>)}</div><button className="primary-action" disabled={saving} onClick={() => void save()}>{saving ? "Saving…" : "Save settings"}</button>{notice && <p className="inline-notice">{notice}</p>}</section>}</DashboardLayout>;
}
