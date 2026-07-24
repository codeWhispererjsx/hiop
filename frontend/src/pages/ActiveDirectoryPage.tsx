/* eslint-disable react-hooks/set-state-in-effect, @typescript-eslint/no-unused-vars */
import {
  useCallback, useEffect, useState, type FormEvent, type ReactNode,
} from "react";
import { Link, useLocation } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import Modal from "../components/Modal";
import { Feedback } from "../components/Feedback";
import { StatCard } from "../components/StatCard";
import { Toast } from "../components/Toast";
import { endpoints } from "../lib/api";
import type {
  ADConnection, ADConnectionInput, ADMatch, ADObject, ADRootDse,
  ADSyncConfig, ADSyncRun, ADChange, ADMapping,
} from "../lib/types";
import { useRequest } from "../hooks/useRequest";
import { getAuthToken } from "../lib/auth";
import "../styles/active-directory.css";

/* ─── helpers ─────────────────────────────────────────────────────────── */
const tabs = [
  ["", "Overview"], ["connections", "Connections"], ["sync-runs", "Sync runs"],
  ["objects", "Directory objects"], ["matches", "Reconciliation"],
  ["mappings", "Mappings"], ["review", "Missing review"], ["reports", "Reports"],
] as const;

const fmt = (value?: string | null) =>
  value ? new Date(value).toLocaleString() : "Never";

const dur = (ms?: number | null) =>
  ms == null ? "—" : ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;

const stateClass = (value?: string | null) =>
  `ad-state state-${(value ?? "unknown").toLowerCase().replaceAll("_", "-")}`;

/* ─── WebSocket events ─────────────────────────────────────────────────── */
const AD_WS_EVENTS = new Set([
  "ad_connection_test_completed", "ad_sync_started", "ad_sync_progress",
  "ad_sync_completed", "ad_sync_failed", "ad_match_run_completed",
  "ad_object_resolved", "ad_mapping_changed", "ad_review_queue_updated",
]);

function useADWebSocket(onEvent: (event: string, data: unknown) => void) {
  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimeout: ReturnType<typeof setTimeout> | undefined;

    function connect() {
      const token = getAuthToken();
      if (!token) return;
      const base = (import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8001/api/v1")
        .replace(/^http/, "ws").replace("/api/v1", "");
      try {
        ws = new WebSocket(`${base}/ws`, ["Bearer", token]);
        ws.onmessage = (e: MessageEvent) => {
          try {
            const msg = JSON.parse(String(e.data)) as { event?: string; data?: unknown };
            if (msg.event && AD_WS_EVENTS.has(msg.event)) onEvent(msg.event, msg.data);
          } catch { /* ignore non-JSON */ }
        };
        ws.onclose = () => {
          reconnectTimeout = setTimeout(connect, 5000);
        };
      } catch { /* WS not available, fallback to polling */ }
    }

    connect();

    return () => {
      clearTimeout(reconnectTimeout);
      ws?.close();
    };
  }, [onEvent]);
}

/* ─── root page ────────────────────────────────────────────────────────── */
export default function ActiveDirectoryPage() {
  const location = useLocation();
  const user = useRequest(endpoints.me, []);
  const section = location.pathname.replace(/^\/active-directory\/?/, "").split("/")[0] || "";

  if (user.loading || user.error || !user.data)
    return <DashboardLayout><Feedback loading={user.loading} error={user.error} onRetry={user.reload} /></DashboardLayout>;
  if (user.data.role !== "admin")
    return <DashboardLayout><Feedback error="Administrator access is required for Active Directory administration." /></DashboardLayout>;

  return (
    <DashboardLayout>
      <div className="ad-title">
        <div>
          <small>Administration</small>
          <h1>Active Directory</h1>
          <p>Secure directory connectivity, staging, reconciliation, and scheduled synchronisation.</p>
        </div>
      </div>
      <nav className="ad-tabs" aria-label="Active Directory sections">
        {tabs.map(([path, label]) => (
          <Link key={path} className={section === path ? "active" : ""} to={`/active-directory${path ? `/${path}` : ""}`}>
            {label}
          </Link>
        ))}
      </nav>
      {section === "" && <Overview />}
      {section === "connections" && <Connections />}
      {section === "sync-runs" && <SyncRuns />}
      {section === "objects" && <Objects />}
      {section === "matches" && <Matches />}
      {section === "mappings" && <Mappings />}
      {section === "review" && <ReviewQueue />}
      {section === "reports" && <Reports />}
    </DashboardLayout>
  );
}

/* ─── Overview ─────────────────────────────────────────────────────────── */
function Overview() {
  const data = useRequest(endpoints.adOverview, []);
  const runs = useRequest(() => endpoints.adSyncRuns({ page_size: 5 }), []);

  // refresh on AD WS events
  const handleWS = useCallback((_event: string, _payload: unknown) => {
    void data.reload();
    void runs.reload();
  }, [data, runs]);
  useADWebSocket(handleWS);

  if (data.loading || data.error || !data.data)
    return <Feedback loading={data.loading} error={data.error} onRetry={data.reload} />;
  const d = data.data;
  return <>
    <section className="stats-grid">
      <StatCard label="Connections" value={d.configured_connections}
        detail={`${d.healthy_connections} healthy · ${d.failed_connection_tests} failed`} icon="network" />
      <StatCard label="Staged users" value={d.staged.users}
        detail={`${d.staged.computers} computers · ${d.staged.groups} groups`} icon="users" />
      <StatCard label="Pending matches" value={d.pending_matches}
        detail={`${d.conflicts} conflicts`} icon="warning" tone={d.conflicts ? "warning" : undefined} />
      <StatCard label="Scheduled syncs" value={d.scheduled_syncs}
        detail={d.scheduler_running ? "Scheduler active" : "Scheduler stopped"} icon="settings" />
    </section>
    <div className="ad-overview-grid">
      <Panel title="Connection health">
        <dl className="ad-kv">
          <div><dt>Status</dt><dd>{d.integration_enabled ? "AD integration enabled" : "Globally disabled"}</dd></div>
          <div><dt>Failed tests</dt><dd>{d.failed_connection_tests}</dd></div>
          <div><dt>Missing objects</dt><dd>{d.missing_objects}</dd></div>
          <div><dt>Last successful sync</dt><dd>{fmt(d.last_successful_sync)}</dd></div>
        </dl>
        <Link to="/active-directory/connections" className="ad-link">Manage connections →</Link>
      </Panel>
      <Panel title="Review queues">
        <dl className="ad-kv">
          <div><dt>Pending matches</dt><dd>{d.pending_matches}</dd></div>
          <div><dt>Conflicts</dt><dd>{d.conflicts}</dd></div>
          <div><dt>Missing objects</dt><dd>{d.missing_objects}</dd></div>
        </dl>
        <div className="ad-panel-actions">
          <Link to="/active-directory/matches" className="ad-link">Open reconciliation →</Link>
          <Link to="/active-directory/review" className="ad-link">Missing review →</Link>
        </div>
      </Panel>
      <Panel title="Production guard">
        <p>Directory changes remain staged until an administrator explicitly reconciles them. No HIOP user or device is modified automatically.</p>
        <p className="ad-warning">Bulk Admin-role mapping requires explicit additional confirmation and is never applied silently.</p>
      </Panel>
      <Panel title="Recent sync runs" wide>
        {runs.loading && <Feedback loading />}
        {!runs.loading && !runs.data?.items.length && <Feedback empty="No synchronisation runs yet." />}
        {runs.data?.items.length ? (
          <div className="ad-table-wrap">
            <table className="ad-table">
              <thead><tr><th>Status</th><th>Mode</th><th>Trigger</th><th>Started</th><th>Objects</th><th>Duration</th></tr></thead>
              <tbody>
                {runs.data.items.map(r => (
                  <tr key={r.id}>
                    <td><span className={stateClass(r.status)}>{r.status}</span></td>
                    <td>{r.sync_mode}{r.dry_run && <small>Dry run</small>}</td>
                    <td>{r.trigger_type}</td>
                    <td>{fmt(r.started_at)}</td>
                    <td>{r.users_seen + r.computers_seen + r.groups_seen}</td>
                    <td>{dur(r.duration_ms)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        <Link to="/active-directory/sync-runs" className="ad-link">All sync runs →</Link>
      </Panel>
    </div>
  </>;
}

/* ─── Connections ──────────────────────────────────────────────────────── */
function Connections() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 25;
  const list = useRequest(() => endpoints.adConnections({
    search: search || undefined,
    enabled_only: statusFilter === "enabled" ? 1 : undefined,
    offset: (page - 1) * pageSize, limit: pageSize,
  }), [search, statusFilter, page]);
  const [editing, setEditing] = useState<ADConnection | null | undefined>();
  const [secretFor, setSecretFor] = useState<ADConnection | null>(null);
  const [testing, setTesting] = useState<ADConnection | null>(null);
  const [syncing, setSyncing] = useState<ADConnection | null>(null);
  const [syncConfig, setSyncConfig] = useState<ADConnection | null>(null);
  const [rootDse, setRootDse] = useState<ADConnection | null>(null);
  const [notice, setNotice] = useState("");

  const handleWS = useCallback((_: string, __: unknown) => void list.reload(), [list]);
  useADWebSocket(handleWS);

  const toggleEnabled = async (c: ADConnection) => {
    try {
      if (c.enabled) {
        if (!window.confirm(`Disable connection "${c.name}"? Scheduled syncs will stop.`)) return;
        await endpoints.disableADConnection(c.id);
        setNotice("Connection disabled.");
      } else {
        await endpoints.updateADConnection(c.id, { enabled: true });
        setNotice("Connection enabled.");
      }
      await list.reload();
    } catch (e) { setNotice(e instanceof Error ? e.message : "Action failed"); }
  };

  if (list.loading && !list.data || list.error)
    return <Feedback loading={list.loading} error={list.error} onRetry={list.reload} />;

  const total = list.data?.total ?? 0;
  const pages = Math.ceil(total / pageSize);

  return <>
    {notice && <Toast message={notice} tone={notice.toLowerCase().includes("fail") || notice.toLowerCase().includes("error") ? "error" : "success"} />}
    <Toolbar title="Connections" action={<button className="primary-action" onClick={() => setEditing(null)}>Add connection</button>} />
    <div className="ad-filters">
      <label>Search<input value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} placeholder="Name, domain, host…" /></label>
      <label>Status
        <select value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(1); }}>
          <option value="">All</option>
          <option value="enabled">Enabled only</option>
        </select>
      </label>
    </div>
    {!list.data?.items.length ? <Feedback empty="No Active Directory connections match." /> : (
      <div className="ad-table-wrap">
        <table className="ad-table">
          <thead><tr>
            <th>Name</th><th>Domain / server</th><th>Security</th>
            <th>Status</th><th>Last tested</th><th>Last sync</th><th>Scheduled</th><th>Actions</th>
          </tr></thead>
          <tbody>
            {list.data.items.map(c => (
              <tr key={c.id}>
                <td>
                  <strong>{c.name}</strong>
                  <small>{c.secret_configured ? "Secret configured" : "⚠ Secret required"}</small>
                </td>
                <td>{c.domain_name}<small>{c.server_host}:{c.server_port}</small></td>
                <td>
                  {c.use_ssl ? "LDAPS" : c.use_start_tls ? "StartTLS" : "LDAP"}
                  <small>{c.verify_tls ? "TLS verified" : "Verification off"}</small>
                </td>
                <td><span className={stateClass(c.enabled ? (c.last_test_status ?? "untested") : "disabled")}>
                  {c.enabled ? (c.last_test_status ?? "not tested") : "disabled"}
                </span></td>
                <td>{fmt(c.last_tested_at)}</td>
                <td>{fmt(c.last_successful_bind_at)}</td>
                <td><span className={stateClass(c.enabled ? "enabled" : "disabled")}>{c.enabled ? "active" : "off"}</span></td>
                <td>
                  <div className="ad-actions">
                    <button onClick={() => setEditing(c)}>Edit</button>
                    <button onClick={() => setTesting(c)}>Test</button>
                    <button onClick={() => setRootDse(c)}>RootDSE</button>
                    <button onClick={() => setSecretFor(c)}>Secret</button>
                    <button onClick={() => setSyncConfig(c)}>Sync config</button>
                    <button onClick={() => setSyncing(c)}>Sync now</button>
                    <button onClick={() => void toggleEnabled(c)}>{c.enabled ? "Disable" : "Enable"}</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )}
    {pages > 1 && (
      <div className="ad-pagination">
        <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Previous</button>
        <span>Page {page} of {pages} ({total} total)</span>
        <button disabled={page >= pages} onClick={() => setPage(p => p + 1)}>Next</button>
      </div>
    )}
    {editing !== undefined && (
      <ConnectionDialog initial={editing} close={() => setEditing(undefined)}
        saved={async () => { setEditing(undefined); await list.reload(); }} />
    )}
    {secretFor && <SecretDialog connection={secretFor} close={() => setSecretFor(null)} />}
    {testing && <TestDialog connection={testing} close={() => { setTesting(null); void list.reload(); }} />}
    {syncing && <SyncDialog connection={syncing} close={() => setSyncing(null)} />}
    {syncConfig && <SyncConfigDialog connection={syncConfig} close={() => setSyncConfig(null)} saved={() => { setSyncConfig(null); void list.reload(); }} />}
    {rootDse && <RootDseDialog connection={rootDse} close={() => setRootDse(null)} />}
  </>;
}

/* ─── Connection dialog ────────────────────────────────────────────────── */
function ConnectionDialog({ initial, close, saved }: { initial: ADConnection | null; close: () => void; saved: () => void }) {
  const [form, setForm] = useState<ADConnectionInput>({
    name: initial?.name ?? "", domain_name: initial?.domain_name ?? "",
    server_host: initial?.server_host ?? "", server_port: initial?.server_port ?? 636,
    use_ssl: initial?.use_ssl ?? true, use_start_tls: initial?.use_start_tls ?? false,
    verify_tls: initial?.verify_tls ?? true, base_dn: initial?.base_dn ?? "",
    user_search_base: initial?.user_search_base ?? "", computer_search_base: initial?.computer_search_base ?? "",
    group_search_base: initial?.group_search_base ?? "", bind_username: initial?.bind_username ?? "",
    authentication_method: initial?.authentication_method ?? "simple",
    connection_timeout_seconds: initial?.connection_timeout_seconds ?? 10,
    page_size: initial?.page_size ?? 500, enabled: initial?.enabled ?? true,
  });
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const set = (key: string, value: unknown) => setForm(p => ({ ...p, [key]: value }));
  const insecure = !form.use_ssl && !form.use_start_tls;
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setError("");
    try {
      if (initial) { await endpoints.updateADConnection(initial.id, form); } else { await endpoints.createADConnection(form); }
      saved();
    } catch (x) { setError(x instanceof Error ? x.message : "Save failed"); } finally { setBusy(false); }
  };
  return (
    <Modal title={initial ? "Edit connection" : "New connection"} onClose={close}>
      <form className="ad-form" onSubmit={submit}>
        {error && <p className="form-error wide" role="alert">{error}</p>}
        {insecure && <p className="ad-warning wide" role="alert">⚠ Plain LDAP is development-only and will be rejected in production.</p>}
        <label>Name<input required value={form.name} onChange={e => set("name", e.target.value)} /></label>
        <label>Domain<input required placeholder="corp.example.com" value={form.domain_name} onChange={e => set("domain_name", e.target.value)} /></label>
        <label>Server host<input required value={form.server_host} onChange={e => set("server_host", e.target.value)} /></label>
        <label>Port<input required type="number" min="1" max="65535" value={form.server_port} onChange={e => set("server_port", Number(e.target.value))} /></label>
        <label>Base DN<input required placeholder="DC=corp,DC=example,DC=com" value={form.base_dn} onChange={e => set("base_dn", e.target.value)} /></label>
        <label>Bind username<input value={form.bind_username ?? ""} onChange={e => set("bind_username", e.target.value)} /></label>
        {!initial && (
          <label className="wide">Bind secret
            <input type="password" autoComplete="new-password" onChange={e => set("bind_secret", e.target.value)} />
            <small>Write-only and encrypted by the backend. Never stored in browser.</small>
          </label>
        )}
        {initial && <p className="wide" style={{ gridColumn: "1/-1", margin: 0, fontSize: 13, color: "var(--muted)" }}>
          To rotate the bind secret use the <strong>Secret</strong> action on the connections list.
        </p>}
        <label>User search base<input value={form.user_search_base ?? ""} onChange={e => set("user_search_base", e.target.value)} /></label>
        <label>Computer search base<input value={form.computer_search_base ?? ""} onChange={e => set("computer_search_base", e.target.value)} /></label>
        <label>Group search base<input value={form.group_search_base ?? ""} onChange={e => set("group_search_base", e.target.value)} /></label>
        <label>Connection timeout (seconds)<input type="number" min="1" max="120" value={form.connection_timeout_seconds} onChange={e => set("connection_timeout_seconds", Number(e.target.value))} /></label>
        <label>Page size<input type="number" min="1" max="1000" value={form.page_size} onChange={e => set("page_size", Number(e.target.value))} /></label>
        <fieldset className="wide">
          <legend>Transport</legend>
          <label><input type="checkbox" checked={Boolean(form.use_ssl)} onChange={e => set("use_ssl", e.target.checked)} /> LDAPS (port 636)</label>
          <label><input type="checkbox" checked={Boolean(form.use_start_tls)} onChange={e => set("use_start_tls", e.target.checked)} /> StartTLS (port 389)</label>
          <label><input type="checkbox" checked={Boolean(form.verify_tls)} onChange={e => set("verify_tls", e.target.checked)} /> Verify TLS certificate</label>
        </fieldset>
        <label className="wide" style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
          <input type="checkbox" checked={Boolean(form.enabled)} onChange={e => set("enabled", e.target.checked)} /> Enabled
        </label>
        <footer className="wide">
          <button type="button" className="secondary-action" onClick={close}>Cancel</button>
          <button className="primary-action" disabled={busy}>{busy ? "Saving…" : "Save connection"}</button>
        </footer>
      </form>
    </Modal>
  );
}

/* ─── Secret dialog ────────────────────────────────────────────────────── */
function SecretDialog({ connection, close }: { connection: ADConnection; close: () => void }) {
  const [secret, setSecret] = useState(""); const [confirm, setConfirm] = useState("");
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (secret !== confirm) { setError("Secret confirmation does not match."); return; }
    setBusy(true);
    try {
      await endpoints.updateADSecret(connection.id, secret);
      setSecret(""); setConfirm(""); setDone(true);
    } catch (x) { setError(x instanceof Error ? x.message : "Update failed"); } finally { setBusy(false); }
  };
  return (
    <Modal title={`Rotate bind secret · ${connection.name}`} onClose={close}>
      <form className="ad-form single" onSubmit={submit}>
        <p className="wide">The existing secret is <strong>never returned</strong>. The replacement is transmitted once and encrypted at rest. It is never stored in this browser.</p>
        {done && <p className="wide" style={{ color: "var(--success)" }}>✓ Secret updated successfully. Use <strong>Test connection</strong> to verify the new credentials.</p>}
        {error && <p role="alert" className="form-error wide">{error}</p>}
        <label>New secret<input required type="password" autoComplete="new-password" value={secret} onChange={e => setSecret(e.target.value)} /></label>
        <label>Confirm secret<input required type="password" autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)} /></label>
        <footer className="wide">
          <button type="button" className="secondary-action" onClick={close}>Close</button>
          <button className="primary-action" disabled={busy || !secret || done}>{busy ? "Updating…" : "Update secret"}</button>
        </footer>
      </form>
    </Modal>
  );
}

/* ─── Test dialog ──────────────────────────────────────────────────────── */
function TestDialog({ connection, close }: { connection: ADConnection; close: () => void }) {
  const [result, setResult] = useState<import("../lib/types").ADTestResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const run = async () => {
    setRunning(true); setError(""); setResult(null);
    try { setResult(await endpoints.testADConnection(connection.id)); }
    catch (e) { setError(e instanceof Error ? e.message : "Test failed"); }
    finally { setRunning(false); }
  };
  useEffect(() => { void run(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Modal title={`Connection test · ${connection.name}`} onClose={close}>
      <div aria-live="polite">
        {running && <Feedback loading />}
        {error && <><Feedback error={error} /><button className="secondary-action" onClick={() => void run()}>Retry</button></>}
        {result && <>
          <div className="ad-test-header">
            <span className={stateClass(result.overall_status)}>{result.overall_status}</span>
            <small>{result.duration_ms} ms · {fmt(result.tested_at)}</small>
          </div>
          {result.warnings.length > 0 && (
            <ul className="ad-test-warnings">
              {result.warnings.map((w, i) => <li key={i}>⚠ {w}</li>)}
            </ul>
          )}
          <div className="ad-stages">
            {result.stages.map((s, i) => (
              <div key={`${s.stage ?? s.name}-${i}`}>
                <strong>{s.stage ?? s.name ?? `Stage ${i + 1}`}</strong>
                <span className={stateClass(s.status)}>{s.status}</span>
                {s.message && <small>{s.message}</small>}
                {s.duration_ms != null && <small>{s.duration_ms} ms</small>}
              </div>
            ))}
          </div>
          <footer style={{ marginTop: 12, display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <button className="secondary-action" onClick={() => void run()}>Re-test</button>
            <button className="primary-action" onClick={close}>Close</button>
          </footer>
        </>}
      </div>
    </Modal>
  );
}

/* ─── RootDSE dialog ───────────────────────────────────────────────────── */
function RootDseDialog({ connection, close }: { connection: ADConnection; close: () => void }) {
  const data = useRequest<ADRootDse>(() => endpoints.adRootDse(connection.id), [connection.id]);
  return (
    <Modal title={`RootDSE · ${connection.name}`} onClose={close}>
      {data.loading && <Feedback loading />}
      {data.error && <Feedback error={data.error} onRetry={data.reload} />}
      {data.data && <>
        <p style={{ color: "var(--muted)", marginTop: 0 }}>Safe directory metadata. Credentials are not returned. Use <em>Suggested base DN</em> to assist configuration — values are never overwritten automatically.</p>
        <dl className="ad-detail"><div>
          <div><dt>Default naming context</dt><dd>{data.data.default_naming_context ?? "—"}</dd></div>
          <div><dt>Root domain</dt><dd>{data.data.root_domain_naming_context ?? "—"}</dd></div>
          <div><dt>DNS host name</dt><dd>{data.data.dns_host_name ?? "—"}</dd></div>
          <div><dt>LDAP versions</dt><dd>{data.data.supported_ldap_versions.join(", ") || "—"}</dd></div>
          <div><dt>SASL mechanisms</dt><dd>{data.data.supported_sasl_mechanisms.join(", ") || "—"}</dd></div>
          <div><dt>Appears Active Directory</dt><dd>{data.data.appears_active_directory ? "Yes" : "No"}</dd></div>
        </div></dl>
        {data.data.default_naming_context && (
          <div className="ad-rootdse-suggest">
            <p>Suggested base DN: <code>{data.data.default_naming_context}</code></p>
            <small>Copy this value and paste it into the connection form manually. Automatic overwrite is not performed.</small>
          </div>
        )}
        <footer style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}>
          <button className="primary-action" onClick={close}>Close</button>
        </footer>
      </>}
    </Modal>
  );
}

/* ─── Sync config dialog ───────────────────────────────────────────────── */
function SyncConfigDialog({ connection, close, saved }: { connection: ADConnection; close: () => void; saved: () => void }) {
  const initial = useRequest<ADSyncConfig>(() => endpoints.adSyncConfig(connection.id), [connection.id]);
  const [form, setForm] = useState<Partial<ADSyncConfig>>({});
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  useEffect(() => {
    if (initial.data) setForm(initial.data);
  }, [initial.data]);
  const set = (key: string, value: unknown) => setForm(p => ({ ...p, [key]: value }));
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setError("");
    try {
      await endpoints.updateADSyncConfig(connection.id, form);
      saved();
    } catch (x) { setError(x instanceof Error ? x.message : "Save failed"); } finally { setBusy(false); }
  };
  if (initial.loading) return <Modal title={`Sync configuration · ${connection.name}`} onClose={close}><Feedback loading /></Modal>;
  if (initial.error) return <Modal title={`Sync configuration · ${connection.name}`} onClose={close}><Feedback error={initial.error} onRetry={initial.reload} /></Modal>;
  const autoCreate = Boolean(form.auto_create_users || form.auto_create_devices);
  return (
    <Modal title={`Sync configuration · ${connection.name}`} onClose={close}>
      <form className="ad-form" onSubmit={submit}>
        {error && <p className="form-error wide" role="alert">{error}</p>}
        {autoCreate && <p className="ad-warning wide">Auto-create is enabled. New HIOP records are created only after administrator reconciliation review — never automatically.</p>}
        <fieldset className="wide">
          <legend>Object types to sync</legend>
          <label><input type="checkbox" checked={Boolean(form.sync_users_enabled)} onChange={e => set("sync_users_enabled", e.target.checked)} /> Users</label>
          <label><input type="checkbox" checked={Boolean(form.sync_computers_enabled)} onChange={e => set("sync_computers_enabled", e.target.checked)} /> Computers</label>
          <label><input type="checkbox" checked={Boolean(form.sync_groups_enabled)} onChange={e => set("sync_groups_enabled", e.target.checked)} /> Groups</label>
        </fieldset>
        <label>Default sync mode
          <select value={String(form.default_sync_mode ?? "incremental")} onChange={e => set("default_sync_mode", e.target.value)}>
            <option value="incremental">Incremental</option>
            <option value="full">Full</option>
          </select>
        </label>
        <label>Sync interval (minutes)
          <input type="number" min="5" max="10080" value={Number(form.sync_interval_minutes ?? 60)} onChange={e => set("sync_interval_minutes", Number(e.target.value))} />
        </label>
        <label><input type="checkbox" checked={Boolean(form.dry_run_default)} onChange={e => set("dry_run_default", e.target.checked)} /> Dry run by default</label>
        <label>Conflict policy
          <select value={String(form.conflict_policy ?? "flag")} onChange={e => set("conflict_policy", e.target.value)}>
            <option value="flag">Flag for review</option>
            <option value="skip">Skip object</option>
          </select>
        </label>
        <label>Maximum objects per sync
          <input type="number" min="1" max="100000" value={Number(form.maximum_objects_per_sync ?? 10000)} onChange={e => set("maximum_objects_per_sync", Number(e.target.value))} />
        </label>
        <label>Batch size
          <input type="number" min="10" max="2000" value={Number(form.batch_size ?? 500)} onChange={e => set("batch_size", Number(e.target.value))} />
        </label>
        <label>Missing grace period (hours)
          <input type="number" min="1" max="8760" value={Number(form.missing_object_grace_period_hours ?? 72)} onChange={e => set("missing_object_grace_period_hours", Number(e.target.value))} />
        </label>
        <label>Incremental overlap (minutes)
          <input type="number" min="0" max="1440" value={Number(form.incremental_overlap_minutes ?? 30)} onChange={e => set("incremental_overlap_minutes", Number(e.target.value))} />
        </label>
        <fieldset className="wide">
          <legend>Reconciliation defaults</legend>
          <label><input type="checkbox" checked={Boolean(form.auto_create_users)} onChange={e => set("auto_create_users", e.target.checked)} /> Allow new HIOP user creation from staged results</label>
          <label><input type="checkbox" checked={Boolean(form.auto_create_devices)} onChange={e => set("auto_create_devices", e.target.checked)} /> Allow new inventory device creation from staged results</label>
        </fieldset>
        <label className="wide" style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
          <input type="checkbox" checked={Boolean(form.enabled)} onChange={e => set("enabled", e.target.checked)} /> Sync configuration enabled
        </label>
        <footer className="wide">
          <button type="button" className="secondary-action" onClick={close}>Cancel</button>
          <button className="primary-action" disabled={busy}>{busy ? "Saving…" : "Save configuration"}</button>
        </footer>
      </form>
    </Modal>
  );
}

/* ─── Manual sync dialog ───────────────────────────────────────────────── */
function SyncDialog({ connection, close }: { connection: ADConnection; close: () => void }) {
  const config = useRequest(() => endpoints.adSyncConfig(connection.id), [connection.id]);
  const [mode, setMode] = useState<"full" | "incremental">("incremental");
  const [dry, setDry] = useState(true);
  const [types, setTypes] = useState({ user: true, computer: true, group: true });
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const toggleType = (t: "user" | "computer" | "group") => setTypes(p => ({ ...p, [t]: !p[t] }));
  const start = async () => {
    if (!dry && !window.confirm("This is a live sync. Directory changes will be staged. Proceed?")) return;
    setBusy(true);
    try {
      const object_types = (["user", "computer", "group"] as const).filter(t => types[t]);
      if (!object_types.length) { setError("Select at least one object type."); setBusy(false); return; }
      await endpoints.startADSync(connection.id, { sync_mode: mode, dry_run: dry, object_types });
      close();
    } catch (x) { setError(x instanceof Error ? x.message : "Sync failed"); } finally { setBusy(false); }
  };
  return (
    <Modal title={`Start sync · ${connection.name}`} onClose={close}>
      {config.loading ? <Feedback loading /> : (
        <div className="ad-form single">
          {error && <p role="alert" className="form-error">{error}</p>}
          <label>Mode
            <select value={mode} onChange={e => setMode(e.target.value as "full" | "incremental")}>
              <option value="incremental">Incremental</option>
              <option value="full">Full</option>
            </select>
          </label>
          <fieldset>
            <legend>Object types</legend>
            <label><input type="checkbox" checked={types.user} onChange={() => toggleType("user")} /> Users</label>
            <label><input type="checkbox" checked={types.computer} onChange={() => toggleType("computer")} /> Computers</label>
            <label><input type="checkbox" checked={types.group} onChange={() => toggleType("group")} /> Groups</label>
          </fieldset>
          <label style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
            <input type="checkbox" checked={dry} onChange={e => setDry(e.target.checked)} />
            Dry run (no staging mutations, projected counts only)
          </label>
          <div className="ad-warning">
            {mode === "full" ? "A full sync may take longer. Missing detection runs only after a complete, non-dry full sync." : "Incremental sync uses an overlap window from the last successful checkpoint."}
            {!dry && " Live sync: staged objects will be written to the database."}
          </div>
          <p style={{ color: "var(--muted)", fontSize: 13 }}>No HIOP user or device is created until you explicitly reconcile staged objects.</p>
          <footer>
            <button className="secondary-action" onClick={close}>Cancel</button>
            <button className="primary-action" disabled={busy || Boolean(config.error)} onClick={() => void start()}>
              {busy ? "Starting…" : "Confirm sync"}
            </button>
          </footer>
        </div>
      )}
    </Modal>
  );
}

/* ─── Sync runs ────────────────────────────────────────────────────────── */
function SyncRuns() {
  const [statusFilter, setStatusFilter] = useState("");
  const [modeFilter, setModeFilter] = useState("");
  const [dryFilter, setDryFilter] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 25;
  const [selected, setSelected] = useState<ADSyncRun | null>(null);

  const runs = useRequest(() => endpoints.adSyncRuns({
    status: statusFilter || undefined, sync_mode: modeFilter || undefined,
    dry_run: dryFilter === "" ? undefined : dryFilter,
    offset: (page - 1) * pageSize, page_size: pageSize,
  }), [statusFilter, modeFilter, dryFilter, page]);

  const handleWS = useCallback((event: string, _: unknown) => {
    if (["ad_sync_started", "ad_sync_progress", "ad_sync_completed", "ad_sync_failed"].includes(event))
      void runs.reload();
  }, [runs]);
  useADWebSocket(handleWS);

  // Poll while any run is active
  useEffect(() => {
    const active = runs.data?.items.some(r => r.status === "running" || r.status === "pending");
    if (!active) return;
    const id = window.setInterval(() => void runs.reload(), 5000);
    return () => clearInterval(id);
  }, [runs]);

  const cancel = async (run: ADSyncRun) => {
    try { await endpoints.cancelADSync(run.id); await runs.reload(); }
    catch (e) { alert(e instanceof Error ? e.message : "Cancel failed"); }
  };

  const total = runs.data?.total ?? 0;
  const pages = Math.ceil(total / pageSize);

  return <>
    <Toolbar title="Synchronisation runs" action={<button className="secondary-action" onClick={() => void runs.reload()}>Refresh</button>} />
    <div className="ad-filters">
      <label>Status
        <select value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(1); }}>
          <option value="">All</option>
          <option value="running">Running</option>
          <option value="completed">Completed</option>
          <option value="partial">Partial</option>
          <option value="failed">Failed</option>
        </select>
      </label>
      <label>Mode
        <select value={modeFilter} onChange={e => { setModeFilter(e.target.value); setPage(1); }}>
          <option value="">All</option>
          <option value="full">Full</option>
          <option value="incremental">Incremental</option>
        </select>
      </label>
      <label>Dry run
        <select value={dryFilter} onChange={e => { setDryFilter(e.target.value); setPage(1); }}>
          <option value="">All</option>
          <option value="true">Dry run only</option>
          <option value="false">Live only</option>
        </select>
      </label>
    </div>
    {runs.loading && !runs.data ? <Feedback loading /> :
      !runs.data?.items.length ? <Feedback empty="No synchronisation runs match." /> : (
        <div className="ad-table-wrap">
          <table className="ad-table">
            <thead><tr>
              <th>Status</th><th>Trigger</th><th>Mode</th>
              <th>Started</th><th>Completed</th><th>Duration</th>
              <th>Users</th><th>Computers</th><th>Groups</th>
              <th>Created</th><th>Updated</th><th>Missing</th><th>Errors</th><th>Actions</th>
            </tr></thead>
            <tbody>
              {runs.data!.items.map(r => (
                <tr key={r.id}>
                  <td><span className={stateClass(r.status)}>{r.status}</span></td>
                  <td>{r.trigger_type}</td>
                  <td>{r.sync_mode}{r.dry_run && <small>Dry</small>}</td>
                  <td>{fmt(r.started_at)}</td>
                  <td>{fmt(r.completed_at)}</td>
                  <td>{dur(r.duration_ms)}</td>
                  <td>{r.users_seen}</td>
                  <td>{r.computers_seen}</td>
                  <td>{r.groups_seen}</td>
                  <td>{r.created_objects}</td>
                  <td>{r.updated_objects}</td>
                  <td>{r.missing_objects}</td>
                  <td>{r.errors_count}{r.error_summary && <small>{r.error_summary}</small>}</td>
                  <td>
                    <div className="ad-actions">
                      <button onClick={() => setSelected(r)}>Details</button>
                      {(r.status === "running" || r.status === "pending") && (
                        <button onClick={() => void cancel(r)}>Cancel</button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    {pages > 1 && (
      <div className="ad-pagination">
        <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Previous</button>
        <span>Page {page} of {pages}</span>
        <button disabled={page >= pages} onClick={() => setPage(p => p + 1)}>Next</button>
      </div>
    )}
    {selected && <SyncRunDetail run={selected} close={() => setSelected(null)} />}
  </>;
}

/* ─── Sync run detail ──────────────────────────────────────────────────── */
function SyncRunDetail({ run, close }: { run: ADSyncRun; close: () => void }) {
  const detail = useRequest(() => endpoints.adSyncRun(run.id), [run.id]);
  const summary = useRequest(() => endpoints.adSyncSummary(run.id), [run.id]);
  const r = detail.data ?? run;
  const isActive = r.status === "running" || r.status === "pending";
  useEffect(() => {
    if (!isActive) return;
    const id = setInterval(() => void detail.reload(), 4000);
    return () => clearInterval(id);
  }, [isActive, detail]);
  return (
    <Modal title={`Sync run detail`} onClose={close}>
      <div aria-live="polite">
        <div className="ad-test-header">
          <span className={stateClass(r.status)}>{r.status}</span>
          {isActive && <small>Auto-refreshing…</small>}
          <small>{fmt(r.started_at)} — {fmt(r.completed_at)}</small>
          <small>{dur(r.duration_ms)}</small>
        </div>
        <dl className="ad-detail"><div>
          <div><dt>Trigger</dt><dd>{r.trigger_type}</dd></div>
          <div><dt>Mode</dt><dd>{r.sync_mode}{r.dry_run ? " (dry run)" : ""}</dd></div>
          <div><dt>Users seen</dt><dd>{r.users_seen}</dd></div>
          <div><dt>Computers seen</dt><dd>{r.computers_seen}</dd></div>
          <div><dt>Groups seen</dt><dd>{r.groups_seen}</dd></div>
          <div><dt>Created</dt><dd>{r.created_objects}</dd></div>
          <div><dt>Updated</dt><dd>{r.updated_objects}</dd></div>
          <div><dt>Missing</dt><dd>{r.missing_objects}</dd></div>
          <div><dt>Conflicts</dt><dd>{r.conflicts}</dd></div>
          <div><dt>Errors</dt><dd>{r.errors_count}</dd></div>
        </div></dl>
        {r.error_summary && <p className="ad-warning">{r.error_summary}</p>}
        {summary.data && (
          <details style={{ marginTop: 12 }}>
            <summary style={{ cursor: "pointer", fontWeight: 700 }}>Full summary</summary>
            <pre style={{ fontSize: 11, maxHeight: 300, overflow: "auto", whiteSpace: "pre-wrap" }}>
              {JSON.stringify(summary.data, null, 2)}
            </pre>
          </details>
        )}
        <footer style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}>
          <button className="primary-action" onClick={close}>Close</button>
        </footer>
      </div>
    </Modal>
  );
}

/* ─── Directory Objects ────────────────────────────────────────────────── */
function Objects() {
  const [type, setType] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [review, setReview] = useState("");
  const [missing, setMissing] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 50;
  const [selected, setSelected] = useState<ADObject | null>(null);

  const objects = useRequest(() => endpoints.adObjects({
    object_type: type || undefined, search: search || undefined,
    sync_status: status || undefined, review_status: review || undefined,
    is_missing: missing === "" ? undefined : missing,
    offset: (page - 1) * pageSize, page_size: pageSize,
  }), [type, search, status, review, missing, page]);

  const total = objects.data?.total ?? 0;
  const pages = Math.ceil(total / pageSize);

  return <>
    <Toolbar title="Directory objects" />
    <div className="ad-filters">
      <label>Type
        <select value={type} onChange={e => { setType(e.target.value); setPage(1); }}>
          <option value="">All</option>
          <option value="user">Users</option>
          <option value="computer">Computers</option>
          <option value="group">Groups</option>
        </select>
      </label>
      <label>Sync status
        <select value={status} onChange={e => { setStatus(e.target.value); setPage(1); }}>
          <option value="">All</option>
          <option value="created">Created</option>
          <option value="updated">Updated</option>
          <option value="unchanged">Unchanged</option>
          <option value="missing">Missing</option>
          <option value="restored">Restored</option>
        </select>
      </label>
      <label>Review status
        <select value={review} onChange={e => { setReview(e.target.value); setPage(1); }}>
          <option value="">All</option>
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="ignored">Ignored</option>
        </select>
      </label>
      <label>Missing
        <select value={missing} onChange={e => { setMissing(e.target.value); setPage(1); }}>
          <option value="">All</option>
          <option value="true">Missing only</option>
          <option value="false">Present only</option>
        </select>
      </label>
      <label>Search<input value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} placeholder="Username, hostname, email…" /></label>
    </div>
    {objects.loading && !objects.data ? <Feedback loading /> :
      !objects.data?.items.length ? <Feedback empty="No staged directory objects match." /> : (
        <div className="ad-table-wrap">
          <table className="ad-table">
            <thead><tr>
              <th>Identity</th><th>Type</th><th>Department / OS</th><th>OU</th>
              <th>Enabled</th><th>Sync status</th><th>Review</th><th>Last seen</th><th>Actions</th>
            </tr></thead>
            <tbody>
              {objects.data!.items.map(o => (
                <tr key={o.id}>
                  <td>
                    <strong>{o.display_name || o.dns_hostname || o.sam_account_name || "Unnamed"}</strong>
                    <small>{o.user_principal_name || o.email || ""}</small>
                  </td>
                  <td>{o.object_type}</td>
                  <td>{o.department || o.operating_system || "—"}<small>{o.job_title || o.operating_system_version || ""}</small></td>
                  <td><small>{o.organizational_unit || "—"}</small></td>
                  <td>{o.enabled == null ? "—" : o.enabled ? "Yes" : "No"}</td>
                  <td><span className={stateClass(o.sync_status)}>{o.sync_status}</span></td>
                  <td><span className={stateClass(o.review_status)}>{o.review_status}</span></td>
                  <td>{fmt(o.last_seen_at)}{o.missing_since && <small style={{ color: "var(--danger)" }}>Missing since {fmt(o.missing_since)}</small>}</td>
                  <td><button onClick={() => setSelected(o)}>View</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    {pages > 1 && (
      <div className="ad-pagination">
        <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Previous</button>
        <span>Page {page} of {pages} ({total})</span>
        <button disabled={page >= pages} onClick={() => setPage(p => p + 1)}>Next</button>
      </div>
    )}
    {selected && <ObjectDetail object={selected} close={() => setSelected(null)} />}
  </>;
}

/* ─── Object detail ────────────────────────────────────────────────────── */
function ObjectDetail({ object, close }: { object: ADObject; close: () => void }) {
  const changes = useRequest(() => endpoints.adObjectChanges(object.id), [object.id]);
  const plan = useRequest(() => endpoints.adReconciliationPlan(object.id), [object.id]);
  return (
    <Modal title={object.display_name || object.dns_hostname || object.sam_account_name || "Directory object"} onClose={close}>
      <div className="ad-detail">
        <dl><div>
          {[
            ["Type", object.object_type], ["Username / SAM", object.sam_account_name],
            ["UPN", object.user_principal_name], ["Display name", object.display_name],
            ["Email", object.email], ["DNS hostname", object.dns_hostname],
            ["Department", object.department], ["Job title", object.job_title],
            ["OS", object.operating_system], ["OS version", object.operating_system_version],
            ["OU", object.organizational_unit], ["Description", object.description],
            ["Enabled", object.enabled == null ? null : object.enabled ? "Yes" : "No"],
            ["Sync status", object.sync_status], ["Review status", object.review_status],
            ["First seen", fmt(object.first_seen_at)], ["Last seen", fmt(object.last_seen_at)],
            ["Missing since", object.missing_since ? fmt(object.missing_since) : null],
            ["Matched user ID", object.matched_user_id], ["Matched device ID", object.matched_device_id],
          ].map(([k, v]) => v != null ? <div key={String(k)}><dt>{k}</dt><dd>{String(v)}</dd></div> : null)}
        </div></dl>

        {plan.data && Object.keys(plan.data).length > 0 && (
          <>
            <h3 style={{ marginBottom: 6 }}>Reconciliation plan</h3>
            <pre style={{ fontSize: 11, maxHeight: 200, overflow: "auto", whiteSpace: "pre-wrap", border: "1px solid var(--line)", borderRadius: 8, padding: 10 }}>
              {JSON.stringify(plan.data, null, 2)}
            </pre>
          </>
        )}

        <h3 style={{ marginBottom: 6 }}>Change history</h3>
        {changes.loading ? <Feedback loading /> :
          !changes.data?.items.length ? <p style={{ color: "var(--muted)" }}>No changes recorded.</p> : (
            <ol className="ad-timeline">
              {(changes.data.items as ADChange[]).map(c => (
                <li key={c.id}>
                  <strong>{c.change_type}</strong>
                  <span>{c.changed_fields.join(", ") || "Identity staged"}</span>
                  {Object.keys(c.before_values ?? {}).length > 0 && (
                    <small>Before: {Object.entries(c.before_values).slice(0, 3).map(([k, v]) => `${k}: ${String(v)}`).join(", ")}</small>
                  )}
                  <small>{fmt(c.detected_at)}</small>
                </li>
              ))}
            </ol>
          )}
        <footer style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}>
          <button className="primary-action" onClick={close}>Close</button>
        </footer>
      </div>
    </Modal>
  );
}

/* ─── Matches ──────────────────────────────────────────────────────────── */
function Matches() {
  const connections = useRequest(() => endpoints.adConnections({ page_size: 100 }), []);
  const [levelFilter, setLevelFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("pending");
  const [page, setPage] = useState(1);
  const pageSize = 25;
  const [selected, setSelected] = useState<ADMatch | null>(null);
  const [notice, setNotice] = useState("");
  const [bulkRunning, setBulkRunning] = useState(false);

  const matches = useRequest(() => endpoints.adMatches({
    match_level: levelFilter || undefined, match_status: statusFilter || undefined,
    offset: (page - 1) * pageSize, page_size: pageSize,
  }), [levelFilter, statusFilter, page]);

  const handleWS = useCallback((event: string, _: unknown) => {
    if (["ad_match_run_completed", "ad_object_resolved"].includes(event)) void matches.reload();
  }, [matches]);
  useADWebSocket(handleWS);

  const recompute = async () => {
    const id = connections.data?.items[0]?.id;
    if (!id) { setNotice("Configure a connection first."); return; }
    setBulkRunning(true);
    try { await endpoints.runADMatching(id); setNotice("Matching completed."); await matches.reload(); }
    catch (e) { setNotice(e instanceof Error ? e.message : "Matching failed"); }
    finally { setBulkRunning(false); }
  };

  // Metrics summary
  const levelCounts: Record<string, number> = {};
  if (matches.data?.items) {
    for (const m of matches.data.items) {
      levelCounts[m.match_level] = (levelCounts[m.match_level] ?? 0) + 1;
    }
  }

  const total = matches.data?.total ?? 0;
  const pages = Math.ceil(total / pageSize);

  return <>
    {notice && <Toast message={notice} tone={notice.toLowerCase().includes("fail") ? "error" : "success"} />}
    <Toolbar title="Match and reconciliation"
      action={<button className="primary-action" disabled={bulkRunning} onClick={() => void recompute()}>
        {bulkRunning ? "Running…" : "Recompute matches"}
      </button>} />

    {Object.keys(levelCounts).length > 0 && (
      <div className="ad-match-metrics">
        {["exact", "strong", "probable", "weak"].map(l => (
          <div key={l} className={`ad-metric-pill state-${l}`}>{levelCounts[l] ?? 0} {l}</div>
        ))}
        <div className="ad-metric-pill">{matches.data?.total ?? 0} total</div>
      </div>
    )}

    <div className="ad-filters">
      <label>Match level
        <select value={levelFilter} onChange={e => { setLevelFilter(e.target.value); setPage(1); }}>
          <option value="">All</option>
          <option value="exact">Exact</option>
          <option value="strong">Strong</option>
          <option value="probable">Probable</option>
          <option value="weak">Weak</option>
        </select>
      </label>
      <label>Status
        <select value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(1); }}>
          <option value="">All</option>
          <option value="pending">Pending</option>
          <option value="resolved">Resolved</option>
          <option value="ignored">Ignored</option>
        </select>
      </label>
    </div>

    {matches.loading && !matches.data ? <Feedback loading /> :
      !matches.data?.items.length ? <Feedback empty="No match candidates match these filters." /> : (
        <div className="ad-table-wrap">
          <table className="ad-table">
            <thead><tr>
              <th>Type</th><th>Recommended action</th><th>Score</th>
              <th>Level</th><th>Conflicts</th><th>Status</th><th>Actions</th>
            </tr></thead>
            <tbody>
              {matches.data.items.map(m => (
                <tr key={m.id}>
                  <td>{m.candidate_type.replaceAll("_", " ")}</td>
                  <td>{m.recommended_action}</td>
                  <td><strong>{m.match_score.toFixed(0)}%</strong></td>
                  <td><span className={stateClass(m.match_level)}>{m.match_level}</span></td>
                  <td>{m.conflicting_fields.length}</td>
                  <td><span className={stateClass(m.match_status)}>{m.match_status}</span></td>
                  <td><button onClick={() => setSelected(m)}>Review</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    {pages > 1 && (
      <div className="ad-pagination">
        <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Previous</button>
        <span>Page {page} of {pages}</span>
        <button disabled={page >= pages} onClick={() => setPage(p => p + 1)}>Next</button>
      </div>
    )}
    {selected && (
      <MatchDialog match={selected} close={() => setSelected(null)} refreshed={() => matches.reload()} />
    )}
  </>;
}

/* ─── Match dialog (candidate comparison) ─────────────────────────────── */
function MatchDialog({ match, close, refreshed }: { match: ADMatch; close: () => void; refreshed: () => Promise<void> }) {
  const plan = useRequest(() => endpoints.adReconciliationPlan(match.directory_object_id), [match.directory_object_id]);
  const obj = useRequest(() => endpoints.adObject(match.directory_object_id), [match.directory_object_id]);
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const [action, setAction] = useState<"link_existing" | "ignore" | "">("");

  const execute = async () => {
    if (!action) return;
    const needsConfirm = action === "link_existing" && match.conflicting_fields.length === 0;
    if (needsConfirm && !window.confirm("Confirm: link this directory object to the candidate?")) return;
    setBusy(true);
    try {
      if (action === "ignore") await endpoints.ignoreADObject(match.directory_object_id);
      else await endpoints.resolveADObject(match.directory_object_id, { action, candidate_id: match.id, approved_fields: [], confirm: false });
      await refreshed(); close();
    } catch (e) { setError(e instanceof Error ? e.message : "Resolution failed"); } finally { setBusy(false); }
  };

  return (
    <Modal title="Candidate comparison and reconciliation" onClose={close}>
      {error && <p role="alert" className="form-error">{error}</p>}
      <div className="ad-compare">
        <section>
          <h3>Directory object</h3>
          {obj.loading ? <Feedback loading /> : obj.data ? (
            <dl style={{ fontSize: 13 }}>
              {[
                ["Type", obj.data.object_type], ["Username", obj.data.sam_account_name],
                ["Display name", obj.data.display_name], ["Email", obj.data.email],
                ["Department", obj.data.department], ["OU", obj.data.organizational_unit],
                ["Enabled", obj.data.enabled == null ? null : obj.data.enabled ? "Yes" : "No"],
                ["Sync status", obj.data.sync_status],
              ].map(([k, v]) => v != null ? <div key={String(k)} style={{ marginBottom: 4 }}><dt style={{ color: "var(--muted)", fontSize: 11 }}>{k}</dt><dd style={{ margin: 0 }}>{String(v)}</dd></div> : null)}
            </dl>
          ) : null}
          <h4>Evidence ({match.evidence.length} signals)</h4>
          <pre className="ad-evidence-pre">{JSON.stringify(match.evidence, null, 2)}</pre>
        </section>
        <section>
          <h3>Match candidate</h3>
          <dl style={{ fontSize: 13 }}>
            <div><dt style={{ color: "var(--muted)", fontSize: 11 }}>Candidate type</dt><dd>{match.candidate_type.replaceAll("_", " ")}</dd></div>
            <div><dt style={{ color: "var(--muted)", fontSize: 11 }}>Score</dt><dd><strong>{match.match_score.toFixed(0)}%</strong></dd></div>
            <div><dt style={{ color: "var(--muted)", fontSize: 11 }}>Level</dt><dd><span className={stateClass(match.match_level)}>{match.match_level}</span></dd></div>
            <div><dt style={{ color: "var(--muted)", fontSize: 11 }}>Recommended</dt><dd>{match.recommended_action}</dd></div>
          </dl>
          {match.conflicting_fields.length > 0 && (
            <div className="ad-warning">
              <strong>{match.conflicting_fields.length} conflict(s)</strong> — linking disabled until resolved.
              <pre className="ad-evidence-pre">{JSON.stringify(match.conflicting_fields, null, 2)}</pre>
            </div>
          )}
          <h4>Reconciliation plan</h4>
          {plan.loading ? <Feedback loading /> : <pre className="ad-evidence-pre">{JSON.stringify(plan.data, null, 2)}</pre>}
        </section>
      </div>
      <p className="ad-warning" style={{ marginTop: 12 }}>Privileged role changes and conflicting identifiers always require explicit backend approval. Weak matches are never auto-linked.</p>
      <footer>
        <select value={action} onChange={e => setAction(e.target.value as typeof action)} style={{ marginRight: "auto", border: "1px solid var(--line)", borderRadius: 8, padding: "8px 10px", background: "var(--surface)", color: "var(--text)" }}>
          <option value="">— Select action —</option>
          <option value="ignore">Ignore</option>
          <option value="link_existing" disabled={match.conflicting_fields.length > 0}>Link to candidate</option>
        </select>
        <button className="secondary-action" onClick={close}>Cancel</button>
        <button className="primary-action" disabled={busy || !action} onClick={() => void execute()}>
          {busy ? "Applying…" : "Apply action"}
        </button>
      </footer>
    </Modal>
  );
}

/* ─── Mappings ─────────────────────────────────────────────────────────── */
function Mappings() {
  const connections = useRequest(() => endpoints.adConnections({ page_size: 100 }), []);
  const [connection, setConnection] = useState("");
  const [kind, setKind] = useState<"departments" | "ous" | "roles">("departments");
  const [creating, setCreating] = useState(false);
  const [preview, setPreview] = useState<ADMapping | null>(null);
  const [notice, setNotice] = useState("");

  const mappings = useRequest(() => connection ? endpoints.adMappings(connection, kind) : Promise.resolve([]), [connection, kind]);

  useEffect(() => {
    if (!connection && connections.data?.items[0]) setConnection(connections.data.items[0].id);
  }, [connection, connections.data]);

  const remove = async (id: string) => {
    if (!window.confirm("Remove this mapping rule?")) return;
    try { await endpoints.deleteADMapping(connection, kind, id); await mappings.reload(); }
    catch (e) { setNotice(e instanceof Error ? e.message : "Remove failed"); }
  };

  return <>
    {notice && <Toast message={notice} tone="error" />}
    <Toolbar title="Mapping management" action={
      <button className="primary-action" disabled={!connection} onClick={() => setCreating(true)}>Add rule</button>
    } />
    <div className="ad-filters">
      <label>Connection
        <select value={connection} onChange={e => setConnection(e.target.value)}>
          {connections.data?.items.map(c => <option value={c.id} key={c.id}>{c.name}</option>)}
        </select>
      </label>
      <label>Mapping type
        <select value={kind} onChange={e => setKind(e.target.value as typeof kind)}>
          <option value="departments">Departments</option>
          <option value="ous">Organisational units</option>
          <option value="roles">Group roles</option>
        </select>
      </label>
    </div>
    {kind === "roles" && <p className="ad-warning">Group-role mappings that suggest the Administrator role require additional confirmation at reconciliation time. No role is granted automatically.</p>}
    {mappings.loading || mappings.error ? <Feedback loading={mappings.loading} error={mappings.error} onRetry={mappings.reload} /> :
      !mappings.data?.length ? <Feedback empty="No mapping rules configured for this connection and type." /> : (
        <div className="ad-table-wrap">
          <table className="ad-table">
            <thead><tr><th>Source</th><th>Pattern</th><th>Target</th><th>Priority</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>
              {(mappings.data as ADMapping[]).map(m => (
                <tr key={m.id}>
                  <td>{m.source_value || "—"}</td>
                  <td><code>{m.source_pattern || "—"}</code></td>
                  <td>{JSON.stringify(m.target_mapping ?? m.target_department_id ?? m.target_role_id ?? "—")}</td>
                  <td>{m.priority}</td>
                  <td><span className={stateClass(m.enabled ? "enabled" : "disabled")}>{m.enabled ? "enabled" : "disabled"}</span></td>
                  <td>
                    <div className="ad-actions">
                      <button onClick={() => setPreview(m)}>Preview</button>
                      <button onClick={() => void remove(m.id)}>Remove</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    <p className="ad-warning" style={{ marginTop: 12 }}>Mapping changes create suggestions only. They never silently create hierarchy records or grant Administrator access.</p>
    {creating && <MappingCreateDialog connectionId={connection} kind={kind} close={() => setCreating(false)} saved={() => { setCreating(false); void mappings.reload(); }} />}
    {preview && <MappingPreviewDialog connectionId={connection} kind={kind} mapping={preview} close={() => setPreview(null)} />}
  </>;
}

/* ─── Mapping create ───────────────────────────────────────────────────── */
function MappingCreateDialog({ connectionId, kind, close, saved }: { connectionId: string; kind: string; close: () => void; saved: () => void }) {
  const [sourceValue, setSourceValue] = useState("");
  const [sourcePattern, setSourcePattern] = useState("");
  const [targetValue, setTargetValue] = useState("");
  const [priority, setPriority] = useState(50);
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const isRole = kind === "roles";
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (isRole && targetValue.toLowerCase() === "admin") {
      if (!window.confirm("This mapping suggests the Administrator role. Extra confirmation is required at reconciliation time. Proceed to save the rule?")) return;
    }
    setBusy(true); setError("");
    try {
      await endpoints.createADMapping(connectionId, kind as "departments" | "ous" | "roles", {
        source_value: sourceValue || null,
        source_pattern: sourcePattern || null,
        target_mapping: { value: targetValue },
        priority,
        enabled: true,
      });
      saved();
    } catch (x) { setError(x instanceof Error ? x.message : "Create failed"); } finally { setBusy(false); }
  };
  return (
    <Modal title={`New ${kind} mapping`} onClose={close}>
      <form className="ad-form single" onSubmit={submit}>
        {error && <p className="form-error" role="alert">{error}</p>}
        <label>Source value (exact match)<input value={sourceValue} onChange={e => setSourceValue(e.target.value)} placeholder="e.g. IT Department" /></label>
        <label>Source pattern (glob for OUs)<input value={sourcePattern} onChange={e => setSourcePattern(e.target.value)} placeholder="e.g. *IT*" /></label>
        <label>Target {isRole ? "role" : "value"}<input required value={targetValue} onChange={e => setTargetValue(e.target.value)} placeholder={isRole ? "e.g. technician" : "e.g. Information Technology"} /></label>
        <label>Priority (lower = higher priority)<input type="number" min="0" max="999" value={priority} onChange={e => setPriority(Number(e.target.value))} /></label>
        {isRole && <p className="ad-warning">Privileged role mappings require extra administrator confirmation at reconciliation. No role is assigned automatically.</p>}
        <footer>
          <button type="button" className="secondary-action" onClick={close}>Cancel</button>
          <button className="primary-action" disabled={busy}>{busy ? "Saving…" : "Create rule"}</button>
        </footer>
      </form>
    </Modal>
  );
}

/* ─── Mapping preview ──────────────────────────────────────────────────── */
function MappingPreviewDialog({ connectionId, kind, mapping, close }: { connectionId: string; kind: string; mapping: ADMapping; close: () => void }) {
  const preview = useRequest(() => endpoints.previewADMapping(connectionId, kind, mapping.id), [connectionId, kind, mapping.id]);
  return (
    <Modal title="Mapping preview" onClose={close}>
      {preview.loading && <Feedback loading />}
      {preview.error && <Feedback error={preview.error} onRetry={preview.reload} />}
      {preview.data && <>
        <p><strong>{preview.data.total}</strong> objects would match this rule{preview.data.truncated ? " (truncated)" : ""}. Changes are <em>not</em> applied here.</p>
        {preview.data.items.length > 0 ? (
          <div className="ad-table-wrap">
            <table className="ad-table">
              <thead><tr><th>Type</th><th>Identity</th><th>Source value</th><th>Review status</th></tr></thead>
              <tbody>
                {preview.data.items.map((item: Record<string, unknown>, i: number) => (
                  <tr key={String(item.object_id ?? i)}>
                    <td>{String(item.object_type ?? "—")}</td>
                    <td>{String(item.identity ?? "—")}</td>
                    <td>{String(item.source ?? "—")}</td>
                    <td>{String(item.review_status ?? "—")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <Feedback empty="No objects currently match this rule." />}
      </>}
      <footer style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}>
        <button className="primary-action" onClick={close}>Close</button>
      </footer>
    </Modal>
  );
}

/* ─── Review queue ─────────────────────────────────────────────────────── */
function ReviewQueue() {
  const [typeFilter, setTypeFilter] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 25;
  const [notice, setNotice] = useState("");

  const queue = useRequest(() => endpoints.adReviewQueue({
    object_type: typeFilter || undefined,
    offset: (page - 1) * pageSize, page_size: pageSize,
  }), [typeFilter, page]);

  const handleWS = useCallback((_: string, __: unknown) => void queue.reload(), [queue]);
  useADWebSocket(handleWS);

  const act = async (id: string, _action: "ignore") => {
    try { await endpoints.ignoreADObject(id); await queue.reload(); }
    catch (e) { setNotice(e instanceof Error ? e.message : "Action failed"); }
  };

  const total = queue.data?.total ?? 0;
  const pages = Math.ceil(total / pageSize);

  return <>
    {notice && <Toast message={notice} tone="error" />}
    <Toolbar title="Missing and disabled review" />
    <div className="ad-filters">
      <label>Type
        <select value={typeFilter} onChange={e => { setTypeFilter(e.target.value); setPage(1); }}>
          <option value="">All</option>
          <option value="user">Users</option>
          <option value="computer">Computers</option>
          <option value="group">Groups</option>
        </select>
      </label>
    </div>
    {queue.loading && !queue.data ? <Feedback loading /> :
      !queue.data?.items.length ? <Feedback empty="No missing, disabled, or conflicted objects require review." /> : (
        <div className="ad-table-wrap">
          <table className="ad-table">
            <thead><tr>
              <th>Identity</th><th>Type</th><th>Status</th><th>Recommendation</th>
              <th>Open tickets</th><th>Alerts</th><th>Last seen</th><th>HIOP record</th><th>Actions</th>
            </tr></thead>
            <tbody>
              {queue.data.items.map((item: Record<string, unknown>, i: number) => (
                <tr key={String(item.id ?? i)}>
                  <td>
                    <strong>{String(item.display_name ?? item.dns_hostname ?? item.sam_account_name ?? "Object")}</strong>
                    {Boolean(item.user_role) && <small>Role: {String(item.user_role)}</small>}
                  </td>
                  <td>{String(item.object_type ?? "—")}</td>
                  <td><span className={stateClass(String(item.sync_status ?? "review"))}>{String(item.sync_status ?? "review")}</span></td>
                  <td>{String(item.recommendation ?? "Review required")}</td>
                  <td>{String(item.open_tickets ?? 0)}</td>
                  <td>{String(item.open_alerts ?? 0)}</td>
                  <td>{item.last_seen_at ? fmt(String(item.last_seen_at)) : "—"}</td>
                  <td>{item.user_id ? <small>User linked</small> : item.device_id ? <small>Device linked</small> : "None"}</td>
                  <td>
                    <div className="ad-actions">
                      <button onClick={() => void act(String(item.id), "ignore")}>Ignore</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    <p className="ad-warning" style={{ marginTop: 12 }}>HIOP users are never disabled and devices are never retired automatically. Last-administrator and active-work safeguards are enforced by the backend.</p>
    {pages > 1 && (
      <div className="ad-pagination">
        <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Previous</button>
        <span>Page {page} of {pages}</span>
        <button disabled={page >= pages} onClick={() => setPage(p => p + 1)}>Next</button>
      </div>
    )}
  </>;
}

/* ─── Reports ──────────────────────────────────────────────────────────── */
function Reports() {
  const overview = useRequest(endpoints.adOverview, []);
  const d = overview.data;
  return (
    <div className="ad-overview-grid">
      <Panel title="Connection and sync health">
        {d && <dl className="ad-kv">
          <div><dt>Configured connections</dt><dd>{d.configured_connections}</dd></div>
          <div><dt>Healthy connections</dt><dd>{d.healthy_connections}</dd></div>
          <div><dt>Failed tests</dt><dd>{d.failed_connection_tests}</dd></div>
          <div><dt>Scheduled syncs</dt><dd>{d.scheduled_syncs}</dd></div>
          <div><dt>Last successful sync</dt><dd>{fmt(d.last_successful_sync)}</dd></div>
        </dl>}
        <Link to="/active-directory/sync-runs" className="ad-link">View sync history →</Link>
      </Panel>
      <Panel title="Staged objects">
        {d && <dl className="ad-kv">
          <div><dt>Users staged</dt><dd>{d.staged.users}</dd></div>
          <div><dt>Computers staged</dt><dd>{d.staged.computers}</dd></div>
          <div><dt>Groups staged</dt><dd>{d.staged.groups}</dd></div>
          <div><dt>Missing objects</dt><dd>{d.missing_objects}</dd></div>
        </dl>}
        <Link to="/active-directory/objects" className="ad-link">Browse directory objects →</Link>
      </Panel>
      <Panel title="Reconciliation">
        {d && <dl className="ad-kv">
          <div><dt>Pending matches</dt><dd>{d.pending_matches}</dd></div>
          <div><dt>Conflicts</dt><dd>{d.conflicts}</dd></div>
        </dl>}
        <Link to="/active-directory/matches" className="ad-link">Open reconciliation workspace →</Link>
      </Panel>
      <Panel title="Export and audit">
        <p>AD audit events are recorded in the HIOP audit trail and accessible from the Audit Center. Exports follow HIOP authorisation, pagination, and CSV formula-injection controls.</p>
        <Link to="/audit" className="ad-link">Open audit trail →</Link>
        <Link to="/reports" className="ad-link">Open report center →</Link>
      </Panel>
    </div>
  );
}

/* ─── shared helpers ───────────────────────────────────────────────────── */
function Toolbar({ title, action }: { title: string; action?: ReactNode }) {
  return <div className="ad-toolbar"><h2>{title}</h2>{action}</div>;
}
function Panel({ title, children, wide }: { title: string; children: ReactNode; wide?: boolean }) {
  return (
    <section className={`panel ad-panel${wide ? " ad-panel-wide" : ""}`}>
      <h2>{title}</h2>{children}
    </section>
  );
}
