import { type FormEvent, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { ConfirmationModal } from "../components/ConfirmationModal";
import { Feedback } from "../components/Feedback";
import Modal from "../components/Modal";
import { StatusBadge } from "../components/StatusBadge";
import { Toast } from "../components/Toast";
import { Icon } from "../components/Icon";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import type { AuditLog, Ticket, User } from "../lib/types";
import { PageTitle } from "./DashboardPage";

type ConfirmAction = "close" | "delete" | null;

export default function TicketDetailsPage() {
  const {id = ""} = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const ticket = useRequest(() => endpoints.ticket(id), [id]);
  const users = useRequest(endpoints.users, []);
  const me = useRequest(endpoints.me, []);
  const devices = useRequest(endpoints.devices, []);
  const audit = useRequest(() => endpoints.auditLogs({ entity_type: "Ticket", page_size: 100 }), []);
  const [assigning, setAssigning] = useState(false);
  const [confirming, setConfirming] = useState<ConfirmAction>(null);
  const [busy, setBusy] = useState("");
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState((location.state as {notice?: string} | null)?.notice ?? "");
  const current = ticket.data;
  const userMap = useMemo(() => new Map((users.data ?? []).map(user => [user.id,user.username])), [users.data]);
  const device = devices.data?.find(item => item.id === current?.device_id);
  const ticketAudit = useMemo(() => (audit.data?.items ?? []).filter(item => item.entity_id === id).sort((a,b)=>new Date(a.created_at).getTime()-new Date(b.created_at).getTime()), [audit.data,id]);
  const canOperate = ["admin","technician"].includes(me.data?.role ?? "");
  const canDelete = me.data?.role === "admin";
  const refresh = async () => { await Promise.all([ticket.reload(), audit.reload()]); };
  const act = async (kind: "close" | "delete" | "reopen") => {
    if (!current || busy) return;
    setBusy(kind); setActionError("");
    try {
      if (kind === "delete") { await endpoints.deleteTicket(current.id); navigate("/tickets", {replace:true, state:{notice:"Ticket deleted successfully."}}); return; }
      if (kind === "close") await endpoints.closeTicket(current.id); else await endpoints.updateTicket(current.id,{status:"Open"});
      setNotice(kind === "close" ? "Ticket closed successfully." : "Ticket reopened successfully."); setConfirming(null); await refresh();
    } catch (error) { setActionError(error instanceof Error ? error.message : `Unable to ${kind} ticket.`); }
    finally { setBusy(""); }
  };

  return <DashboardLayout><PageTitle eyebrow="Service ticket" title={current?.title ?? "Ticket details"} copy="Complete operational context, ownership, related asset and audited lifecycle activity." action={<div className="page-actions"><Link className="secondary-action" to="/tickets">Back to tickets</Link>{current && <><Link className="secondary-action" to={`/tickets/${id}/edit`}>Edit ticket</Link>{canOperate && current.status !== "Closed" && <button className="secondary-action" onClick={() => setAssigning(true)}>Assign</button>}{canOperate && current.status !== "Closed" && <button className="primary-action" onClick={() => {setActionError("");setConfirming("close")}}>Close ticket</button>}{canOperate && current.status === "Closed" && <button className="primary-action" disabled={busy === "reopen"} onClick={() => void act("reopen")}>{busy === "reopen" ? "Reopening…" : "Reopen ticket"}</button>}{canDelete && <button className="danger-action" onClick={() => {setActionError("");setConfirming("delete")}}>Delete ticket</button>}</>}</div>}/>
    {notice && <Toast message={notice}/>}
    {ticket.loading || ticket.error || devices.loading || devices.error || me.loading || me.error ? <Feedback loading={ticket.loading || devices.loading || me.loading} error={ticket.error || devices.error || me.error} onRetry={() => void Promise.all([ticket.reload(), devices.reload(), me.reload(), users.reload(), audit.reload()])}/> : !current ? <Feedback emptyTitle="Ticket not found" empty="No ticket exists with this identifier."/> : <>
      <section className="ticket-detail-layout"><article className="ticket-detail-card panel"><header><div><span className={`priority ${current.priority.toLowerCase()}`}>{current.priority}</span><StatusBadge status={current.status}/></div><small>Ticket ID · {current.id}</small></header><p className="ticket-detail-description">{current.description}</p><dl><Detail label="Reported by" value={userLabel(current.reported_by,userMap)}/><Detail label="Assigned to" value={userLabel(current.assigned_to,userMap)}/><Detail label="Created" value={new Date(current.created_at).toLocaleString()}/><Detail label="Last updated" value={new Date(current.updated_at).toLocaleString()}/><Detail label="Related device" value={device?.hostname ?? (current.device_id ? "Linked device" : "None")}/><Detail label="Asset tag" value={device?.asset_tag ?? "—"}/></dl>{device && <footer><Link className="secondary-action" to={`/devices/${device.id}`}>Open related device</Link></footer>}</article>
      <aside className="ticket-side-stack"><section className="panel ticket-timeline-panel"><header className="section-head"><div><h2>Activity timeline</h2><p>Persisted ticket audit entries in chronological order.</p></div></header>{audit.loading ? <Feedback loading/> : audit.error ? <div className="api-gap compact"><Icon name="warning"/><div><strong>Audit history unavailable</strong><p>{audit.error}</p></div></div> : <TicketTimeline ticket={current} entries={ticketAudit}/>}</section><div className="api-gap compact"><Icon name="warning"/><div><strong>No exact alert relationship</strong><p>The backend links alerts and tickets to devices independently but does not store an alert-to-ticket identifier.</p></div></div></aside></section>
      {users.error && canOperate && <div className="api-gap compact"><Icon name="warning"/><div><strong>Eligible users unavailable</strong><p>{users.error}</p></div></div>}
    </>}
    {assigning && current && <AssignTicketModal ticket={current} users={users.data ?? []} onClose={() => setAssigning(false)} onAssigned={async updated => {setAssigning(false);setNotice(`Ticket assigned to ${userMap.get(updated.assigned_to ?? "") ?? "the selected user"}.`);await refresh();}}/>}
    {confirming === "close" && current && <ConfirmationModal title="Close ticket" confirmLabel="Close ticket" busyLabel="Closing…" busy={busy === "close"} error={actionError} onCancel={() => setConfirming(null)} onConfirm={() => void act("close")}><p>Close <strong>{current.title}</strong>? The ticket and audit history will remain available.</p></ConfirmationModal>}
    {confirming === "delete" && current && <ConfirmationModal title="Delete ticket" confirmLabel="Delete permanently" busyLabel="Deleting…" busy={busy === "delete"} error={actionError} onCancel={() => setConfirming(null)} onConfirm={() => void act("delete")}><p>Delete <strong>{current.title}</strong>? This removes the ticket record. The deletion audit entry remains available.</p><p className="confirmation-warning">This action cannot be undone.</p></ConfirmationModal>}
  </DashboardLayout>;
}

function Detail({label,value}:{label:string;value:string}) { return <div><dt>{label}</dt><dd>{value}</dd></div>; }
function userLabel(id:string|null,map:Map<string,string>) { return id ? map.get(id) ?? `User ${id.slice(0,8)}` : "Unassigned"; }

function TicketTimeline({ticket,entries}:{ticket:Ticket;entries:AuditLog[]}) {
  const events = entries.length ? entries : [{id:"created",actor:"System",action:"CREATE_TICKET",entity_type:"Ticket",entity_id:ticket.id,description:`Created ticket '${ticket.title}'`,created_at:ticket.created_at}];
  return <div className="ticket-timeline">{events.map(entry => <article key={entry.id}><i/><time>{new Date(entry.created_at).toLocaleString()}</time><strong>{timelineLabel(entry.action)}</strong><p>{entry.description} · {entry.actor}</p></article>)}</div>;
}
function timelineLabel(action:string) { return ({CREATE_TICKET:"Ticket created",UPDATE_TICKET:"Ticket updated",ASSIGN_TICKET:"Ticket assigned",CLOSE_TICKET:"Ticket closed",DELETE_TICKET:"Ticket deleted"} as Record<string,string>)[action] ?? action.replaceAll("_"," "); }

function AssignTicketModal({ticket,users,onClose,onAssigned}:{ticket:Ticket;users:User[];onClose:()=>void;onAssigned:(ticket:Ticket)=>Promise<void>}) {
  const eligible = users.filter(user => user.is_active && ["admin","technician"].includes(user.role));
  const [assignee,setAssignee] = useState(ticket.assigned_to ?? ""); const [error,setError] = useState(""); const [submitting,setSubmitting] = useState(false);
  const submit = async (event:FormEvent) => {event.preventDefault();if(!assignee||submitting)return;setSubmitting(true);setError("");try{await onAssigned(await endpoints.assignTicket(ticket.id,assignee));}catch(requestError){setError(requestError instanceof Error?requestError.message:"Unable to assign ticket.");}finally{setSubmitting(false)}};
  return <Modal title="Assign ticket" onClose={() => !submitting && onClose()}><form className="modal-form" onSubmit={submit}><label>Eligible assignee<select required value={assignee} disabled={submitting} onChange={event=>setAssignee(event.target.value)}><option value="">Select an active admin or technician</option>{eligible.map(user=><option key={user.id} value={user.id}>{user.username} · {user.role}</option>)}</select></label>{!eligible.length&&<div className="form-error">No eligible users were returned by the backend.</div>}{error&&<div className="form-error" role="alert">{error}</div>}<footer><button type="button" className="secondary-action" disabled={submitting} onClick={onClose}>Cancel</button><button className="primary-action" disabled={submitting||!assignee}>{submitting?"Assigning…":"Assign ticket"}</button></footer></form></Modal>;
}
