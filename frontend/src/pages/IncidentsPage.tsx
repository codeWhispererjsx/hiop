import { useDeferredValue, useMemo, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { Feedback } from "../components/Feedback";
import { StatusBadge } from "../components/StatusBadge";
import { StatCard } from "../components/StatCard";
import { PageTitle } from "./DashboardPage";
import { Icon } from "../components/Icon";
import { endpoints, getPaginatedItems } from "../lib/api";
import { useRequest } from "../hooks/useRequest";

const CATEGORIES = [
  "network",
  "hardware",
  "software",
  "pos",
  "pms",
  "wifi",
  "printer",
  "security_system",
  "telephony",
  "other",
];

const title = (value: string) =>
  value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (x) => x.toUpperCase());

const duration = (seconds: number | null) =>
  seconds === null
    ? "Not available"
    : seconds < 60
    ? `${seconds}s`
    : seconds < 3600
    ? `${Math.round(seconds / 60)}m`
    : `${(seconds / 3600).toFixed(1)}h`;

export default function IncidentsPage() {
  const location = useLocation();
  const { id, serviceId } = useParams();

  if (location.pathname.startsWith("/incidents/services")) {
    return <ServicesWorkspace id={serviceId} />;
  }
  if (location.pathname === "/incidents/new") {
    return <IncidentForm />;
  }
  if (id) {
    return <IncidentDetails id={id} />;
  }
  return <IncidentList />;
}

function WorkspaceLinks() {
  const { id } = useParams();
  const related = useRequest(
    () => (id ? endpoints.incidentProblems(id) : Promise.resolve([])),
    [id]
  );
  const me = useRequest(endpoints.me, []);

  return (
    <nav className="page-actions" aria-label="Maintain workspaces">
      <Link className="secondary-action" to="/incidents">
        Incidents
      </Link>
      <Link className="secondary-action" to="/problems">
        Problems
      </Link>
      <Link className="secondary-action" to="/problems?status=known_error">
        Known Errors
      </Link>
      <Link className="secondary-action" to="/changes">
        Changes
      </Link>
      <Link className="secondary-action" to="/knowledge">
        Knowledge
      </Link>
      <Link className="secondary-action" to="/incidents/services">
        Services
      </Link>
      {id &&
        related.data?.map((problem) => (
          <Link
            key={problem.id}
            className="secondary-action"
            to={`/problems/${problem.id}`}
          >
            Related {problem.problem_number}
          </Link>
        ))}
      {id && me.data?.role === "admin" && (
        <Link
          className="primary-action"
          to={`/problems/new?incident=${id}`}
        >
          Create Problem
        </Link>
      )}
    </nav>
  );
}

function IncidentList() {
  const rows = useRequest(() => endpoints.serviceIncidents(), []);
  const summary = useRequest(endpoints.serviceManagementSummary, []);
  const me = useRequest(endpoints.me, []);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [priority, setPriority] = useState("all");

  const q = useDeferredValue(search).toLowerCase();

  const filtered = useMemo(
    () =>
      getPaginatedItems(rows.data).filter(
        (x) =>
          (!q ||
            [
              x.incident_number,
              x.title,
              x.description,
              x.asset?.asset_number,
              x.asset?.asset_tag,
              x.service_name,
              x.assigned_technician,
            ].some((v) => v?.toLowerCase().includes(q))) &&
          (status === "all" || x.status === status) &&
          (priority === "all" || x.priority === priority)
      ),
    [rows.data, q, status, priority]
  );

  const paginatedRows = getPaginatedItems(rows.data);

  return (
    <DashboardLayout>
      <WorkspaceLinks />
      <PageTitle
        eyebrow="Maintain · incidents"
        title="Service & incident management"
        copy="Track operational responsibility, business service impact, investigation, and resolution."
        action={
          me.data?.role !== "viewer" ? (
            <Link className="primary-action" to="/incidents/new">
              Create Incident
            </Link>
          ) : undefined
        }
      />

      {summary.data && (
        <section className="stats-grid" aria-label="Incident statistics">
          <StatCard
            label="Open incidents"
            value={summary.data.open}
            detail={`${summary.data.critical} critical`}
            icon="alerts"
            tone={summary.data.critical ? "danger" : "neutral"}
          />
          <StatCard
            label="Unassigned"
            value={summary.data.unassigned}
            detail="Require ownership"
            icon="users"
          />
          <StatCard
            label="In progress"
            value={summary.data.in_progress}
            detail={`${summary.data.on_hold} on hold`}
            icon="audit"
          />
          <StatCard
            label="Resolved today"
            value={summary.data.resolved_today}
            detail={`Average ${duration(summary.data.average_resolution_seconds)}`}
            icon="check"
            tone="success"
          />
        </section>
      )}

      <section className="toolbar-panel" aria-label="Search and filter incidents">
        <label htmlFor="incident-search" className="search-field">
          <Icon name="search" aria-hidden="true" />
          <input
            id="incident-search"
            type="search"
            aria-label="Search incidents"
            placeholder="Incident, hostname, IP, asset, service, technician"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <div className="filter-row">
          <select
            aria-label="Filter by status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="all">All statuses</option>
            {["new", "acknowledged", "in_progress", "on_hold", "resolved", "closed"].map(
              (x) => (
                <option key={x} value={x}>
                  {title(x)}
                </option>
              )
            )}
          </select>
          <select
            aria-label="Filter by priority"
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
          >
            <option value="all">All priorities</option>
            {["low", "medium", "high", "critical"].map((x) => (
              <option key={x} value={x}>
                {title(x)}
              </option>
            ))}
          </select>
        </div>
      </section>

      {rows.loading || rows.error ? (
        <Feedback loading={rows.loading} error={rows.error} />
      ) : !paginatedRows.length ? (
        <Feedback
          emptyTitle="No incidents found"
          empty="Adjust filters or create your first incident."
        />
      ) : (
        <section className="data-panel" aria-label="Incident list">
          <div className="data-table incident-table">
            <div className="table-row table-head" role="row">
              <span>Incident</span>
              <span>Details</span>
              <span>Assignment</span>
              <span>Service</span>
              <span>Priority</span>
              <span>Status</span>
              <span>Created</span>
            </div>
            {filtered.map((row) => (
              <Link
                className="table-row"
                role="row"
                key={row.id}
                to={`/incidents/${row.id}`}
              >
                <span className="primary-cell">
                  <strong>{row.incident_number}</strong>
                  <small>{row.title}</small>
                </span>
                <span>
                  <strong>{row.description || "No description"}</strong>
                </span>
                <span>
                  <strong>{row.assigned_technician || "Unassigned"}</strong>
                  <small>{row.assigned_team || "No team"}</small>
                </span>
                <span>
                  <strong>{row.service_name || "No service"}</strong>
                </span>
                <span>
                  <StatusBadge status={row.priority} />
                </span>
                <span>
                  <StatusBadge status={row.status} />
                </span>
                <span>{new Date(row.created_at).toLocaleDateString()}</span>
              </Link>
            ))}
          </div>
        </section>
      )}
    </DashboardLayout>
  );
}

function IncidentForm() {
  const nav = useNavigate();
  const hierarchy = useRequest(endpoints.hierarchy, []);
  const assets = useRequest(() => endpoints.assets({}), []);
  const services = useRequest(() => endpoints.technologyServices(), []);
  const users = useRequest(endpoints.users, []);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const property =
    hierarchy.data?.properties.find((x) => x.is_active)?.id ??
    hierarchy.data?.properties[0]?.id ??
    "";

  const [form, setForm] = useState({
    title: "",
    description: "",
    priority: "medium",
    severity: "medium",
    category: "other",
    assigned_team: "",
    assigned_technician_id: "",
    asset_id: "",
    service_id: "",
  });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const row = await endpoints.createServiceIncident({
        ...form,
        property_id: property,
        assigned_team: form.assigned_team || null,
        assigned_technician_id: form.assigned_technician_id || null,
        asset_id: form.asset_id || null,
        service_id: form.service_id || null,
      });
      nav(`/incidents/${row.id}`);
    } catch (x) {
      setError(x instanceof Error ? x.message : "Incident could not be created");
    } finally {
      setBusy(false);
    }
  };

  return (
    <DashboardLayout>
      <WorkspaceLinks />
      <PageTitle
        eyebrow="Maintain · incidents"
        title="Create incident"
        copy="Create a managed work item; alerts remain separate evidence."
      />
      {error && <Feedback error={error} />}
      <form className="panel enterprise-form" onSubmit={(e) => void submit(e)}>
        <div className="form-grid">
          <label htmlFor="incident-title">
            Title
            <input
              id="incident-title"
              required
              minLength={3}
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
            />
          </label>
          <label htmlFor="incident-category">
            Category
            <select
              id="incident-category"
              value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
            >
              {CATEGORIES.map((x) => (
                <option key={x} value={x}>
                  {title(x)}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor="incident-priority">
            Priority
            <select
              id="incident-priority"
              value={form.priority}
              onChange={(e) => setForm({ ...form, priority: e.target.value })}
            >
              {["low", "medium", "high", "critical"].map((x) => (
                <option key={x} value={x}>
                  {x}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor="incident-severity">
            Severity
            <select
              id="incident-severity"
              value={form.severity}
              onChange={(e) => setForm({ ...form, severity: e.target.value })}
            >
              {["low", "medium", "high", "critical"].map((x) => (
                <option key={x} value={x}>
                  {x}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor="incident-team">
            Assigned team
            <input
              id="incident-team"
              value={form.assigned_team}
              onChange={(e) => setForm({ ...form, assigned_team: e.target.value })}
            />
          </label>
          <label htmlFor="incident-technician">
            Assigned technician
            <select
              id="incident-technician"
              value={form.assigned_technician_id}
              onChange={(e) => setForm({ ...form, assigned_technician_id: e.target.value })}
            >
              <option value="">Select technician</option>
              {users.data?.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.username}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor="incident-asset">
            Related asset
            <select
              id="incident-asset"
              value={form.asset_id}
              onChange={(e) => setForm({ ...form, asset_id: e.target.value })}
            >
              <option value="">Select asset</option>
              {assets.data?.map((asset) => (
                <option key={asset.id} value={asset.id}>
                  {asset.asset_number} · {asset.name}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor="incident-service">
            Related service
            <select
              id="incident-service"
              value={form.service_id}
              onChange={(e) => setForm({ ...form, service_id: e.target.value })}
            >
              <option value="">Select service</option>
              {services.data?.map((service) => (
                <option key={service.id} value={service.id}>
                  {service.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label htmlFor="incident-description">
          Description
          <textarea
            id="incident-description"
            rows={4}
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="Describe the incident and its impact"
          />
        </label>
        <div className="row-actions">
          <button type="button" className="secondary-action" onClick={() => nav("/incidents")}>
            Cancel
          </button>
          <button type="submit" className="primary-action" disabled={busy} aria-busy={busy}>
            {busy ? "Creating…" : "Create incident"}
          </button>
        </div>
      </form>
    </DashboardLayout>
  );
}

function IncidentDetails({ id }: { id: string }) {
  const request = useRequest(() => endpoints.serviceIncident(id), [id]);
  const me = useRequest(endpoints.me, []);
  const users = useRequest(endpoints.users, []);

  const [note, setNote] = useState("");
  const [resolution, setResolution] = useState("");
  const [closure, setClosure] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const row = request.data;
  const operate = me.data?.role !== "viewer";

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
      await request.reload();
    } catch (x) {
      setError(x instanceof Error ? x.message : "Action failed");
    } finally {
      setBusy(false);
    }
  };

  const transition = (
    target: string,
    body: Record<string, unknown> = {}
  ) => run(() => endpoints.transitionServiceIncident(id, target, body));

  if (request.loading || request.error || !row) {
    return (
      <DashboardLayout>
        <Feedback loading={request.loading} error={request.error} />
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <WorkspaceLinks />
      <PageTitle
        eyebrow={row.incident_number}
        title={row.title}
        copy={`${title(row.category)} · Created ${new Date(row.created_at).toLocaleString()}`}
        action={
          <Link className="secondary-action" to="/incidents">
            Back to Incidents
          </Link>
        }
      />
      {error && <Feedback error={error} />}
      <section className="incident-detail-grid">
        <article className="panel">
          <header className="section-head">
            <div>
              <h2>Current state</h2>
              <p>{row.description || "No description supplied."}</p>
            </div>
            <StatusBadge status={row.status} />
          </header>
          <dl className="detail-grid">
            <Dt label="Priority" value={title(row.priority)} />
            <Dt label="Severity" value={title(row.severity)} />
            <Dt label="Assigned team" value={row.assigned_team} />
            <Dt label="Technician" value={row.assigned_technician} />
            <Dt label="Service" value={row.service_name} />
            <Dt label="Source alert" value={row.source_alert_id} />
            <Dt
              label="Time to acknowledge"
              value={duration(row.time_to_acknowledge_seconds)}
            />
            <Dt
              label="Time to resolve"
              value={duration(row.time_to_resolve_seconds)}
            />
          </dl>
          {operate && (
            <div className="incident-actions">
              {row.status === "new" && (
                <button onClick={() => void transition("acknowledged")}>
                  Acknowledge
                </button>
              )}
              {["acknowledged", "on_hold"].includes(row.status) && (
                <button onClick={() => void transition("in_progress")}>
                  Start work
                </button>
              )}
              {row.status === "in_progress" && (
                <button onClick={() => void transition("on_hold")}>
                  Pause work
                </button>
              )}
              {["new", "acknowledged", "in_progress", "on_hold"].includes(
                row.status
              ) && (
                <button onClick={() => void transition("resolved")}>
                  Resolve
                </button>
              )}
              {row.status === "resolved" && (
                <button onClick={() => void transition("closed")}>
                  Close
                </button>
              )}
            </div>
          )}
        </article>

        <article className="panel">
          <header className="section-head">
            <h2>Resolution details</h2>
          </header>
          <dl className="detail-grid">
            <Dt label="Resolution reason" value={row.resolution_reason} />
            <Dt label="Resolved by" value={row.resolved_by} />
            <Dt
              label="Resolved at"
              value={
                row.resolved_at
                  ? new Date(row.resolved_at).toLocaleString()
                  : "Not resolved"
              }
            />
          </dl>
        </article>

        <article className="panel">
          <header className="section-head">
            <h2>Add note</h2>
          </header>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              if (!note.trim()) return;
              await run(() => endpoints.addServiceIncidentNote(id, note));
              setNote("");
            }}
          >
            <label htmlFor="incident-note">
              Note
              <textarea
                id="incident-note"
                rows={3}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Add an operational note"
              />
            </label>
            <div className="row-actions">
              <button type="submit" className="primary-action" disabled={busy || !note.trim()}>
                Add note
              </button>
            </div>
          </form>
        </article>

        <article className="panel">
          <header className="section-head">
            <h2>Incident notes</h2>
          </header>
          <div className="detail-notes">
            {row.notes?.length ? (
              row.notes.map((note) => (
                <article key={note.id}>
                  <time>{new Date(note.created_at).toLocaleString()}</time>
                  <strong>{note.created_by}</strong>
                  <p>{note.content}</p>
                </article>
              ))
            ) : (
              <p>No notes have been recorded yet.</p>
            )}
          </div>
        </article>
      </section>
    </DashboardLayout>
  );
}

function ServicesWorkspace({ id }: { id?: string }) {
  return id ? <ServiceDetails id={id} /> : <ServiceList />;
}

function ServiceList() {
  const rows = useRequest(() => endpoints.technologyServices(), []);
  const me = useRequest(endpoints.me, []);
  const [creating, setCreating] = useState(false);

  return (
    <DashboardLayout>
      <WorkspaceLinks />
      <PageTitle
        eyebrow="Maintain · services"
        title="Technology services"
        copy="Operational business context for assets, devices, and incidents."
        action={
          me.data?.role === "admin" ? (
            <button
              className="primary-action"
              onClick={() => setCreating(true)}
              aria-label="Add new technology service"
            >
              Add Service
            </button>
          ) : undefined
        }
      />

      {rows.loading || rows.error ? (
        <Feedback loading={rows.loading} error={rows.error} />
      ) : !rows.data?.length ? (
        <Feedback
          emptyTitle="No technology services configured yet."
          empty="Create a service to connect operational incidents with business context."
        />
      ) : (
        <section className="service-grid">
          {rows.data.map((row) => (
            <Link
              to={`/incidents/services/${row.id}`}
              className="panel service-card"
              key={row.id}
            >
              <div>
                <strong>{row.name}</strong>
                <StatusBadge status={row.status} />
              </div>
              <p>{row.description || "No description"}</p>
              <small>
                {row.asset_count} assets · {row.device_count} devices ·{" "}
                {row.open_incidents} open incidents
              </small>
            </Link>
          ))}
        </section>
      )}

      {creating && (
        <ServiceForm
          close={() => setCreating(false)}
          saved={async () => {
            setCreating(false);
            await rows.reload();
          }}
        />
      )}
    </DashboardLayout>
  );
}

function ServiceDetails({ id }: { id: string }) {
  const row = useRequest(() => endpoints.technologyService(id), [id]);
  const assets = useRequest(() => endpoints.assets({}), []);
  const me = useRequest(endpoints.me, []);
  const [assetId, setAssetId] = useState("");

  if (row.loading || row.error || !row.data) {
    return (
      <DashboardLayout>
        <Feedback loading={row.loading} error={row.error} />
      </DashboardLayout>
    );
  }

  const value = row.data;

  return (
    <DashboardLayout>
      <WorkspaceLinks />
      <PageTitle
        eyebrow={value.service_id}
        title={value.name}
        copy={value.description || "Technology service"}
        action={
          <Link className="secondary-action" to="/incidents/services">
            Back to Services
          </Link>
        }
      />

      <section className="panel">
        <header className="section-head">
          <div>
            <h2>Service health</h2>
            <p>Health remains unknown unless supported evidence establishes a state.</p>
          </div>
          <StatusBadge status={value.status} />
        </header>
        <dl className="detail-grid">
          <Dt label="Criticality" value={title(value.criticality)} />
          <Dt label="Owner / team" value={value.owner_team} />
          <Dt label="Assets" value={String(value.asset_count)} />
          <Dt label="Devices" value={String(value.device_count)} />
          <Dt label="Open incidents" value={String(value.open_incidents)} />
          <Dt label="Notes" value={value.notes} />
        </dl>
      </section>

      <section className="panel">
        <h2>Related assets</h2>
        {value.assets?.length ? (
          <div className="linked-list">
            {value.assets.map((x) => (
              <Link key={x.id} to={`/assets/${x.id}`}>
                <strong>{x.asset_number}</strong> {x.name}
              </Link>
            ))}
          </div>
        ) : (
          <Feedback empty="No assets associated." />
        )}
        {me.data?.role === "admin" && (
          <div className="inline-editor">
            <select
              aria-label="Associate asset"
              value={assetId}
              onChange={(e) => setAssetId(e.target.value)}
            >
              <option value="">Select asset</option>
              {assets.data
                ?.filter(
                  (x) => !value.assets?.some((y) => y.id === x.id)
                ).map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.asset_number} · {x.name}
                  </option>
                ))}
            </select>
            <button
              disabled={!assetId}
              onClick={() =>
                void endpoints
                  .linkTechnologyServiceAsset(id, assetId)
                  .then(() => row.reload())
              }
            >
              Link Asset
            </button>
          </div>
        )}
      </section>

      <section className="panel">
        <h2>Related incidents</h2>
        {value.incidents?.length ? (
          <div className="linked-list">
            {value.incidents.map((incident) => (
              <Link key={incident.id} to={`/incidents/${incident.id}`}>
                <strong>{incident.incident_number}</strong>
                <small>{incident.title}</small>
              </Link>
            ))}
          </div>
        ) : (
          <Feedback empty="No incidents associated." />
        )}
      </section>
    </DashboardLayout>
  );
}

function ServiceForm({
  close,
  saved,
}: {
  close: () => void;
  saved: () => Promise<void>;
}) {
  const hierarchy = useRequest(endpoints.hierarchy, []);
  const [form, setForm] = useState({
    name: "",
    code: "",
    description: "",
    status: "unknown",
    criticality: "medium",
    owner_team: "",
    notes: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const property =
    hierarchy.data?.properties.find((x) => x.is_active)?.id ??
    hierarchy.data?.properties[0]?.id ??
    "";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await endpoints.createTechnologyService({
        ...form,
        property_id: property,
        owner_team: form.owner_team || null,
      });
      await saved();
    } catch (x) {
      setError(x instanceof Error ? x.message : "Service could not be created");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop">
      <form
        className="modal-card enterprise-form"
        onSubmit={(e) => void submit(e)}
      >
        <h2>Add technology service</h2>
        {error && <Feedback error={error} />}
        <div className="form-grid">
          <label htmlFor="service-name">
            Name
            <input
              id="service-name"
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </label>
          <label htmlFor="service-code">
            Code
            <input
              id="service-code"
              required
              pattern="[A-Za-z0-9_-]{2,50}"
              value={form.code}
              onChange={(e) => setForm({ ...form, code: e.target.value })}
            />
          </label>
          <label htmlFor="service-status">
            Status
            <select
              id="service-status"
              value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value })}
            >
              {["operational", "degraded", "outage", "unknown"].map((x) => (
              <option key={x} value={x}>
                {x}
              </option>
            ))}
            </select>
          </label>
          <label htmlFor="service-criticality">
            Criticality
            <select
              id="service-criticality"
              value={form.criticality}
              onChange={(e) => setForm({ ...form, criticality: e.target.value })}
            >
              {["low", "medium", "high", "critical"].map((x) => (
                <option key={x} value={x}>
                  {x}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor="service-team">
            Owner / responsible team
            <input
              id="service-team"
              value={form.owner_team}
              onChange={(e) => setForm({ ...form, owner_team: e.target.value })}
            />
          </label>
        </div>
        <label htmlFor="service-description">
          Description
          <textarea
            id="service-description"
            rows={3}
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </label>
        <label htmlFor="service-notes">
          Notes
          <textarea
            id="service-notes"
            rows={2}
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
          />
        </label>
        <div className="row-actions">
          <button type="button" onClick={close}>
            Cancel
          </button>
          <button type="submit" className="primary-action" disabled={busy} aria-busy={busy}>
            {busy ? "Creating…" : "Create service"}
          </button>
        </div>
      </form>
    </div>
  );
}

function Dt({ label, v }: { label: string; v: string | null | undefined }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{v || "Not available"}</dd>
    </div>
  );
}

// Retained as an exported V1 compatibility surface for consumers that embed the
// original compact incident context while V4E uses the richer detail workspace.
export function IncidentCompatibilityContext({
  incidentId,
  relatedDevice,
  canOperate,
}: {
  incidentId: string;
  relatedDevice: {
    id: string;
    hostname: string;
    ip_address: string;
    network_status: string | null;
  };
  canOperate: boolean;
}) {
  const propertyId = localStorage.getItem("hiop.active_property_id");
  void propertyId;

  return (
    <section aria-label="Related device">
      <h2>Related device</h2>
      {relatedDevice && (
        <dl>
          <Dt label="IP address" v={relatedDevice.ip_address} />
          <Dt label="Network status" v={relatedDevice.network_status} />
          <Link to={`/devices/${relatedDevice.id}`}>
            {relatedDevice.hostname}
          </Link>
        </dl>
      )}
      <h2>Email notification</h2>
      <button
        onClick={() => void endpoints.sendIncidentEmail(incidentId, "")}
        aria-label="Send email update for this incident"
      >
        Send email update
      </button>
      {canOperate ? (
        <button onClick={() => undefined}>Create incident</button>
      ) : (
        <p>Viewer access is read-only.</p>
      )}
    </section>
  );
}