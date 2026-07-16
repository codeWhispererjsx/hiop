import { useMemo, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { PageTitle } from "./DashboardPage";
import { Icon } from "../components/Icon";
import { Feedback } from "../components/Feedback";
import { StatCard } from "../components/StatCard";
import { StatusBadge } from "../components/StatusBadge";
import { Toast } from "../components/Toast";
import { endpoints } from "../lib/api";
import { useRequest } from "../hooks/useRequest";
import type { Device, Ticket } from "../lib/types";

const PAGE_SIZE = 10;
const dateValue = (value: string) => new Date(value).toLocaleDateString("en-CA");

export default function TicketsPage() {
  const tickets = useRequest(endpoints.tickets, []);
  const users = useRequest(endpoints.users, []);
  const devices = useRequest(endpoints.devices, []);
  const [params] = useSearchParams();
  const location = useLocation();
  const successNotice = (location.state as {notice?: string} | null)?.notice;
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState(params.get("status") ?? "All");
  const [priority, setPriority] = useState("All");
  const [assignee, setAssignee] = useState("All");
  const [createdDate, setCreatedDate] = useState("");
  const [page, setPage] = useState(1);
  const userNames = useMemo(() => new Map((users.data ?? []).map(user => [user.id, user.username])), [users.data]);
  const deviceMap = useMemo(() => new Map((devices.data ?? []).map(device => [device.id, device])), [devices.data]);
  const assignees = useMemo(() => {
    const ids = [...new Set((tickets.data ?? []).map(ticket => ticket.assigned_to).filter((id): id is string => Boolean(id)))];
    return ids.map(id => ({id, label:userNames.get(id) ?? `User ${id.slice(0,8)}`}));
  }, [tickets.data, userNames]);
  const filtered = useMemo(() => (tickets.data ?? []).filter(ticket => {
    const text = `${ticket.title} ${ticket.description}`.toLowerCase();
    return (!query.trim() || text.includes(query.trim().toLowerCase()))
      && (status === "All" || ticket.status === status)
      && (priority === "All" || ticket.priority === priority)
      && (assignee === "All" || (assignee === "Unassigned" ? !ticket.assigned_to : ticket.assigned_to === assignee))
      && (!createdDate || dateValue(ticket.created_at) === createdDate);
  }), [assignee, createdDate, priority, query, status, tickets.data]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount);
  const rows = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const all = tickets.data ?? [];
  const clear = () => { setQuery(""); setStatus("All"); setPriority("All"); setAssignee("All"); setCreatedDate(""); setPage(1); };

  return <DashboardLayout>
    <PageTitle eyebrow="IT service desk" title="Enterprise tickets" copy="Manage real operational issues from creation through assignment, resolution and audit." action={<Link className="primary-action" to="/tickets/new"><Icon name="tickets"/>Create ticket</Link>}/>
    {successNotice && <Toast message={successNotice}/>}
    {tickets.loading || tickets.error || devices.loading || devices.error ? <Feedback loading={tickets.loading || devices.loading} error={tickets.error || devices.error} onRetry={() => void Promise.all([tickets.reload(), devices.reload(), users.reload()])}/> : <>
      <section className="tickets-summary">
        <StatCard label="Total tickets" value={all.length} detail="All persisted service records" icon="tickets" trend="Recorded"/>
        <StatCard label="Open tickets" value={all.filter(item => item.status === "Open").length} detail="Awaiting assignment or action" icon="warning" tone="warning" trend="Queue"/>
        <StatCard label="In progress" value={all.filter(item => item.status === "In Progress").length} detail="Assigned and actively handled" icon="network" tone="success" trend="Active"/>
        <StatCard label="Closed tickets" value={all.filter(item => item.status === "Closed").length} detail="Completed service records" icon="check" tone="success" trend="Complete"/>
        <StatCard label="High priority" value={all.filter(item => item.priority === "High").length} detail="High-priority operational issues" icon="alerts" tone="danger" trend="Priority"/>
        <StatCard label="Unassigned" value={all.filter(item => !item.assigned_to).length} detail="Tickets without an owner" icon="users" tone="warning" trend="Ownership"/>
      </section>
      <section className="toolbar-panel tickets-toolbar">
        <label className="search-field"><Icon name="search" size={16}/><input aria-label="Search tickets" placeholder="Search title or description" value={query} onChange={event => {setQuery(event.target.value);setPage(1)}}/></label>
        <select aria-label="Ticket status" value={status} onChange={event => {setStatus(event.target.value);setPage(1)}}><option>All</option><option>Open</option><option>In Progress</option><option>Closed</option></select>
        <select aria-label="Ticket priority" value={priority} onChange={event => {setPriority(event.target.value);setPage(1)}}><option>All</option><option>Low</option><option>Medium</option><option>High</option></select>
        <select aria-label="Ticket assignee" value={assignee} onChange={event => {setAssignee(event.target.value);setPage(1)}}><option>All</option><option>Unassigned</option>{assignees.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select>
        <input className="tickets-date" aria-label="Created date" type="date" value={createdDate} onChange={event => {setCreatedDate(event.target.value);setPage(1)}}/>
        <button className="secondary-action" onClick={clear}>Clear</button><button className="secondary-action" onClick={() => void tickets.reload()}>Refresh</button>
      </section>
      <section className="panel tickets-table-panel"><header className="section-head"><div><h2>Ticket queue</h2><p>{filtered.length} of {all.length} tickets match the current view.</p></div></header>
        {!filtered.length ? <Feedback emptyTitle="No tickets found" empty="No tickets match the selected search and filters."/> : <TicketTable tickets={rows} users={userNames} devices={deviceMap}/>}
      </section>
      {filtered.length > 0 && <nav className="pagination" aria-label="Ticket pages"><button className="secondary-action" disabled={currentPage === 1} onClick={() => setPage(value => value - 1)}>Previous</button><div className="page-numbers">{Array.from({length:pageCount},(_,index)=>index+1).map(number => <button key={number} className={currentPage === number ? "active" : ""} aria-current={currentPage === number ? "page" : undefined} onClick={() => setPage(number)}>{number}</button>)}</div><button className="secondary-action" disabled={currentPage === pageCount} onClick={() => setPage(value => value + 1)}>Next</button></nav>}
      {users.error && <div className="api-gap compact"><Icon name="warning"/><div><strong>Assignee names unavailable</strong><p>{users.error} Ticket data remains available and assignee identifiers are preserved.</p></div></div>}
    </>}
  </DashboardLayout>;
}

function TicketTable({tickets, users, devices}: {tickets: Ticket[]; users: Map<string,string>; devices: Map<string,Device>}) {
  const userLabel = (id: string | null) => id ? users.get(id) ?? `User ${id.slice(0,8)}` : "Unassigned";
  return <div className="tickets-table-wrap"><table className="tickets-table"><thead><tr><th>Ticket</th><th>Priority</th><th>Status</th><th>Reporter</th><th>Assignee</th><th>Created</th><th>Updated</th><th>Related device</th><th>Actions</th></tr></thead><tbody>{tickets.map(ticket => <tr key={ticket.id}><td><Link className="ticket-title-link" to={`/tickets/${ticket.id}`}><strong>{ticket.title}</strong><span>{ticket.description}</span></Link></td><td><span className={`priority ${ticket.priority.toLowerCase()}`}>{ticket.priority}</span></td><td><StatusBadge status={ticket.status}/></td><td>{userLabel(ticket.reported_by)}</td><td>{userLabel(ticket.assigned_to)}</td><td>{new Date(ticket.created_at).toLocaleString()}</td><td>{new Date(ticket.updated_at).toLocaleString()}</td><td>{ticket.device_id ? <Link className="table-link" to={`/devices/${ticket.device_id}`}>{devices.get(ticket.device_id)?.hostname ?? "Linked device"}</Link> : "None"}</td><td><div className="row-actions"><Link to={`/tickets/${ticket.id}`}>View</Link>{ticket.status !== "Closed" && <Link to={`/tickets/${ticket.id}/edit`}>Edit</Link>}</div></td></tr>)}</tbody></table></div>;
}
