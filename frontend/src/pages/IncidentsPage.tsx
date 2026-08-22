import { useDeferredValue, useMemo, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
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
        Tickets
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

  return (
    <DashboardLayout>
      <WorkspaceLinks />
      <PageTitle
        eyebrow="Maintain · service desk"
        title="Tickets & incidents"
        copy="Create, assign, investigate, and resolve operational work from one service desk queue."
        action={
          me.data?.role !== "viewer" ? (
            <Link className="primary-action" to="/incidents/new">
              Create Ticket
            </Link>
          ) : undefined
        }
      />

      {summary.data && (
        <section className="stats-grid" aria-label="Incident statistics">
          <StatCard
            label="Open tickets"
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

      <section className="toolbar-panel" aria-label="Search and filter tickets">
        <label htmlFor="incident-search" className="search-field">
          <Icon name="search" aria-hidden="true" />
          <input
            id="incident-search"
            type="search"
            aria-label="Search tickets"
            placeholder="Ticket ID, hostname, IP, asset, service, technician"
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
      ) : !filtered.length ? (
        <Feedback
          emptyTitle="No tickets found"
          empty="Adjust the filters or create your first service ticket."
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
  const [searchParams] = useSearchParams();
  const sourceAlertId = searchParams.get("alert");
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
    title: searchParams.get("title") ?? "",
    description: searchParams.get("description") ?? "",
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
        alert_id: sourceAlertId || null,
        property_id: property,
        assigned_team: form.assigned_team || null,
        assigned_technician_id: form.assigned_technician_id || null,
        asset_id: form.asset_id || null,
        service_id: form.service_id || null,
      });
      nav(`/incidents/${row.id}`);
    } catch (x) {
      setError(x instanceof Error ? x.message : "Ticket could not be created");
    } finally {
      setBusy(false);
    }
  };

  return (
    <DashboardLayout>
      <WorkspaceLinks />
      <PageTitle
        eyebrow="Maintain · service desk"
        title="Create service ticket"
        copy={sourceAlertId ? "Create an assignable ticket linked to the source alert. The alert remains separate evidence." : "Create an assignable operational work item for investigation and resolution."}
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
              {getPaginatedItems(assets.data).map((asset) => (
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
            placeholder="Describe the issue, request, and operational impact"
          />
        </label>
        <div className="row-actions">
          <button type="button" className="secondary-action" onClick={() => nav("/incidents")}>
            Cancel
          </button>
          <button type="submit" className="primary-action" disabled={busy} aria-busy={busy}>
            {busy ? "Creating…" : "Create ticket"}
          </button>
        </div>
      </form>
    </DashboardLayout>
  );
}

function IncidentDetails({ id }: { id: string }) {
  const request = useRequest(() => endpoints.serviceIncident(id), [id]);
  const assignees = useRequest(() => endpoints.serviceIncidentAssignees(id), [id]);
  const me = useRequest(endpoints.me, []);

  const [note, setNote] = useState("");
  const [resolution, setResolution] = useState("");
  const [closure, setClosure] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [selectedAssignee, setSelectedAssignee] = useState("");

  const row = request.data;
  const operate = me.data?.role === "admin" || me.data?.role === "technician";
  const assignmentValue = selectedAssignee || row?.assigned_technician_id || "";

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
            Back to Tickets
          </Link>
        }
      />
      {error && <Feedback error={error} />}
      <section className="ticket-hero panel" aria-label="Ticket summary">
        <div className="ticket-hero-copy">
          <div className="ticket-badges"><StatusBadge status={row.status} /><StatusBadge status={row.priority} /><StatusBadge status={row.severity} /></div>
          <p>{row.description || "No description supplied."}</p>
        </div>
        <dl className="ticket-owner-grid">
          <Dt label="Assigned technician" value={row.assigned_technician || "Unassigned"} />
          <Dt label="Assigned team" value={row.assigned_team || "No team assigned"} />
          <Dt label="Service" value={row.service_name || "No service linked"} />
          <Dt label="Source" value={row.source_alert_id ? "Monitoring alert" : title(row.source)} />
        </dl>
      </section>

      <section className="ticket-detail-layout">
        <div className="ticket-main-column">
          <article className="panel ticket-workflow-panel">
            <header className="section-head"><div><span className="section-kicker">Workflow</span><h2>Next action</h2><p>Move this ticket through its operational lifecycle. Every transition is retained in history.</p></div></header>
            {operate ? <div className="ticket-action-bar">
              {row.status === "new" && <button className="primary-action" disabled={busy} onClick={() => void transition("acknowledged")}>Acknowledge ticket</button>}
              {["acknowledged", "on_hold"].includes(row.status) && <button className="primary-action" disabled={busy} onClick={() => void transition("in_progress")}>Start work</button>}
              {row.status === "in_progress" && <button className="secondary-action" disabled={busy} onClick={() => void transition("on_hold")}>Place on hold</button>}
              {["resolved", "closed"].includes(row.status) && <button className="secondary-action" disabled={busy} onClick={() => void transition("in_progress", { reason: "Ticket reopened" })}>Reopen ticket</button>}
              {row.status === "closed" && <p className="ticket-complete-note"><Icon name="check" aria-hidden="true" /> This ticket is closed. Reopen it if work must continue.</p>}
            </div> : <p className="ticket-readonly-note">You have read-only access to this ticket.</p>}
          </article>

          <article className="panel ticket-resolution-panel">
            <header className="section-head"><div><span className="section-kicker">Outcome</span><h2>Resolution & closure</h2><p>Record the technical outcome before the ticket is closed.</p></div></header>
            {(row.resolution_summary || row.root_cause_notes || row.follow_up_notes || row.closure_notes) && <dl className="ticket-resolution-grid">
              <Dt label="Resolution summary" value={row.resolution_summary} />
              <Dt label="Root cause notes" value={row.root_cause_notes} />
              <Dt label="Follow-up notes" value={row.follow_up_notes} />
              <Dt label="Closure notes" value={row.closure_notes} />
            </dl>}
            {operate && ["new", "acknowledged", "in_progress", "on_hold"].includes(row.status) && <form className="ticket-inline-form" onSubmit={(event) => { event.preventDefault(); void transition("resolved", { resolution_summary: resolution.trim() }); }}>
              <label htmlFor="incident-resolution"><span>Resolution summary <b>Required</b></span><textarea id="incident-resolution" rows={4} required minLength={3} value={resolution} onChange={(event) => setResolution(event.target.value)} placeholder="Describe what was fixed, restored, or changed." /></label>
              <div className="row-actions"><button className="primary-action" disabled={busy || resolution.trim().length < 3}>Resolve ticket</button></div>
            </form>}
            {operate && row.status === "resolved" && <div className="ticket-inline-form"><label htmlFor="incident-closure"><span>Closure notes <b>Required</b></span><textarea id="incident-closure" rows={4} required minLength={3} value={closure} onChange={(event) => setClosure(event.target.value)} placeholder="Confirm validation, acceptance, and any final handover." /></label><div className="row-actions"><button className="primary-action" disabled={busy || closure.trim().length < 3} onClick={() => void transition("closed", { closure_notes: closure.trim() })}>Close ticket</button></div></div>}
            {!row.resolution_summary && !operate && <p className="ticket-empty-copy">No resolution has been recorded.</p>}
          </article>

          <article className="panel ticket-activity-panel">
            <header className="section-head"><div><span className="section-kicker">History</span><h2>Activity & notes</h2><p>A chronological record of ticket activity.</p></div></header>
            {operate && <form className="ticket-note-composer" onSubmit={async (event) => { event.preventDefault(); if (!note.trim()) return; await run(() => endpoints.addServiceIncidentNote(id, note)); setNote(""); }}><label htmlFor="incident-note"><span>Add operational note</span><textarea id="incident-note" rows={3} value={note} onChange={(event) => setNote(event.target.value)} placeholder="Record investigation, communication, or work performed." /></label><button type="submit" className="primary-action" disabled={busy || !note.trim()}>Add note</button></form>}
            <div className="incident-timeline">
              {row.timeline?.length ? row.timeline.slice().reverse().map((event) => <article key={event.id}><time>{new Date(event.timestamp).toLocaleString()}</time><strong>{event.title}</strong><p>{event.summary || "No additional details."}</p><small>{event.author || "System"}</small></article>) : <p className="ticket-empty-copy">No activity has been recorded yet.</p>}
            </div>
          </article>
        </div>

        <aside className="ticket-side-column">
          <article className="panel ticket-assignment-panel">
            <header className="section-head"><div><span className="section-kicker">Ownership</span><h2>Assign technician</h2><p>Only active IT Technicians with access to this property are listed.</p></div></header>
            {operate ? assignees.loading ? <p className="ticket-empty-copy">Loading eligible technicians…</p> : assignees.error ? <Feedback error={assignees.error} /> : assignees.data?.length ? <form className="ticket-assignment-form" onSubmit={(event) => { event.preventDefault(); if (!assignmentValue) return; void run(() => endpoints.assignServiceIncident(id, assignmentValue, row.assigned_team || undefined)); }}>
              <label htmlFor="ticket-assignee"><span>IT Technician</span><select id="ticket-assignee" value={assignmentValue} onChange={(event) => setSelectedAssignee(event.target.value)}><option value="">Select a technician</option>{assignees.data.map((technician) => <option key={technician.id} value={technician.id}>{technician.username}</option>)}</select></label>
              <button className="primary-action" disabled={busy || !assignmentValue || assignmentValue === row.assigned_technician_id}>{row.assigned_technician_id ? "Reassign ticket" : "Assign ticket"}</button>
            </form> : <p className="ticket-empty-copy">No eligible IT Technicians have access to this property. Add a technician and grant property access in Administration.</p> : <p className="ticket-readonly-note">You can view the assignment, but you cannot change it.</p>}
          </article>
          <article className="panel ticket-context-panel"><header className="section-head"><div><span className="section-kicker">Context</span><h2>Business & technology</h2></div></header><dl className="ticket-side-facts"><Dt label="Category" value={title(row.category)} /><Dt label="Department" value={row.department} /><Dt label="Location" value={row.location} /><Dt label="Support contact" value={row.vendor?.support_contact} /></dl><div className="ticket-related-links">{row.asset && <Link to={`/assets/${row.asset.id}`}><span>Asset</span><strong>{row.asset.asset_number}</strong><small>{row.asset.name}</small></Link>}{row.device && <Link to={`/devices/${row.device.id}`}><span>Device</span><strong>{row.device.hostname}</strong><small>{row.device.ip_address}</small></Link>}{row.vendor && <Link to={`/vendors/${row.vendor.id}`}><span>Vendor</span><strong>{row.vendor.name}</strong><small>{row.vendor.support_contact || "Support contact unavailable"}</small></Link>}{row.procurement && <Link to={`/procurement/${row.procurement.id}`}><span>Procurement</span><strong>{row.procurement.procurement_number}</strong><small>{row.procurement.title}</small></Link>}{!row.asset && !row.device && !row.vendor && !row.procurement && <p className="ticket-empty-copy">No related operational records.</p>}</div></article>
          <article className="panel ticket-metrics-panel"><header className="section-head"><div><span className="section-kicker">Timing</span><h2>Response metrics</h2></div></header><dl className="ticket-side-facts"><Dt label="Created" value={new Date(row.created_at).toLocaleString()} /><Dt label="Acknowledged" value={row.acknowledged_at ? new Date(row.acknowledged_at).toLocaleString() : "Not yet"} /><Dt label="Time to acknowledge" value={duration(row.time_to_acknowledge_seconds)} /><Dt label="Time to resolve" value={duration(row.time_to_resolve_seconds)} /></dl></article>
          <article className="panel ticket-impact-panel"><header className="section-head"><div><span className="section-kicker">Impact</span><h2>Operational reach</h2></div></header>{row.impact ? <dl className="ticket-impact-grid"><Dt label="Confirmed" value={String(row.impact.confirmed_affected)} /><Dt label="Potential" value={String(row.impact.potentially_affected)} /><Dt label="Confidence" value={`${Math.round(row.impact.confidence_score * 100)}%`} /></dl> : <p className="ticket-empty-copy">Impact evidence is not available for this ticket.</p>}</article>
        </aside>
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

function Dt({ label, v, value }: { label: string; v?: string | null; value?: string | null }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{v || value || "Not available"}</dd>
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
