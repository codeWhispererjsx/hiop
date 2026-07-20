import { useDeferredValue, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ConfirmationModal } from "../components/ConfirmationModal";
import { ApprovalDialog, RejectDialog, RunDiscoveryDialog } from "../components/DiscoveryDialogs";
import { Feedback } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { StatCard } from "../components/StatCard";
import { StatusBadge } from "../components/StatusBadge";
import { Toast } from "../components/Toast";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import type { BulkApprovalItem, DiscoveredDevice, DiscoveryStatus, LiveEvent, ReviewStatus } from "../lib/types";
import { PageTitle } from "./DashboardPage";


type Dialog = { kind:"approve"; devices:DiscoveredDevice[] } | { kind:"ignore"; devices:DiscoveredDevice[] } | { kind:"reject"; devices:DiscoveredDevice[] } | { kind:"run" } | null;

export default function DiscoveryPage() {
  const currentUser = useRequest(endpoints.me, []);
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const [status, setStatus] = useState<DiscoveryStatus | "">("");
  const [reviewStatus, setReviewStatus] = useState<ReviewStatus | "">("");
  const [sortBy, setSortBy] = useState("last_seen_at");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [dialog, setDialog] = useState<Dialog>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");
  const stats = useRequest(endpoints.discoveryStats, []);
  const records = useRequest(() => endpoints.discovery({
    search: deferredSearch || undefined,
    status: status || undefined,
    review_status: reviewStatus || undefined,
    sort_by: sortBy,
    sort_order: sortOrder,
    page,
    page_size: 25,
  }), [deferredSearch, status, reviewStatus, sortBy, sortOrder, page]);
  const isAdmin = currentUser.data?.role === "admin";
  const selectedDevices = useMemo(() => (records.data?.items ?? []).filter((device) => selected.has(device.id)), [records.data, selected]);
  const pendingOnPage = (records.data?.items ?? []).filter((device) => device.review_status === "pending");

  const refresh = async () => {
    await Promise.all([records.reload(), stats.reload()]);
  };
  const closeDialog = () => { if (!busy) { setDialog(null); setActionError(""); } };
  const complete = async (message: string) => {
    setDialog(null); setSelected(new Set()); setNotice(message); setActionError(""); await refresh();
  };
  const approve = async (items: BulkApprovalItem[]) => {
    setBusy(true); setActionError("");
    try {
      if (items.length === 1) await endpoints.approveDiscovery(items[0].discovery_id, items[0].inventory);
      else await endpoints.bulkApproveDiscovery(items);
      await complete(items.length === 1 ? "Device approved and added to inventory." : `${items.length} devices approved and added to inventory.`);
    } catch (error) { setActionError(message(error)); } finally { setBusy(false); }
  };
  const ignore = async () => {
    if (!dialog || dialog.kind !== "ignore") return;
    setBusy(true); setActionError("");
    try {
      if (dialog.devices.length === 1) await endpoints.ignoreDiscovery(dialog.devices[0].id);
      else await endpoints.bulkIgnoreDiscovery(dialog.devices.map((device) => device.id));
      await complete(dialog.devices.length === 1 ? "Discovery ignored; its history was preserved." : `${dialog.devices.length} discoveries ignored.`);
    } catch (error) { setActionError(message(error)); } finally { setBusy(false); }
  };
  const reject = async (reason?: string) => {
    if (!dialog || dialog.kind !== "reject") return;
    setBusy(true); setActionError("");
    try {
      if (dialog.devices.length === 1) await endpoints.rejectDiscovery(dialog.devices[0].id, reason);
      else await endpoints.bulkRejectDiscovery(dialog.devices.map((device) => device.id), reason);
      await complete(dialog.devices.length === 1 ? "Discovery rejected; its history was preserved." : `${dialog.devices.length} discoveries rejected.`);
    } catch (error) { setActionError(message(error)); } finally { setBusy(false); }
  };
  const run = async (range: string) => {
    setBusy(true); setActionError("");
    try { const result = await endpoints.runDiscovery(range); await complete(`Discovery completed: ${result.hosts_responded} hosts responded, ${result.new_devices} new.`); }
    catch (error) { setActionError(message(error)); } finally { setBusy(false); }
  };
  const exportCsv = async () => {
    setBusy(true);
    try {
      const file = await endpoints.exportDiscovery();
      const url = URL.createObjectURL(file.blob);
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = file.filename; anchor.click(); URL.revokeObjectURL(url);
    } catch (error) { setNotice(`Export failed: ${message(error)}`); } finally { setBusy(false); }
  };
  const sort = (field: string) => {
    if (sortBy === field) setSortOrder((current) => current === "asc" ? "desc" : "asc");
    else { setSortBy(field); setSortOrder("asc"); }
    setPage(1);
  };
  const toggleAll = () => setSelected((current) => current.size === pendingOnPage.length && pendingOnPage.length ? new Set() : new Set(pendingOnPage.map((device) => device.id)));
  const live = (event: LiveEvent) => { if (event.event.startsWith("discovery_")) void refresh(); };

  return <DashboardLayout onLiveEvent={live}>
    <PageTitle eyebrow="Network intelligence" title="Discovery" copy="Find, review, and safely promote devices observed on authorized private networks." action={isAdmin ? <div className="page-actions"><button className="secondary-action" disabled={busy} onClick={() => void exportCsv()}><Icon name="audit"/>Export</button><button className="primary-action" onClick={() => setDialog({kind:"run"})}><Icon name="discovery"/>Run Discovery</button></div> : undefined}/>
    {notice && <Toast key={notice} message={notice} tone={notice.startsWith("Export failed") ? "error" : "success"}/>}
    {stats.loading || stats.error || !stats.data ? <Feedback loading={stats.loading} error={stats.error} onRetry={stats.reload}/> : <section className="discovery-stats stats-grid" aria-label="Discovery summary">
      <StatCard label="Pending" value={stats.data.pending_review} detail="Awaiting administrator review" icon="clock" tone="warning"/>
      <StatCard label="Approved" value={stats.data.approved} detail="Promoted to official inventory" icon="check" tone="success"/>
      <StatCard label="Ignored" value={stats.data.ignored} detail="Retained outside inventory" icon="wifi"/>
      <StatCard label="Rejected" value={stats.data.rejected} detail="Declined with history preserved" icon="warning" tone="danger"/>
      <StatCard label="Last run" value={stats.data.last_run?.status ?? "Never"} detail={stats.data.last_run ? new Date(stats.data.last_run.started_at).toLocaleString() : "No discovery run recorded"} icon="discovery"/>
      <StatCard label="New today" value={stats.data.new_today} detail="First observed since midnight" icon="devices"/>
    </section>}

    <section className="toolbar-panel discovery-toolbar" aria-label="Discovery search and filters">
      <label className="search-field"><Icon name="search"/><input type="search" value={search} placeholder="Search hostname, IP, MAC, or vendor" onChange={(event) => { setSearch(event.target.value); setPage(1); }}/></label>
      <div className="filter-row">
        <select value={status} onChange={(event) => { setStatus(event.target.value as DiscoveryStatus | ""); setPage(1); }} aria-label="Filter network status"><option value="">All network states</option><option value="online">Online</option><option value="offline">Offline</option><option value="unknown">Unknown</option></select>
        <select value={reviewStatus} onChange={(event) => { setReviewStatus(event.target.value as ReviewStatus | ""); setPage(1); }} aria-label="Filter review status"><option value="">All review states</option><option value="pending">Pending</option><option value="approved">Approved</option><option value="ignored">Ignored</option><option value="rejected">Rejected</option></select>
      </div>
    </section>

    {isAdmin && selectedDevices.length > 0 && <div className="bulk-action-bar"><strong>{selectedDevices.length} selected</strong><span>Only pending records can be selected.</span><div><button className="primary-action" onClick={() => setDialog({kind:"approve",devices:selectedDevices})}>Approve</button><button className="secondary-action" onClick={() => setDialog({kind:"ignore",devices:selectedDevices})}>Ignore</button><button className="danger-action" onClick={() => setDialog({kind:"reject",devices:selectedDevices})}>Reject</button></div></div>}

    {records.loading || records.error ? <Feedback loading={records.loading} error={records.error} onRetry={records.reload}/> : !records.data?.items.length ? <Feedback emptyTitle="No discoveries found" empty={search || status || reviewStatus ? "Try clearing or changing the current filters." : "Run Discovery on an authorized private range to begin."}/> : <>
      <section className="data-panel discovery-data-panel" aria-label="Discovered devices"><div className={`data-table discovery-table ${isAdmin ? "is-admin" : ""}`}>
        <div className="table-row table-head" role="row">
          {isAdmin && <span><input type="checkbox" aria-label="Select all pending discoveries on this page" checked={pendingOnPage.length > 0 && selectedDevices.length === pendingOnPage.length} onChange={toggleAll}/></span>}
          <SortHead label="Hostname" field="hostname" active={sortBy} direction={sortOrder} onSort={sort}/><SortHead label="IP" field="ip_address" active={sortBy} direction={sortOrder} onSort={sort}/><SortHead label="MAC" field="mac_address" active={sortBy} direction={sortOrder} onSort={sort}/><SortHead label="Vendor" field="vendor" active={sortBy} direction={sortOrder} onSort={sort}/><SortHead label="Confidence" field="confidence_score" active={sortBy} direction={sortOrder} onSort={sort}/><SortHead label="Status" field="status" active={sortBy} direction={sortOrder} onSort={sort}/><SortHead label="Review" field="review_status" active={sortBy} direction={sortOrder} onSort={sort}/><SortHead label="Seen" field="times_seen" active={sortBy} direction={sortOrder} onSort={sort}/><span>Actions</span>
        </div>
        {records.data.items.map((device) => <div className="table-row discovery-row" role="row" key={device.id}>
          {isAdmin && <span><input type="checkbox" aria-label={`Select ${device.hostname || device.ip_address}`} disabled={device.review_status !== "pending"} checked={selected.has(device.id)} onChange={() => setSelected((current) => { const next = new Set(current); if (next.has(device.id)) next.delete(device.id); else next.add(device.id); return next; })}/></span>}
          <span className="discovery-host"><strong>{device.hostname || "Unresolved host"}</strong><small>{device.device_type_guess || "unknown"}</small></span><span>{device.ip_address}</span><span className="mono-cell">{device.mac_address || "—"}</span><span>{device.vendor || "Unknown"}</span><span><Confidence value={device.confidence_score}/></span><span><StatusBadge status={device.status}/></span><span><StatusBadge status={device.review_status}/></span><span><strong>{device.times_seen}</strong><small>{new Date(device.last_seen_at).toLocaleDateString()}</small></span><span className="discovery-actions"><Link to={`/discovery/${device.id}`} className="secondary-action">View</Link>{isAdmin && device.review_status === "pending" && <><button onClick={() => setDialog({kind:"approve",devices:[device]})} aria-label={`Approve ${device.hostname || device.ip_address}`}><Icon name="check"/></button><button onClick={() => setDialog({kind:"ignore",devices:[device]})} aria-label={`Ignore ${device.hostname || device.ip_address}`}><Icon name="wifi"/></button><button className="reject" onClick={() => setDialog({kind:"reject",devices:[device]})} aria-label={`Reject ${device.hostname || device.ip_address}`}><Icon name="close"/></button></>}</span>
        </div>)}
      </div></section>
      <Pagination current={records.data.page} pages={records.data.pages} onChange={setPage}/>
    </>}

    {dialog?.kind === "approve" && <ApprovalDialog devices={dialog.devices} busy={busy} error={actionError} onClose={closeDialog} onSubmit={approve}/>}
    {dialog?.kind === "run" && <RunDiscoveryDialog busy={busy} error={actionError} onClose={closeDialog} onSubmit={run}/>}
    {dialog?.kind === "reject" && <RejectDialog count={dialog.devices.length} busy={busy} error={actionError} onClose={closeDialog} onSubmit={reject}/>}
    {dialog?.kind === "ignore" && <ConfirmationModal title={dialog.devices.length === 1 ? "Ignore discovery" : `Ignore ${dialog.devices.length} discoveries`} confirmLabel="Ignore" busyLabel="Ignoring…" busy={busy} error={actionError} onCancel={closeDialog} onConfirm={() => void ignore()}><p>Keep {dialog.devices.length === 1 ? <strong>{dialog.devices[0].hostname || dialog.devices[0].ip_address}</strong> : <strong>{dialog.devices.length} selected discoveries</strong>} outside official inventory?</p><p className="confirmation-warning">Observation history will be preserved and no device will be deleted.</p></ConfirmationModal>}
  </DashboardLayout>;
}

function SortHead({label,field,active,direction,onSort}:{label:string;field:string;active:string;direction:"asc"|"desc";onSort:(field:string)=>void}) { return <button className={`sort-head ${active === field ? "active" : ""}`} onClick={() => onSort(field)}>{label}<span>{active === field ? direction === "asc" ? "↑" : "↓" : "↕"}</span></button>; }
function Confidence({value}:{value:number|null}) { const score=Math.round(value??0); return <span className="confidence"><span><i style={{width:`${score}%`}}/></span><strong>{value == null ? "—" : `${score}%`}</strong></span>; }
function Pagination({current,pages,onChange}:{current:number;pages:number;onChange:(page:number)=>void}) { const numbers=Array.from({length:pages},(_,index)=>index+1).filter((value)=>value===1||value===pages||Math.abs(value-current)<=1); return <nav className="pagination" aria-label="Discovery pages"><button className="secondary-action" disabled={current===1} onClick={()=>onChange(current-1)}>Previous</button><div className="page-numbers">{numbers.map((value,index)=><span key={value}>{index>0&&value-numbers[index-1]>1&&<i>…</i>}<button className={value===current?"active":""} aria-current={value===current?"page":undefined} onClick={()=>onChange(value)}>{value}</button></span>)}</div><button className="secondary-action" disabled={current===pages} onClick={()=>onChange(current+1)}>Next</button></nav>; }
function message(error: unknown) { return error instanceof Error ? error.message : "The Discovery request could not be completed."; }
