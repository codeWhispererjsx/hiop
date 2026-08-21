import { useDeferredValue, useMemo, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Feedback } from "../components/Feedback";
import { Icon } from "../components/Icon";
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
  const [form, setForm] = useState({title:"",description:"",problem_statement:"",priority:"medium",category:"other",assigned_team:""});
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const submit=async(event:FormEvent)=>{event.preventDefault();setBusy(true);setError("");try{const incident=source.data;const row=await endpoints.createOperationalProblem({...form,assigned_team:form.assigned_team||null,source:incident?"incident":"manual",incident_id:incident?.id??null,asset_id:incident?.asset_id??null,service_id:incident?.service_id??null});nav(`/problems/${row.id}`)}catch(x){setError(x instanceof Error?x.message:"Problem could not be created")}finally{setBusy(false)}};
  return (
    <DashboardLayout>
      <MaintainLinks />
      <PageTitle
        eyebrow="Maintain · problems"
        title="Create problem"
        copy="Document underlying causes and known errors."
      />
      {source.loading?<Feedback loading/>:<form className="panel enterprise-form" onSubmit={event=>void submit(event)}>{error&&<Feedback error={error}/>} {source.data&&<p className="inline-notice">Context inherited from incident <strong>{source.data.incident_number}</strong>. The incident remains a separate record.</p>}<div className="form-grid"><label>Title<input required minLength={3} value={form.title} onChange={event=>setForm({...form,title:event.target.value})}/></label><label>Priority<select value={form.priority} onChange={event=>setForm({...form,priority:event.target.value})}>{priorities.map(value=><option key={value}>{value}</option>)}</select></label><label>Category<select value={form.category} onChange={event=>setForm({...form,category:event.target.value})}>{categories.map(value=><option key={value}>{value}</option>)}</select></label><label>Assigned team<input value={form.assigned_team} onChange={event=>setForm({...form,assigned_team:event.target.value})}/></label></div><label>Problem statement<textarea required minLength={3} rows={4} value={form.problem_statement} onChange={event=>setForm({...form,problem_statement:event.target.value})} placeholder="Describe the recurring or significant underlying problem."/></label><label>Description<textarea rows={4} value={form.description} onChange={event=>setForm({...form,description:event.target.value})}/></label><div className="row-actions"><Link className="secondary-action" to="/problems">Cancel</Link><button className="primary-action" disabled={busy}>{busy?"Creating…":"Create problem"}</button></div></form>}
    </DashboardLayout>
  );
}

function ProblemDetail({ id }: { id: string }) {
  const request = useRequest(() => endpoints.operationalProblem(id), [id]);
  const me = useRequest(endpoints.me, []);
  const [fields,setFields]=useState({root_cause:"",workaround:"",resolution:"",follow_up_notes:""});
  const [note,setNote]=useState("");
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);

  if (request.loading || request.error || !request.data) {
    return (
      <DashboardLayout>
        <Feedback loading={request.loading} error={request.error} />
      </DashboardLayout>
    );
  }

  const row = request.data;
  const save=async()=>{setBusy(true);setError("");try{await endpoints.updateOperationalProblem(id,fields);await request.reload()}catch(x){setError(x instanceof Error?x.message:"Problem could not be updated")}finally{setBusy(false)}};
  const transition=async(target_status:string)=>{setBusy(true);setError("");try{await endpoints.transitionOperationalProblem(id,{target_status,resolution:target_status==="resolved"?(fields.resolution||row.resolution):undefined});await request.reload()}catch(x){setError(x instanceof Error?x.message:"Status could not be updated")}finally{setBusy(false)}};

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
      {error&&<Feedback error={error}/>}
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
      <section className="panel"><header className="section-head"><h2>Investigation and resolution</h2></header><dl className="detail-grid"><Dt label="Root cause" value={row.root_cause}/><Dt label="Workaround" value={row.workaround}/><Dt label="Corrective resolution" value={row.resolution}/><Dt label="Follow-up notes" value={row.follow_up_notes}/></dl>{me.data?.role==="admin"&&<div className="enterprise-form"><label>Root cause<textarea value={fields.root_cause} onChange={event=>setFields({...fields,root_cause:event.target.value})}/></label><label>Workaround<textarea value={fields.workaround} onChange={event=>setFields({...fields,workaround:event.target.value})}/></label><label>Corrective resolution<textarea value={fields.resolution} onChange={event=>setFields({...fields,resolution:event.target.value})}/></label><label>Follow-up notes<textarea value={fields.follow_up_notes} onChange={event=>setFields({...fields,follow_up_notes:event.target.value})}/></label><div className="row-actions"><button className="secondary-action" disabled={busy} onClick={()=>void save()}>Save investigation</button>{states.filter(state=>state!==row.status).map(state=><button key={state} disabled={busy||(state==="resolved"&&!fields.resolution&&!row.resolution)} onClick={()=>void transition(state)}>{title(state)}</button>)}</div></div>}</section>
      <section className="panel"><header className="section-head"><h2>Related incidents and assets</h2></header><div className="linked-list">{row.incidents?.map(item=><Link key={item.id} to={`/incidents/${item.id}`}><strong>{item.incident_number}</strong><small>{item.title}</small></Link>)}{row.assets?.map(item=><Link key={item.id} to={`/assets/${item.id}`}><strong>{item.asset_number}</strong><small>{item.name}</small></Link>)}</div>{!row.incidents?.length&&!row.assets?.length&&<p>No related incidents or assets.</p>}</section>
      <section className="panel"><header className="section-head"><h2>Existing incident impact</h2></header>{row.impact?<dl className="detail-grid"><Dt label="Confirmed affected" value={String(row.impact.confirmed_affected)}/><Dt label="Potential impact" value={String(row.impact.potentially_affected)}/><Dt label="Evidence source" value={row.impact.source}/></dl>:<p>No existing incident impact evidence is available.</p>}</section>
      {me.data?.role!=="viewer"&&<section className="panel"><h2>Add problem note</h2><form onSubmit={async event=>{event.preventDefault();if(!note.trim())return;setBusy(true);try{await endpoints.addOperationalProblemNote(id,note.trim());setNote("");await request.reload()}catch(x){setError(x instanceof Error?x.message:"Note could not be added")}finally{setBusy(false)}}}><label>Note<textarea required minLength={2} value={note} onChange={event=>setNote(event.target.value)}/></label><button className="primary-action" disabled={busy||note.trim().length<2}>Add note</button></form></section>}
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
