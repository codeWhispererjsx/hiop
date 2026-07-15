import { type FormEvent, useMemo, useState } from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import { PageTitle } from "./DashboardPage";
import { Icon } from "../components/Icon";
import Modal from "../components/Modal";
import { Feedback } from "../components/Feedback";
import { endpoints } from "../lib/api";
import { useRequest } from "../hooks/useRequest";
import type { Ticket, User } from "../lib/types";

export default function TicketsPage() {
  const tickets = useRequest(endpoints.tickets, []);
  const users = useRequest(endpoints.users, []);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("All");
  const [editing, setEditing] = useState<Ticket | null | "new">(null);
  const [assigning, setAssigning] = useState<Ticket | null>(null);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const userNames = useMemo(() => new Map((users.data ?? []).map((user) => [user.id, user.username])), [users.data]);
  const rows = useMemo(() => (tickets.data ?? []).filter((ticket) => (status === "All" || ticket.status === status) && `${ticket.title} ${ticket.description} ${ticket.priority}`.toLowerCase().includes(query.toLowerCase())), [tickets.data, query, status]);
  const act = async (label: string, action: () => Promise<unknown>) => { setBusy(label); setNotice(""); try { await action(); setNotice(`${label} completed.`); await tickets.reload(); } catch (error) { setNotice(error instanceof Error ? error.message : `${label} failed`); } finally { setBusy(""); } };
  return <DashboardLayout>
    <PageTitle eyebrow="IT service desk" title="Service tickets" copy="Create, assign, update and close operational issues." action={<button className="primary-action" onClick={() => setEditing("new")}><Icon name="tickets"/>New ticket</button>}/>
    {notice && <div className="inline-notice">{notice}</div>}
    <section className="toolbar-panel"><div className="search-field"><Icon name="search"/><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search tickets"/></div><select value={status} onChange={(event) => setStatus(event.target.value)}><option>All</option><option>Open</option><option>In Progress</option><option>Closed</option></select><button className="secondary-action" onClick={() => void tickets.reload()}>Refresh</button></section>
    {tickets.loading || tickets.error || !rows.length ? <Feedback loading={tickets.loading} error={tickets.error} empty="No tickets match the current filters." onRetry={tickets.reload}/> : <section className="ticket-grid">{rows.map((ticket) => <article className="ticket-card" key={ticket.id}><header><b className={`priority ${ticket.priority.toLowerCase()}`}>{ticket.priority}</b><b className={`status-badge ${ticket.status.toLowerCase().replace(" ", "-")}`}>{ticket.status}</b></header><h2>{ticket.title}</h2><p>{ticket.description}</p><dl><div><dt>Reporter</dt><dd>{userNames.get(ticket.reported_by) ?? ticket.reported_by.slice(0, 8)}</dd></div><div><dt>Assignee</dt><dd>{ticket.assigned_to ? userNames.get(ticket.assigned_to) ?? ticket.assigned_to.slice(0, 8) : "Unassigned"}</dd></div></dl><footer><button disabled={!!busy || ticket.status === "Closed"} onClick={() => setEditing(ticket)}>Edit</button><button disabled={!!busy || ticket.status === "Closed"} onClick={() => setAssigning(ticket)}>Assign</button><button disabled={!!busy || ticket.status === "Closed"} onClick={() => void act("Close ticket", () => endpoints.closeTicket(ticket.id))}>Close</button><button disabled={!!busy} onClick={() => confirm("Delete this ticket?") && void act("Delete ticket", () => endpoints.deleteTicket(ticket.id))}>Delete</button></footer></article>)}</section>}
    {editing && <TicketModal ticket={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={async () => { setEditing(null); await tickets.reload(); }}/>}
    {assigning && <AssignModal ticket={assigning} users={users.data ?? []} onClose={() => setAssigning(null)} onSaved={async () => { setAssigning(null); await tickets.reload(); }}/>}
  </DashboardLayout>;
}

function TicketModal({ ticket, onClose, onSaved }: { ticket: Ticket | null; onClose: () => void; onSaved: () => Promise<void> }) {
  const [form, setForm] = useState({ title: ticket?.title ?? "", description: ticket?.description ?? "", priority: ticket?.priority ?? "Medium", status: ticket?.status ?? "Open" });
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => { event.preventDefault(); setBusy(true); setError(""); try { if (ticket) await endpoints.updateTicket(ticket.id, form); else await endpoints.createTicket(form); await onSaved(); } catch (error) { setError(error instanceof Error ? error.message : "Unable to save ticket"); } finally { setBusy(false); } };
  return <Modal title={ticket ? "Edit service ticket" : "Create service ticket"} onClose={onClose}><form className="modal-form" onSubmit={submit}><label>Title<input required value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })}/></label><label>Description<textarea required rows={5} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })}/></label><label>Priority<select value={form.priority} onChange={(event) => setForm({ ...form, priority: event.target.value })}><option>Low</option><option>Medium</option><option>High</option></select></label>{ticket && <label>Status<select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}><option>Open</option><option>In Progress</option><option>Closed</option></select></label>}{error && <p className="form-error">{error}</p>}<footer><button type="button" className="secondary-action" onClick={onClose}>Cancel</button><button className="primary-action" disabled={busy}>{busy ? "Saving…" : "Save ticket"}</button></footer></form></Modal>;
}

function AssignModal({ ticket, users, onClose, onSaved }: { ticket: Ticket; users: User[]; onClose: () => void; onSaved: () => Promise<void> }) {
  const [id, setId] = useState(ticket.assigned_to ?? ""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const eligible = users.filter((user) => user.is_active && ["admin", "technician"].includes(user.role));
  const submit = async (event: FormEvent) => { event.preventDefault(); setBusy(true); setError(""); try { await endpoints.assignTicket(ticket.id, id); await onSaved(); } catch (error) { setError(error instanceof Error ? error.message : "Assignment failed"); } finally { setBusy(false); } };
  return <Modal title={`Assign ${ticket.title}`} onClose={onClose}><form className="modal-form" onSubmit={submit}><label>Technician<select required value={id} onChange={(event) => setId(event.target.value)}><option value="">Select an active team member</option>{eligible.map((user) => <option key={user.id} value={user.id}>{user.username} — {user.role}</option>)}</select></label>{!eligible.length && <p className="form-error">No active admin or technician accounts are available.</p>}{error && <p className="form-error">{error}</p>}<footer><button type="button" className="secondary-action" onClick={onClose}>Cancel</button><button className="primary-action" disabled={busy || !id}>{busy ? "Assigning…" : "Assign ticket"}</button></footer></form></Modal>;
}
