import { useCallback, useMemo, useState } from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import { PageTitle } from "./DashboardPage";
import { Feedback } from "../components/Feedback";
import { endpoints } from "../lib/api";
import { useRequest } from "../hooks/useRequest";
import type { LiveEvent } from "../lib/types";

export default function AlertsPage() {
  const alerts = useRequest(endpoints.alerts, []);
  const reloadAlerts = alerts.reload;
  const [showAcknowledged, setShowAcknowledged] = useState(true);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const rows = useMemo(
    () => (alerts.data ?? []).filter((alert) => showAcknowledged || !alert.acknowledged),
    [alerts.data, showAcknowledged],
  );
  const acknowledge = async (id: string) => {
    setBusy(id);
    setNotice("");
    try {
      await endpoints.acknowledgeAlert(id);
      setNotice("Alert acknowledged.");
      await alerts.reload();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Unable to acknowledge alert");
    } finally {
      setBusy("");
    }
  };
  const live = useCallback((event: LiveEvent) => {
    if (event.event === "device_status_changed") void reloadAlerts();
  }, [reloadAlerts]);

  return <DashboardLayout onLiveEvent={live}>
    <PageTitle eyebrow="Attention centre" title="Alerts" copy="Persistent device status alerts recorded by the monitoring service." action={<button className="secondary-action" onClick={() => void alerts.reload()}>Refresh</button>}/>
    {notice && <div className="inline-notice">{notice}</div>}
    <section className="toolbar-panel">
      <label className="checkbox-field"><input type="checkbox" checked={showAcknowledged} onChange={(event) => setShowAcknowledged(event.target.checked)}/> Show acknowledged alerts</label>
    </section>
    {alerts.loading || alerts.error || !rows.length
      ? <Feedback loading={alerts.loading} error={alerts.error} empty="No alerts match the current view." onRetry={alerts.reload}/>
      : <section className="event-list">{rows.map((alert) => <article key={alert.id} className={alert.acknowledged ? "acknowledged" : ""}>
          <span className={`pulse ${alert.current_status.toLowerCase()}`}/>
          <div><strong>{alert.message}</strong><p>{alert.previous_status} → {alert.current_status}</p></div>
          <time>{new Date(alert.created_at).toLocaleString()}</time>
          <button className="secondary-action" disabled={alert.acknowledged || busy === alert.id} onClick={() => void acknowledge(alert.id)}>{alert.acknowledged ? "Acknowledged" : busy === alert.id ? "Saving…" : "Acknowledge"}</button>
        </article>)}</section>}
  </DashboardLayout>;
}
