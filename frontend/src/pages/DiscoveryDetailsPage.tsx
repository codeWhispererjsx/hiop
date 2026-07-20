import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ConfirmationModal } from "../components/ConfirmationModal";
import { ApprovalDialog, RejectDialog } from "../components/DiscoveryDialogs";
import { Feedback } from "../components/Feedback";
import { StatusBadge } from "../components/StatusBadge";
import { Toast } from "../components/Toast";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import type { BulkApprovalItem, LiveEvent } from "../lib/types";
import { PageTitle } from "./DashboardPage";


type Dialog = "approve" | "ignore" | "reject" | null;

export default function DiscoveryDetailsPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const record = useRequest(() => endpoints.discoveryDetail(id), [id]);
  const currentUser = useRequest(endpoints.me, []);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");
  const device = record.data;
  const isAdmin = currentUser.data?.role === "admin";
  const pending = device?.review_status === "pending";
  const close = () => { if (!busy) { setDialog(null); setActionError(""); } };
  const done = async (text: string) => { setDialog(null); setNotice(text); setActionError(""); await record.reload(); };
  const approve = async (items: BulkApprovalItem[]) => {
    setBusy(true); setActionError("");
    try { const result = await endpoints.approveDiscovery(id, items[0].inventory); navigate(`/devices/${result.device.id}`, { state: { notice: "Discovery approved and added to inventory." } }); }
    catch (error) { setActionError(message(error)); } finally { setBusy(false); }
  };
  const ignore = async () => { setBusy(true); setActionError(""); try { await endpoints.ignoreDiscovery(id); await done("Discovery ignored; history remains available."); } catch (error) { setActionError(message(error)); } finally { setBusy(false); } };
  const reject = async (reason?: string) => { setBusy(true); setActionError(""); try { await endpoints.rejectDiscovery(id, reason); await done("Discovery rejected; history remains available."); } catch (error) { setActionError(message(error)); } finally { setBusy(false); } };
  const live = (event: LiveEvent) => { if (event.discovery_id === id) void record.reload(); };

  return <DashboardLayout onLiveEvent={live}>
    <PageTitle eyebrow="Discovery record" title={device?.hostname || device?.ip_address || "Discovery details"} copy="Observation evidence, fingerprint hints, review state, and inventory linkage." action={<div className="page-actions"><Link className="secondary-action" to="/discovery">Back to Discovery</Link>{isAdmin && pending && <><button className="primary-action" onClick={() => setDialog("approve")}>Approve</button><button className="secondary-action" onClick={() => setDialog("ignore")}>Ignore</button><button className="danger-action" onClick={() => setDialog("reject")}>Reject</button></>}</div>}/>
    {notice && <Toast key={notice} message={notice}/>}
    {record.loading || record.error ? <Feedback loading={record.loading} error={record.error} onRetry={record.reload}/> : !device ? <Feedback emptyTitle="Discovery not found" empty="This discovery record is unavailable."/> : <>
      <section className="discovery-detail-hero">
        <div className="discovery-signal"><span className={`signal-orbit ${device.status}`}><i/><i/><b/></span><div><small>Observed identity</small><strong>{device.hostname || "Unresolved host"}</strong><span>{device.ip_address} · {device.mac_address || "MAC unavailable"}</span></div></div>
        <div className="detail-state"><StatusBadge status={device.status}/><StatusBadge status={device.review_status}/>{device.confidence_score != null && <strong>{Math.round(device.confidence_score)}% confidence</strong>}</div>
      </section>
      <section className="discovery-detail-grid">
        <article className="device-details"><header><h2>Identity and fingerprint</h2></header><dl>
          <Detail label="Hostname" value={device.hostname}/><Detail label="IP address" value={device.ip_address}/><Detail label="MAC address" value={device.mac_address}/><Detail label="Vendor hint" value={device.vendor}/><Detail label="Device type guess" value={device.device_type_guess}/><Detail label="OS guess" value={device.operating_system_guess}/><Detail label="Confidence score" value={device.confidence_score == null ? null : `${Math.round(device.confidence_score)}%`}/><Detail label="Discovery method" value={device.discovery_method}/><Detail label="Subnet" value={device.subnet}/><Detail label="Response time" value={device.response_time == null ? null : `${device.response_time} ms`}/>
        </dl></article>
        <article className="device-details"><header><h2>History and review</h2></header><dl>
          <Detail label="First seen" value={formatDate(device.first_seen_at)}/><Detail label="Last seen" value={formatDate(device.last_seen_at)}/><Detail label="Times seen" value={String(device.times_seen)}/><Detail label="Review status" value={device.review_status}/><Detail label="Reviewed at" value={device.reviewed_at ? formatDate(device.reviewed_at) : null}/><Detail label="Reviewer ID" value={device.reviewed_by}/><Detail label="Inventory device" value={device.approved_device_id}/><Detail label="Network zone ID" value={device.network_zone_id}/><Detail label="Notes" value={device.notes}/><Detail label="Discovery ID" value={device.id}/>
        </dl></article>
      </section>
      <div className="fingerprint-notice"><strong>Fingerprinting is advisory.</strong><span>HIOP combines hostname and vendor hints into a confidence score. Confirm the device identity before approval.</span></div>
    </>}
    {dialog === "approve" && device && <ApprovalDialog devices={[device]} busy={busy} error={actionError} onClose={close} onSubmit={approve}/>}
    {dialog === "reject" && <RejectDialog count={1} busy={busy} error={actionError} onClose={close} onSubmit={reject}/>}
    {dialog === "ignore" && device && <ConfirmationModal title="Ignore discovery" confirmLabel="Ignore" busyLabel="Ignoring…" busy={busy} error={actionError} onCancel={close} onConfirm={() => void ignore()}><p>Keep <strong>{device.hostname || device.ip_address}</strong> outside official inventory?</p><p className="confirmation-warning">The record, first and last seen timestamps, and observation count will remain available.</p></ConfirmationModal>}
  </DashboardLayout>;
}

function Detail({label,value}:{label:string;value:string|null|undefined}) { return <div><dt>{label}</dt><dd>{value || "Not recorded"}</dd></div>; }
function formatDate(value:string) { return new Date(value).toLocaleString(); }
function message(error:unknown) { return error instanceof Error ? error.message : "The Discovery request could not be completed."; }
