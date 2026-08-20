import { useDeferredValue, useMemo, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Feedback } from "../components/Feedback";
import { StatCard } from "../components/StatCard";
import { StatusBadge } from "../components/StatusBadge";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints, getPaginatedItems } from "../lib/api";
import { PageTitle } from "./DashboardPage";

const states = ["open", "investigating", "known_error", "resolved", "closed"];
const priorities = ["low", "medium", "high", "critical"];
const categories = [
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

export default function ProblemsPage() {
  const { id } = useParams();
  const location = useLocation();

  return location.pathname === "/problems/new" ? (
    <ProblemForm />
  ) : id ? (
    <ProblemDetail id={id} />
  ) : (
    <ProblemList />
  );
}

function ProblemList() {
  const [params] = useSearchParams();
  const request = useRequest(() => endpoints.operationalProblems(), []);
  const summary = useRequest(endpoints.operationalProblemSummary, []);
  const me = useRequest(endpoints.me, []);

  const [search, setSearch] = useState("");
  const [status, setStatus] = useState(params.get("status") ?? "all");
  const [priority, setPriority] = useState("all");
  const query = useDeferredValue(search).toLowerCase();

  const rows = useMemo(
    () =>
      getPaginatedItems(request.data).filter(
        (row) =>
          (!query ||
            [
              row.problem_number,
              row.title,
              row.description,
              row.problem_statement,
              row.service_name,
              row.department,
              row.location,
              row.vendor?.name,
            ].some((x) => x?.toLowerCase().includes(query))) &&
          (status === "all" || row.status === status) &&
          (priority === "all" || row.priority === priority)
      ),
    [request.data, query, status, priority]
  );

  return (
    <DashboardLayout>
      <MaintainLinks />
      <PageTitle
        eyebrow="Maintain · problems"
        title="Problem management"
        copy="Investigate significant or recurring underlying causes while incidents remain separate operational records."
        action={
          me.data?.role === "admin" ? (
            <Link className="primary-action" to="/problems/new">
              Create Problem
            </Link>
          ) : undefined
        }
      />

      {summary.data && (
        <section className="stats-grid" aria-label="Problem statistics">
          <StatCard
            label="Open problems"
            value={summary.data.open ?? 0}
            detail={`${summary.data.critical ?? 0} critical`}
            icon="alerts"
          />
          <StatCard
            label="Investigating"
            value={summary.data.investigating ?? 0}
            detail="Investigation underway"
            icon="audit"
          />
          <StatCard
            label="Known errors"
            value={summary.data.known_error ?? 0}
            detail="Documented workaround"
            icon="check"
          />
          <StatCard
            label="Recurring context"
            value={summary.data.recurring ?? 0}
            detail="Multiple incidents linked"
            icon="network"
          />
        </section>
      )}

      <section className="toolbar-panel" aria-label="Search and filter problems">
        <label htmlFor="problem-search" className="search-field">
          <Icon name="search" aria-hidden="true" />
          <input
            id="problem-search"
            type="search"
            aria-label="Search problems"
            placeholder="Problem, asset, service, department, location, vendor"
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
            {states.map((x) => (
              <option key={x} value={x}>
                {title(x)}
              </option>
            ))}
          </select>
          <select
            aria-label="Filter by priority"
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
          >
            <option value="all">All priorities</option>
            {priorities.map((x) => (
              <option key={x}>{x}</option>
            ))}
          </select>
        </div>
      </section>

      {request.loading || request.error ? (
        <Feedback loading={request.loading} error={request.error} />
      ) : !rows.length ? (
        <Feedback
          emptyTitle={
            status === "known_error"
              ? "No known errors yet."
              : "No problems yet."
          }
          empty="Create a problem when an underlying recurring or significant cause requires investigation."
        />
      ) : (
        <section className="data-panel" aria-label="Problem list">
          <div className="data-table incident-table">
            <div className="table-row table-head" role="row">
              <span>Problem</span>
              <span>Context</span>
              <span>Related</span>
              <span>Priority</span>
              <span>Status</span>
            </div>
            {rows.map((row) => (
              <Link className="table-row" to={`/problems/${row.id}`} key={row.id}>
                <span>
                  <strong>{row.problem_number}</strong>
                  <small>{row.title}</small>
                </span>
                <span>
                  {row.service_name || row.department || "No service/department"}
                  <small>{title(row.category)}</small>
                </span>
                <span>
                  {row.related_counts.incident ?? 0} incidents
                  <small>{row.related_counts.asset ?? 0} assets</small>
                </span>
                <span>
                  <StatusBadge status={row.priority} />
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

function ProblemForm() {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const incidentId = params.get("incident");
  const source = useRequest(
    () => (incidentId ? endpoints.serviceIncident(incidentId) : Promise.resolve(null)),
    [incidentId]
  );

  // Simplified problem form - full implementation would be similar to IncidentForm
  return (
    <DashboardLayout>
      <MaintainLinks />
      <PageTitle
        eyebrow="Maintain · problems"
        title="Create problem"
        copy="Document underlying causes and known errors."
      />
      <Feedback empty="Problem form implementation pending." />
    </DashboardLayout>
  );
}

function ProblemDetail({ id }: { id: string }) {
  const request = useRequest(() => endpoints.operationalProblem(id), [id]);

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
        eyebrow={row.problem_number}
        title={row.title}
        copy={`${title(row.category)} · Created ${new Date(row.created_at).toLocaleString()}`}
        action={
          <Link className="secondary-action" to="/problems">
            Back to Problems
          </Link>
        }
      />
      <section className="panel">
        <header className="section-head">
          <div>
            <h2>Problem details</h2>
            <p>{row.problem_statement || "No problem statement provided."}</p>
          </div>
          <StatusBadge status={row.status} />
        </header>
        <dl className="detail-grid">
          <Dt label="Priority" value={row.priority} />
          <Dt label="Category" value={title(row.category)} />
          <Dt label="Service" value={row.service_name || "Not assigned"} />
          <Dt label="Department" value={row.department || "Not assigned"} />
          <Dt label="Location" value={row.location || "Not assigned"} />
          <Dt label="Vendor" value={row.vendor?.name || "Not specified"} />
        </dl>
      </section>
    </DashboardLayout>
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