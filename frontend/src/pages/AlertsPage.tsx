import { useMemo, useState } from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import { PageTitle } from "./DashboardPage";
import { Feedback } from "../components/Feedback";
import { StatusBadge } from "../components/StatusBadge";
import { StatCard } from "../components/StatCard";
import { Toast } from "../components/Toast";
import Modal from "../components/Modal";
import { Icon } from "../components/Icon";
import { useRequest } from "../hooks/useRequest";
import { endpoints } from "../lib/api";
import type { V3EAlert, V3EAlertRule } from "../lib/types";

export default function AlertsPage() {
  const [status, setStatus] = useState("");
  const [severity, setSeverity] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<V3EAlert>();
  const [mode, setMode] = useState<"alerts" | "events" | "rules">("alerts");
  const [notice, setNotice] = useState("");
  const [resolveOpen, setResolveOpen] = useState(false);

  const alerts = useRequest(
    () => endpoints.v3eAlerts({
      status: status || undefined,
      severity: severity || undefined,
      search: search || undefined,
    }),
    [status, severity, search]
  );
  const events = useRequest(endpoints.v3eEvents, []);
  const rules = useRequest(endpoints.v3eRules, []);
  const me = useRequest(endpoints.me, []);
  const canEditRules = me.data?.role === "admin";

  const counts = useMemo(
    () => ({
      open: (alerts.data?.items ?? []).filter((x) => x.status === "open").length,
      ack: (alerts.data?.items ?? []).filter((x) => x.status === "acknowledged").length,
      resolved: (alerts.data?.items ?? []).filter((x) => x.status === "resolved").length,
    }),
    [alerts.data]
  );

  const open = async (row: V3EAlert) => setSelected(await endpoints.v3eAlert(row.id));

  const acknowledge = async () => {
    if (!selected) return;
    setSelected(await endpoints.acknowledgeV3EAlert(selected.id));
    setNotice("Alert acknowledged and audited.");
    await alerts.reload();
  };

  const resolve = async (reason: string) => {
    if (!selected) return;
    setSelected(await endpoints.resolveV3EAlert(selected.id, reason));
    setResolveOpen(false);
    setNotice("Alert manually resolved and audited; monitoring continues independently.");
    await alerts.reload();
  };

  return (
    <DashboardLayout>
      <PageTitle
        eyebrow="V3E operations"
        title="Alerts & events"
        copy="Actionable, debounced monitoring conditions with preserved evidence and lifecycle history."
      />
      {notice && <Toast message={notice} />}
      <div className="alerts-tabs" role="tablist" aria-label="Alert center sections">
        {(["alerts", "events", "rules"] as const).map((tab) => (
          <button
            key={tab}
            role="tab"
            aria-selected={mode === tab}
            aria-controls={`${tab}-panel`}
            id={`${tab}-tab`}
            className={mode === tab ? "active" : ""}
            onClick={() => setMode(tab)}
          >
            {tab === "alerts" ? (
              <Icon name="alerts" aria-hidden="true" />
            ) : tab === "events" ? (
              <Icon name="clock" aria-hidden="true" />
            ) : (
              <Icon name="settings" aria-hidden="true" />
            )}
            <span>{tab[0].toUpperCase() + tab.slice(1)}</span>
          </button>
        ))}
      </div>

      {mode === "alerts" && (
        <>
          <section className="noc-summary" aria-label="Alert statistics">
            <StatCard
              label="Open"
              value={counts.open}
              detail="Requires attention"
              icon="warning"
              tone="danger"
            />
            <StatCard
              label="Acknowledged"
              value={counts.ack}
              detail="Owned but unresolved"
              icon="check"
              tone="warning"
            />
            <StatCard
              label="Recently resolved"
              value={counts.resolved}
              detail="History preserved"
              icon="audit"
              tone="success"
            />
            <StatCard
              label="Critical"
              value={alerts.data?.summary.critical ?? 0}
              detail="Critical severity"
              icon="alerts"
              tone="danger"
            />
          </section>

          <section className="panel alerts-panel" id="alerts-panel" role="tabpanel" aria-labelledby="alerts-tab">
            <div className="port-filters">
              <label htmlFor="alerts-search" className="search-field">
                <Icon name="search" aria-hidden="true" />
                <input
                  id="alerts-search"
                  type="search"
                  aria-label="Search alerts"
                  placeholder="Device, hostname, IP, or alert title"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </label>
              <select
                aria-label="Filter alert severity"
                value={severity}
                onChange={(e) => setSeverity(e.target.value)}
              >
                <option value="">All severities</option>
                <option value="critical">Critical</option>
                <option value="warning">Warning</option>
                <option value="info">Info</option>
              </select>
              <select
                aria-label="Filter alert status"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
              >
                <option value="">All statuses</option>
                <option value="open">Open</option>
                <option value="acknowledged">Acknowledged</option>
                <option value="resolved">Resolved</option>
              </select>
            </div>

            {alerts.loading || alerts.error ? (
              <Feedback loading={alerts.loading} error={alerts.error} />
            ) : (
              <div className="noc-table-wrap">
                <table className="noc-table">
                  <thead>
                    <tr>
                      <th scope="col">Severity</th>
                      <th scope="col">Alert</th>
                      <th scope="col">Device</th>
                      <th scope="col">Triggered</th>
                      <th scope="col">Status</th>
                      <th scope="col">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(alerts.data?.items ?? []).map((row) => (
                      <tr key={row.id}>
                        <td>
                          <StatusBadge status={row.severity} />
                        </td>
                        <td>
                          <strong>{row.title}</strong>
                          <small>{row.reason}</small>
                        </td>
                        <td>
                          <strong>{row.device_name}</strong>
                          <small>{row.ip_address ?? "IP unavailable"}</small>
                        </td>
                        <td>{new Date(row.triggered_at).toLocaleString()}</td>
                        <td>
                          <StatusBadge status={row.status} />
                        </td>
                        <td>
                          <button
                            className="secondary-action"
                            onClick={() => void open(row)}
                            aria-label={`View details for ${row.title}`}
                          >
                            View
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}

      {mode === "events" && (
        <>
          <section className="panel events-panel" id="events-panel" role="tabpanel" aria-labelledby="events-tab">
            <header>
              <h2>Alert events</h2>
              <p>Raw alert lifecycle events with timestamps and actor attribution.</p>
            </header>

            {events.loading || events.error ? (
              <Feedback loading={events.loading} error={events.error} />
            ) : (
              <div className="noc-table-wrap">
                <table className="noc-table">
                  <thead>
                    <tr>
                      <th scope="col">Timestamp</th>
                      <th scope="col">Alert</th>
                      <th scope="col">Action</th>
                      <th scope="col">Actor</th>
                      <th scope="col">Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(events.data?.items ?? []).map((row) => (
                      <tr key={row.id}>
                        <td>{new Date(row.created_at).toLocaleString()}</td>
                        <td>
                          <strong>{row.alert_title}</strong>
                          <small>{row.alert_id}</small>
                        </td>
                        <td>
                          <strong>{row.action}</strong>
                        </td>
                        <td>{row.actor}</td>
                        <td>{row.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}

      {mode === "rules" && (
        <Rules
          rows={rules.data?.items ?? []}
          reload={rules.reload}
          canEdit={canEditRules}
        />
      )}

      {selected && (
        <AlertDetails
          row={selected}
          acknowledge={acknowledge}
          resolve={() => setResolveOpen(true)}
          close={() => setSelected(undefined)}
        />
      )}

      {resolveOpen && (
        <ResolutionDialog
          title={selected?.title ?? "this alert"}
          close={() => setResolveOpen(false)}
          resolve={resolve}
        />
      )}
    </DashboardLayout>
  );
}

function AlertDetails({
  row,
  acknowledge,
  resolve,
  close,
}: {
  row: V3EAlert;
  acknowledge: () => Promise<void>;
  resolve: () => void;
  close: () => void;
}) {
  return (
    <Modal title="Alert details" onClose={close}>
      <div className="alert-detail-body">
        <div className="alert-detail-hero">
          <span className={`pulse ${row.severity}`} aria-hidden="true" />
          <div>
            <StatusBadge status={row.severity} />
            <h3>{row.title}</h3>
            <p>
              {row.device_name} · {row.ip_address ?? "IP unavailable"}
            </p>
          </div>
          <StatusBadge status={row.status} />
        </div>

        <dl className="alert-detail-grid">
          <div>
            <dt>Source</dt>
            <dd>{row.source}</dd>
          </div>
          <div>
            <dt>Triggered</dt>
            <dd>{new Date(row.triggered_at).toLocaleString()}</dd>
          </div>
          <div>
            <dt>Reason</dt>
            <dd>{row.reason}</dd>
          </div>
          <div>
            <dt>Current / threshold</dt>
            <dd>
              {row.current_value ?? "State condition"} /{" "}
              {row.threshold_value ?? "Rule state"}
            </dd>
          </div>
          <div>
            <dt>Acknowledged</dt>
            <dd>
              {row.acknowledged_at
                ? new Date(row.acknowledged_at).toLocaleString()
                : "Not acknowledged"}
            </dd>
          </div>
          <div>
            <dt>Resolution</dt>
            <dd>
              {row.resolution_reason ?? "Unresolved"}
              {row.manually_resolved ? " (manual)" : ""}
            </dd>
          </div>
        </dl>

        <section className="alert-detail-section">
          <h4>Evidence</h4>
          <pre className="alert-evidence">
            {JSON.stringify(row.evidence, null, 2)}
          </pre>
        </section>

        <section className="alert-detail-section">
          <h4>Alert history</h4>
          <div className="alert-history-list">
            {row.history?.length ? (
              row.history.map((x, index) => (
                <article key={index}>
                  <time>{new Date(x.created_at).toLocaleString()}</time>
                  <strong>{x.action}</strong>
                  <span>
                    {x.actor} · {x.reason}
                  </span>
                </article>
              ))
            ) : (
              <p>No lifecycle history recorded yet.</p>
            )}
          </div>
        </section>
      </div>

      {row.status !== "resolved" && (
        <footer className="alert-detail-actions">
          <button
            className="secondary-action"
            onClick={() => void acknowledge()}
            disabled={row.status === "acknowledged"}
            aria-label={
              row.status === "acknowledged"
                ? "Alert already acknowledged"
                : "Acknowledge this alert"
            }
          >
            <Icon name="check" aria-hidden="true" />
            {row.status === "acknowledged" ? "Acknowledged" : "Acknowledge alert"}
          </button>
          <button
            className="danger-action"
            onClick={resolve}
            aria-label="Resolve this alert manually"
          >
            <Icon name="audit" aria-hidden="true" />
            Resolve manually
          </button>
        </footer>
      )}
    </Modal>
  );
}

function ResolutionDialog({
  title,
  close,
  resolve,
}: {
  title: string;
  close: () => void;
  resolve: (reason: string) => Promise<void>;
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  return (
    <Modal title="Resolve alert manually" onClose={close}>
      <form
        className="alert-resolution-form"
        onSubmit={async (e) => {
          e.preventDefault();
          if (!reason.trim()) return;
          setBusy(true);
          try {
            await resolve(reason.trim());
          } finally {
            setBusy(false);
          }
        }}
      >
        <p>
          You are resolving <strong>{title}</strong> manually. This does not stop
          monitoring or claim that the underlying condition recovered.
        </p>
        <label htmlFor="resolution-reason">
          <span>Resolution reason</span>
          <textarea
            id="resolution-reason"
            autoFocus
            required
            rows={4}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Explain why this alert is being resolved manually"
            aria-describedby="resolution-help"
          />
          <small id="resolution-help">
            This reason will be recorded in the alert history and audit trail.
          </small>
        </label>
        <footer>
          <button
            type="button"
            className="secondary-action"
            onClick={close}
          >
            Cancel
          </button>
          <button
            className="danger-action"
            disabled={busy || !reason.trim()}
            aria-busy={busy}
          >
            {busy ? "Resolving…" : "Resolve alert"}
          </button>
        </footer>
      </form>
    </Modal>
  );
}

function Rules({
  rows,
  reload,
  canEdit,
}: {
  rows: V3EAlertRule[];
  reload: () => Promise<void>;
  canEdit: boolean;
}) {
  const [busy, setBusy] = useState<string>();

  const save = async (row: V3EAlertRule, enabled: boolean) => {
    setBusy(row.id);
    try {
      await endpoints.updateV3ERule(row.id, {
        enabled,
        severity: row.severity,
        threshold_value: row.threshold_value,
        duration_minutes: row.duration_minutes,
        consecutive_observations: row.consecutive_observations,
        notify_in_app: row.notify_in_app,
        notify_email: row.notify_email,
      });
      await reload();
    } finally {
      setBusy(undefined);
    }
  };

  return (
    <section className="panel alert-rules" id="rules-panel" role="tabpanel" aria-labelledby="rules-tab">
      <header>
        <h2>Predefined alert rules</h2>
        <p>
          Administrators can enable or disable bounded rules; no arbitrary rule
          scripting is supported.
        </p>
      </header>

      {!canEdit && (
        <p className="settings-note" role="note">
          Rule settings are read-only for your account. An Organization Administrator can enable, disable, and tune predefined rules.
        </p>
      )}

      {!rows.length && <Feedback emptyTitle="No predefined rules are configured." empty="Alert rules are created by platform configuration; no arbitrary rule scripts are accepted." />}

      {rows.map((row) => (
        <article className="admin-entry" key={row.id}>
          <div>
            <h3>{row.name}</h3>
            <p>
              {row.description} · {row.severity} · {row.consecutive_observations}{" "}
              observations
              {row.threshold_value != null ? ` · threshold ${row.threshold_value}` : ""}
            </p>
          </div>
          <div className="alert-rule-state">
            <StatusBadge status={row.enabled ? "active" : "disabled"} />
            {canEdit && (
              <button
                className={row.enabled ? "danger-action" : "primary-action"}
                disabled={busy === row.id}
                onClick={() => void save(row, !row.enabled)}
                aria-label={
                  row.enabled
                    ? `Disable rule ${row.name}`
                    : `Enable rule ${row.name}`
                }
                aria-busy={busy === row.id}
              >
                {busy === row.id
                  ? "Updating…"
                  : row.enabled
                  ? "Disable rule"
                  : "Enable rule"}
              </button>
            )}
          </div>
        </article>
      ))}
    </section>
  );
}
