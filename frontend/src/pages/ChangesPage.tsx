import { useDeferredValue, useMemo, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { Feedback } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { StatCard } from "../components/StatCard";
import { StatusBadge } from "../components/StatusBadge";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import { PageTitle } from "./DashboardPage";

const statuses = [
  "draft",
  "submitted",
  "under_review",
  "approved",
  "scheduled",
  "in_progress",
  "completed",
  "failed",
  "rolled_back",
  "cancelled",
  "closed",
];
const levels = ["low", "medium", "high", "critical"];
const types = ["standard", "normal", "emergency"];

const title = (value: string) =>
  value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (x) => x.toUpperCase());

function MaintainLinks() {
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
    </nav>
  );
}

export default function ChangesPage() {
  const { id } = useParams();
  const location = useLocation();

  return location.pathname === "/changes/new" ? (
    <ChangeForm />
  ) : id ? (
    <ChangeDetail id={id} />
  ) : (
    <ChangeList />
  );
}

function ChangeList() {
  const request = useRequest(() => endpoints.governanceChanges(), []);
  const summary = useRequest(endpoints.governanceChangeSummary, []);
  const me = useRequest(endpoints.me, []);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [risk, setRisk] = useState("all");
  const query = useDeferredValue(search).toLowerCase();

  const rows = useMemo(
    () =>
      (request.data ?? []).filter(
        (row) =>
          (!query ||
            [
              row.change_id,
              row.title,
              row.description,
              row.reason,
            ].some((x) => x?.toLowerCase().includes(query))) &&
          (status === "all" || row.status === status) &&
          (risk === "all" || row.risk === risk)
      ),
    [request.data, query, status, risk]
  );

  return (
    <DashboardLayout>
      <MaintainLinks />
      <PageTitle
        eyebrow="Maintain · changes"
        title="Change management"
        copy="Plan, authorize and record operational changes. HIOP never executes infrastructure changes."
        action={
          me.data?.role === "admin" ? (
            <Link className="primary-action" to="/changes/new">
              Create Change
            </Link>
          ) : undefined
        }
      />

      {summary.data && (
        <section className="stats-grid" aria-label="Change statistics">
          <StatCard
            label="Under review"
            value={summary.data.under_review ?? 0}
            detail={`${summary.data.high_risk ?? 0} high risk`}
            icon="audit"
          />
          <StatCard
            label="Scheduled"
            value={summary.data.scheduled ?? 0}
            detail={`${summary.data.upcoming ?? 0} upcoming`}
            icon="check"
          />
          <StatCard
            label="In progress"
            value={summary.data.in_progress ?? 0}
            detail="Execution recorded only"
            icon="network"
          />
          <StatCard
            label="Emergency"
            value={summary.data.emergency ?? 0}
            detail="Urgent governance"
            icon="alerts"
          />
        </section>
      )}

      <section className="toolbar-panel" aria-label="Search and filter changes">
        <label htmlFor="change-search" className="search-field">
          <input
            id="change-search"
            type="search"
            aria-label="Search changes"
            placeholder="Change ID, title, reason or asset"
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
            {statuses.map((x) => (
              <option key={x} value={x}>
                {title(x)}
              </option>
            ))}
          </select>
          <select
            aria-label="Filter by risk level"
            value={risk}
            onChange={(e) => setRisk(e.target.value)}
          >
            <option value="all">All risk levels</option>
            {levels.map((x) => (
              <option key={x}>{x}</option>
            ))}
          </select>
        </div>
      </section>

      {request.loading || request.error ? (
        <Feedback loading={request.loading} error={request.error} />
      ) : !rows.length ? (
        <Feedback
          emptyTitle="No changes yet."
          empty="Create a change to govern planned operational work."
        />
      ) : (
        <section className="data-panel" aria-label="Change list">
          <div className="data-table incident-table">
            <div className="table-row table-head" role="row">
              <span>Change</span>
              <span>Schedule</span>
              <span>Impact</span>
              <span>Risk</span>
              <span>Status</span>
            </div>
            {rows.map((row) => (
              <Link className="table-row" to={`/changes/${row.id}`} key={row.id}>
                <span>
                  <strong>{row.change_id}</strong>
                  <small>{row.title}</small>
                </span>
                <span>
                  {row.planned_start
                    ? new Date(row.planned_start).toLocaleString()
                    : "Not scheduled"}
                  <small>{title(row.type)}</small>
                </span>
                <span>
                  {row.related_counts.asset ?? 0} assets
                  <small>{row.related_counts.service ?? 0} services</small>
                </span>
                <span>
                  <StatusBadge status={row.risk} />
                </span>
                <span>
                  <StatusBadge status={row.status} />
                </span>
              </Link>
            ))}
          </div>
        </section>
      )}
    </DashboardLayout>
  );
}

function ChangeForm() {
  const nav = useNavigate();
  const assets = useRequest(() => endpoints.assets(), []);
  const services = useRequest(() => endpoints.technologyServices(), []);
  const problems = useRequest(() => endpoints.operationalProblems(), []);
  const vendors = useRequest(() => endpoints.operationalVendors(), []);

  const [form, setForm] = useState({
    title: "",
    description: "",
    change_type: "normal",
    priority: "medium",
    risk: "medium",
    risk_explanation: "",
    reason: "",
    implementation_plan: "",
    validation_plan: "",
    rollback_plan: "",
    planned_start: "",
    planned_end: "",
    asset_id: "",
    service_id: "",
    problem_id: "",
    vendor_id: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const row = await endpoints.createGovernanceChange({
        ...form,
        planned_start: form.planned_start
          ? new Date(form.planned_start).toISOString()
          : null,
        planned_end: form.planned_end
          ? new Date(form.planned_end).toISOString()
          : null,
        asset_id: form.asset_id || null,
        service_id: form.service_id || null,
        problem_id: form.problem_id || null,
        vendor_id: form.vendor_id || null,
      });
      nav(`/changes/${row.id}`);
    } catch (x) {
      setError(x instanceof Error ? x.message : "Change could not be created");
    } finally {
      setBusy(false);
    }
  };

  return (
    <DashboardLayout>
      <MaintainLinks />
      <PageTitle
        eyebrow="Maintain · changes"
        title="Create change"
        copy="Document the plan, risk, impact and rollback before work starts."
      />
      {error && <Feedback error={error} />}
      <form className="panel enterprise-form" onSubmit={(e) => void submit(e)}>
        <div className="form-grid">
          <Field label="Title">
            <input
              required
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
            />
          </Field>
          <Field label="Type">
            <select
              value={form.change_type}
              onChange={(e) => setForm({ ...form, change_type: e.target.value })}
            >
              {types.map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </Field>
          <Field label="Priority">
            <select
              value={form.priority}
              onChange={(e) => setForm({ ...form, priority: e.target.value })}
            >
              {levels.map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </Field>
          <Field label="Risk">
            <select
              value={form.risk}
              onChange={(e) => setForm({ ...form, risk: e.target.value })}
            >
              {levels.map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </Field>
          <Field label="Planned start">
            <input
              type="datetime-local"
              value={form.planned_start}
              onChange={(e) => setForm({ ...form, planned_start: e.target.value })}
            />
          </Field>
          <Field label="Planned end">
            <input
              type="datetime-local"
              value={form.planned_end}
              onChange={(e) => setForm({ ...form, planned_end: e.target.value })}
            />
          </Field>
          <Select
            label="Asset"
            value={form.asset_id}
            set={(x) => setForm({ ...form, asset_id: x })}
            options={
              assets.data?.map((x) => ({
                id: x.id,
                name: `${x.asset_number} · ${x.name}`,
              })) ?? []
            }
          />
          <Select
            label="Service"
            value={form.service_id}
            set={(x) => setForm({ ...form, service_id: x })}
            options={services.data?.map((x) => ({ id: x.id, name: x.name })) ?? []}
          />
          <Select
            label="Problem"
            value={form.problem_id}
            set={(x) => setForm({ ...form, problem_id: x })}
            options={
              problems.data?.map((x) => ({
                id: x.id,
                name: `${x.problem_number} · ${x.title}`,
              })) ?? []
            }
          />
          <Select
            label="Vendor"
            value={form.vendor_id}
            set={(x) => setForm({ ...form, vendor_id: x })}
            options={vendors.data?.map((x) => ({ id: x.id, name: x.name })) ?? []}
          />
        </div>
        {[
          ["description", "Description"],
          ["reason", "Reason"],
          ["risk_explanation", "Risk explanation"],
          ["implementation_plan", "Implementation plan"],
          ["validation_plan", "Validation plan"],
          ["rollback_plan", "Rollback plan"],
        ].map(([key, label]) => (
          <label key={key}>
            {label}
            <textarea
              rows={3}
              value={form[key as keyof typeof form] as string}
              onChange={(e) => setForm({ ...form, [key]: e.target.value })}
            />
          </label>
        ))}
        <div className="row-actions">
          <button
            type="button"
            className="secondary-action"
            onClick={() => nav("/changes")}
          >
            Cancel
          </button>
          <button type="submit" className="primary-action" disabled={busy} aria-busy={busy}>
            {busy ? "Creating…" : "Create change"}
          </button>
        </div>
      </form>
    </DashboardLayout>
  );
}

function ChangeDetail({ id }: { id: string }) {
  const request = useRequest(() => endpoints.governanceChange(id), [id]);

  if (request.loading || request.error || !request.data) {
    return (
      <DashboardLayout>
        <Feedback loading={request.loading} error={request.error} />
      </DashboardLayout>
    );
  }

  const row = request.data;

  return (
    <DashboardLayout>
      <MaintainLinks />
      <PageTitle
        eyebrow={row.change_id}
        title={row.title}
        copy={`${title(row.change_type)} · ${title(row.risk)} risk`}
        action={
          <Link className="secondary-action" to="/changes">
            Back to Changes
          </Link>
        }
      />
      <section className="panel">
        <header className="section-head">
          <div>
            <h2>Change details</h2>
            <p>{row.description || "No description provided."}</p>
          </div>
          <StatusBadge status={row.status} />
        </header>
        <dl className="detail-grid">
          <Dt label="Priority" value={row.priority} />
          <Dt label="Risk" value={row.risk} />
          <Dt label="Type" value={title(row.change_type)} />
          <Dt
            label="Planned start"
            value={
              row.planned_start
                ? new Date(row.planned_start).toLocaleString()
                : "Not scheduled"
            }
          />
          <Dt
            label="Planned end"
            value={
              row.planned_end
                ? new Date(row.planned_end).toLocaleString()
                : "Not scheduled"
            }
          />
        </dl>
      </section>
    </DashboardLayout>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label>
      {label}
      {children}
    </label>
  );
}

function Select({
  label,
  value,
  set,
  options,
}: {
  label: string;
  value: string;
  set: (value: string) => void;
  options: Array<{ id: string; name: string }>;
}) {
  return (
    <label>
      {label}
      <select value={value} onChange={(e) => set(e.target.value)}>
        <option value="">Select {label.toLowerCase()}</option>
        {options.map((x) => (
          <option key={x.id} value={x.id}>
            {x.name}
          </option>
        ))}
      </select>
    </label>
  );
}

function Dt({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value || "Not available"}</dd>
    </div>
  );
}