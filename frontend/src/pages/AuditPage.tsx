/* eslint-disable react-hooks/set-state-in-effect */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Feedback } from "../components/Feedback";
import { Icon, type IconName } from "../components/Icon";
import Modal from "../components/Modal";
import { Toast } from "../components/Toast";
import DashboardLayout from "../layouts/DashboardLayout";
import { ApiError, endpoints } from "../lib/api";
import type { AuditFilters, AuditLog, AuditLogPage } from "../lib/types";
import { PageTitle } from "./DashboardPage";

const EMPTY_FILTERS = { actor: "", action: "", entity_type: "", start_date: "", end_date: "", sort_order: "desc" as const };

function readableAction(action: string) {
  const verbs: Record<string, string> = { CREATE: "Created", CREATED: "Created", UPDATE: "Updated", UPDATED: "Updated", RETIRE: "Retired", ASSIGN: "Assigned", CLOSE: "Closed", DELETE: "Deleted", ACKNOWLEDGE: "Acknowledged", DEACTIVATE: "Deactivated", ACTIVATED: "Activated", ROLE: "Changed role for", PASSWORD: "Reset password for", SCAN: "Scanned" };
  const words = action.split("_");
  const verb = words.find((word) => verbs[word]);
  if (!verb) return words.map((word) => word.toLowerCase()).join(" ").replace(/^./, (value) => value.toUpperCase());
  const subject = words.filter((word) => word !== verb && !["USER", "DEVICE", "TICKET", "ALERT"].includes(word)).join(" ").toLowerCase();
  const entity = words.find((word) => ["USER", "DEVICE", "TICKET", "ALERT"].includes(word))?.toLowerCase() ?? subject;
  return `${verbs[verb]} ${entity}`.trim();
}

function relatedPath(log: AuditLog) {
  const type = log.entity_type.toLowerCase();
  if (type === "device") return `/devices/${log.entity_id}`;
  if (type === "user") return `/users/${log.entity_id}`;
  return null;
}

function toApiFilters(filters: typeof EMPTY_FILTERS, search: string, page: number, pageSize: number): AuditFilters {
  const start = filters.start_date ? new Date(`${filters.start_date}T00:00:00`).toISOString() : undefined;
  const end = filters.end_date ? new Date(`${filters.end_date}T23:59:59.999`).toISOString() : undefined;
  return { search: search.trim() || undefined, actor: filters.actor || undefined, action: filters.action || undefined, entity_type: filters.entity_type || undefined, start_date: start, end_date: end, sort_order: filters.sort_order, page, page_size: pageSize };
}

export default function AuditPage() {
  const [data, setData] = useState<AuditLogPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<AuditLog | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [exporting, setExporting] = useState(false);
  const [notice, setNotice] = useState("");
  const [dateError, setDateError] = useState("");
  const requestId = useRef(0);

  useEffect(() => { const timer = window.setTimeout(() => { setDebouncedQuery(query); setPage(1); }, 300); return () => window.clearTimeout(timer); }, [query]);
  const apiFilters = useMemo(() => toApiFilters(filters, debouncedQuery, page, pageSize), [filters, debouncedQuery, page, pageSize]);
  const load = useCallback(async (quiet = false) => {
    if (filters.start_date && filters.end_date && filters.start_date > filters.end_date) { setDateError("Start date must be before or equal to end date."); setLoading(false); return; }
    const currentRequest = ++requestId.current;
    setDateError(""); setError("");
    if (quiet) setRefreshing(true); else setLoading(true);
    try { const response = await endpoints.auditLogs(apiFilters); if (currentRequest === requestId.current) setData(response); }
    catch (caught) { if (currentRequest === requestId.current) setError(caught instanceof Error ? caught.message : "Audit records could not be loaded."); }
    finally { if (currentRequest === requestId.current) { setLoading(false); setRefreshing(false); } }
  }, [apiFilters, filters.start_date, filters.end_date]);
  useEffect(() => { void load(); }, [load]);

  const setFilter = (key: keyof typeof EMPTY_FILTERS, value: string) => { setFilters((current) => ({ ...current, [key]: value })); setPage(1); };
  const resetFilters = () => { setQuery(""); setDebouncedQuery(""); setFilters(EMPTY_FILTERS); setPage(1); setDateError(""); };
  const openDetails = async (id: string) => { setSelectedId(id); setSelected(null); setDetailError(""); setDetailLoading(true); try { setSelected(await endpoints.auditLog(id)); } catch (caught) { setDetailError(caught instanceof Error ? caught.message : "Audit record could not be loaded."); } finally { setDetailLoading(false); } };
  const exportLogs = async () => { setExporting(true); setNotice(""); try { const exportFilters = { ...apiFilters }; delete exportFilters.page; delete exportFilters.page_size; const result = await endpoints.exportAuditLogs(exportFilters); const url = URL.createObjectURL(result.blob); const link = document.createElement("a"); link.href = url; link.download = result.filename; link.click(); URL.revokeObjectURL(url); setNotice(`Exported ${data?.total ?? 0} filtered audit events.`); } catch (caught) { setNotice(caught instanceof ApiError ? caught.message : "Audit export failed."); } finally { setExporting(false); } };

  const summary: Array<{ label: string; value: number; icon: IconName; tone: string }> = data ? [
    { label: "Total events", value: data.summary.total, icon: "audit", tone: "gold" }, { label: "Events today", value: data.summary.today, icon: "clock", tone: "success" }, { label: "User actions", value: data.summary.user_actions, icon: "users", tone: "gold" }, { label: "Device actions", value: data.summary.device_actions, icon: "devices", tone: "success" }, { label: "Ticket actions", value: data.summary.ticket_actions, icon: "tickets", tone: "muted" }, { label: "Security events", value: data.summary.security_events, icon: "lock", tone: "warning" },
  ] : [];

  return <DashboardLayout>
    <div className="page-title-row audit-title-row"><PageTitle eyebrow="Governance" title="Audit center" copy="Search, review, and export immutable accountability records generated by HIOP operations." /><div className="audit-page-actions"><button className="secondary-action" disabled={refreshing} onClick={() => void load(true)}><Icon name="clock" size={15} />{refreshing ? "Refreshing…" : "Refresh"}</button><button className="primary-action" disabled={exporting || !data?.total || Boolean(dateError)} onClick={() => void exportLogs()}><Icon name="arrow" size={15} />{exporting ? "Exporting…" : "Export filtered CSV"}</button></div></div>
    {notice && <Toast message={notice} tone={notice.includes("failed") ? "error" : undefined} />}
    {summary.length > 0 && <section className="audit-summary" aria-label="Audit summary">{summary.map((item) => <article className={`audit-stat ${item.tone}`} key={item.label}><span><Icon name={item.icon} size={17} /></span><div><small>{item.label}</small><strong>{item.value}</strong></div></article>)}</section>}

    <section className="panel audit-center-panel">
      <header className="audit-filter-head"><div><h2>Audit events</h2><p>{data ? `${data.total} filtered results` : "Loading secure history"}</p></div><button className="audit-reset" disabled={!query && Object.entries(filters).every(([key, value]) => key === "sort_order" ? value === "desc" : !value)} onClick={resetFilters}>Reset filters</button></header>
      <div className="audit-filters">
        <label className="audit-search"><Icon name="search" size={16} /><input aria-label="Search audit events" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search actor, action, entity, ID, or description" /></label>
        <select aria-label="Filter by actor" value={filters.actor} onChange={(event) => setFilter("actor", event.target.value)}><option value="">All actors</option>{data?.options.actors.map((value) => <option key={value}>{value}</option>)}</select>
        <select aria-label="Filter by action" value={filters.action} onChange={(event) => setFilter("action", event.target.value)}><option value="">All actions</option>{data?.options.actions.map((value) => <option key={value}>{readableAction(value)}</option>)}</select>
        <select aria-label="Filter by entity type" value={filters.entity_type} onChange={(event) => setFilter("entity_type", event.target.value)}><option value="">All entities</option>{data?.options.entity_types.map((value) => <option key={value}>{value}</option>)}</select>
        <label className="audit-date"><span>From</span><input type="date" value={filters.start_date} onChange={(event) => setFilter("start_date", event.target.value)} /></label>
        <label className="audit-date"><span>To</span><input type="date" value={filters.end_date} onChange={(event) => setFilter("end_date", event.target.value)} /></label>
        <select aria-label="Sort audit events" value={filters.sort_order} onChange={(event) => setFilter("sort_order", event.target.value)}><option value="desc">Newest first</option><option value="asc">Oldest first</option></select>
      </div>
      {dateError && <div className="audit-validation"><Icon name="warning" size={16} />{dateError}</div>}

      {loading || error || !data?.items.length ? <Feedback loading={loading} error={error || undefined} empty={data?.total === 0 && (query || filters.actor || filters.action || filters.entity_type || filters.start_date || filters.end_date) ? "No audit events match the active filters." : "No audit records have been generated yet."} onRetry={() => void load()} /> : <div className="audit-table-wrap"><table className="audit-table"><thead><tr><th>Timestamp</th><th>Actor</th><th>Action</th><th>Entity</th><th>Description</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{data.items.map((log) => <tr key={log.id}><td data-label="Timestamp"><time>{new Date(log.created_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}</time></td><td data-label="Actor"><span className="audit-actor"><Icon name="users" size={13} />{log.actor || "System"}</span></td><td data-label="Action"><span className="audit-action">{readableAction(log.action)}</span></td><td data-label="Entity"><span className={`audit-entity entity-${log.entity_type.toLowerCase()}`}>{log.entity_type}</span><small>{log.entity_id}</small></td><td data-label="Description"><p>{log.description}</p></td><td className="audit-row-action"><button onClick={() => void openDetails(log.id)}>Details <Icon name="arrow" size={13} /></button></td></tr>)}</tbody></table></div>}

      {data && data.total > 0 && <footer className="audit-pagination"><label>Rows<select aria-label="Rows per page" value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1); }}><option value="25">25</option><option value="50">50</option><option value="100">100</option></select></label><span>Page {data.page} of {data.pages} · {data.total} results</span><div><button disabled={data.page <= 1} onClick={() => setPage((value) => value - 1)}>Previous</button><button disabled={data.page >= data.pages} onClick={() => setPage((value) => value + 1)}>Next</button></div></footer>}
    </section>

    {selectedId && <Modal title="Audit event details" onClose={() => setSelectedId(null)}><div className="audit-detail-body">{detailLoading || detailError || !selected ? <Feedback loading={detailLoading} error={detailError || undefined} empty="Audit record not found." /> : <><header className="audit-detail-hero"><span><Icon name="audit" size={21} /></span><div><small>Immutable audit record</small><h3>{readableAction(selected.action)}</h3><p>{selected.description}</p></div></header><dl className="audit-detail-grid"><div><dt>Audit ID</dt><dd>{selected.id}</dd></div><div><dt>Timestamp</dt><dd>{new Date(selected.created_at).toLocaleString()}</dd></div><div><dt>Actor</dt><dd>{selected.actor || "System"}</dd></div><div><dt>Stored action</dt><dd><code>{selected.action}</code></dd></div><div><dt>Entity type</dt><dd>{selected.entity_type}</dd></div><div><dt>Entity ID</dt><dd>{selected.entity_id}</dd></div></dl>{relatedPath(selected) ? <Link className="primary-action audit-related-link" to={relatedPath(selected)!}>Open related {selected.entity_type.toLowerCase()}<Icon name="arrow" size={14} /></Link> : <div className="audit-related-unavailable"><Icon name="lock" size={15} />No safe related-record route is available for this historical event.</div>}</>}</div></Modal>}
  </DashboardLayout>;
}
