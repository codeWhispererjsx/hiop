import { FeatureGuide } from "../components/FeatureGuide";
import Modal from "../components/Modal";
import { formatDateTime } from "../lib/dateTime";
import { useEffect, useState } from "react";
import { Feedback } from "../components/Feedback";
import { StatusBadge } from "../components/StatusBadge";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import type { LocalAgent } from "../lib/types";
import { PageTitle } from "./DashboardPage";
import "../styles/local-agents.css";

export default function LocalAgentsPage() {
  const [revokeId,setRevokeId]=useState<string>();
  const [notice,setNotice]=useState("");
  const [actionError,setActionError]=useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<LocalAgent>();
  const [showEnrollModal, setShowEnrollModal] = useState(false);
  const [enrollForm, setEnrollForm] = useState({ name: "", property_id: "", expires_minutes: 15 });
  const [enrolling, setEnrolling] = useState(false);
  const [enrollToken, setEnrollToken] = useState("");
  const [enrollName, setEnrollName] = useState("");
  const [tokenExpiry, setTokenExpiry] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [enrollError, setEnrollError] = useState("");

  const agents = useRequest(() => endpoints.listLocalAgents({ search: search || undefined }), [search]);
  useEffect(() => { const timer=window.setInterval(()=>void agents.reload(),10000); return ()=>window.clearInterval(timer); }, [agents.reload]);
  useEffect(() => { if(!notice)return; const timer=window.setTimeout(()=>setNotice(""),5000); return ()=>window.clearTimeout(timer); }, [notice]);
  const downloadInstaller = async () => {
    setDownloading(true);setActionError("");
    try {
      const file=await endpoints.downloadAgentInstaller();
      const url=URL.createObjectURL(file.blob);
      const link=document.createElement("a");link.href=url;link.download="HIOP-Agent-Windows.zip";link.click();
      window.setTimeout(()=>URL.revokeObjectURL(url),1000);
    } catch(error) {setActionError(error instanceof Error?error.message:"Download failed. Please retry.");}
    finally {setDownloading(false);}
  };
  const properties = useRequest(endpoints.managedProperties, []);
  const activeProperties = properties.data?.filter((property) => property.status === "active") ?? [];
  const selectedPropertyId = enrollForm.property_id || (activeProperties.length === 1 ? activeProperties[0].id : "");

  const handleEnroll = async () => {
    setEnrolling(true);
    setEnrollError("");
    try {
      const result = await endpoints.createAgentEnrollment({ ...enrollForm, property_id: selectedPropertyId });
      setEnrollToken(result.enrollment_token);
      setEnrollName(result.name);
      setTokenExpiry(result.expires_at);
      setShowEnrollModal(false);
      setEnrollForm({ name: "", property_id: "", expires_minutes: 15 });
    } catch (caught) {
      setEnrollError(caught instanceof Error ? caught.message : "Failed to create enrollment");
    } finally {
      setEnrolling(false);
    }
  };

  const handleRevoke = async (agentId: string) => {

    try {
      await endpoints.revokeAgent(agentId);
      setRevokeId(undefined);setNotice("Agent revoked.");void agents.reload();
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "Failed to revoke agent");
    }
  };

  const copyToken = () => {
    void navigator.clipboard.writeText(enrollToken).then(()=>setNotice("Connection code copied.")).catch(()=>setActionError("Could not copy. Select and copy the code manually."));
  };

  return (
    <DashboardLayout>
      {notice&&<p role="status">{notice}</p>}{actionError&&<p role="alert">{actionError}</p>}
      {revokeId&&<Modal title="Revoke local agent?" onClose={()=>setRevokeId(undefined)}><p>This computer will stop sending observations to HIOP. You will need a new enrollment to reconnect it.</p><div className="modal-actions"><button className="secondary-action" onClick={()=>setRevokeId(undefined)}>Keep agent</button><button className="danger-action" onClick={()=>void handleRevoke(revokeId)}>Revoke agent</button></div></Modal>}
      {enrollToken&&<Modal title="Connect this computer" onClose={()=>setEnrollToken("")}>
        <div className="connection-code-modal">
          <p className="connection-code-lead">Copy this connection code, open <strong>Connect HIOP.cmd</strong> from the extracted Windows agent folder, paste the code when the black window asks for it, then press Enter.</p>
          <div className="connection-code-box">
            <span>Connection code</span>
            <code>{enrollToken}</code>
            <button className="primary-action" onClick={copyToken}>Copy connection code</button>
          </div>
          <ol className="connection-steps">
            <li>Download and extract the Windows agent ZIP.</li>
            <li>Open <strong>Connect HIOP.cmd</strong>.</li>
            <li>Wait for <code>Paste your HIOP connection code:</code>.</li>
            <li>Paste the code and press Enter.</li>
            <li>Wait for <code>Connecting...</code> and then <code>Connected.</code></li>
          </ol>
          <p className="settings-note">Waiting for {enrollName || "this computer"} to appear Online. This code expires at {formatDateTime(tokenExpiry)} and can only be used once.</p>
        </div>
      </Modal>}

      <PageTitle
        eyebrow="Administration"
        title="Local Agents"
        copy="Secure local observation and collection agents running inside hotel networks."
        action={
          <button
            className="primary-action"
            onClick={() => setShowEnrollModal(true)}
          >
            Connect a computer
          </button>
        }
      />

      <section className="operational-guide" aria-label="Connect your network">
        <div><span>1. Download</span><strong>Use a Windows computer at your property</strong><p>Install Python 3.12 with its launcher, then download and extract the ZIP. Keep this computer awake and signed in to scan.</p><a href="https://www.python.org/downloads/windows/" target="_blank" rel="noreferrer">Get Python for Windows</a><button className="primary-action" disabled={downloading} onClick={()=>void downloadInstaller()}>{downloading?"Preparing download...":"Download Windows agent"}</button></div>
        <div><span>2. Connect</span><strong>Paste the connection code</strong><p>Select Connect a computer above. Copy the code, open Connect HIOP.cmd, paste it when you see “Paste your HIOP connection code:”, then press Enter.</p></div>
        <div><span>3. Scan</span><strong>Wait for Online below</strong><p>Status refreshes automatically. Once connected, open Network Discovery, select the same property and start a scan. No router port forwarding is needed.</p></div>
      </section>
      <section className="operational-guide" aria-label="How local agents work">
        <div><span>Why it exists</span><strong>Observe the hotel network from inside</strong><p>A hosted HIOP server cannot directly see private hotel networks. A local agent securely sends approved discovery and monitoring observations.</p></div>
        <div><span>How to use it</span><strong>Create enrollment, install, verify</strong><p>Create a short-lived token for the correct property, enroll the agent on-site, then confirm its heartbeat and version here.</p></div>
        <div><span>Security</span><strong>Property-bound and read-only by default</strong><p>An agent cannot submit data for another property and does not provide arbitrary remote command execution.</p></div>
      </section>
      <FeatureGuide kind="agent"/>

      <section className="agents-layout">
        <div className="agents-list">
          <div className="agents-toolbar">
            <label>
              Find agent, property, or hostname
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search agents..."
              />
            </label>
          </div>

          {agents.loading || agents.error ? (
            <Feedback loading={agents.loading} error={agents.error} onRetry={agents.reload} />
          ) : !agents.data || !Array.isArray(agents.data) || agents.data.length === 0 ? (
            <Feedback emptyTitle="No agents found" empty="No local agents are registered for your properties." />
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Agent Name</th>
                  <th>Computer ID</th>
                  <th>Property</th>
                  <th>Status</th>
                  <th>Version</th>
                  <th>Last Seen</th>
                  <th>Queue</th>
                </tr>
              </thead>
              <tbody>
                {agents.data.map((agent: LocalAgent) => (
                  <tr
                    key={agent.id}
                    className={selected?.id === agent.id ? "selected" : ""}
                    onClick={() => setSelected(agent)}
                  >
                    <td>
                      <strong>{agent.name}</strong>
                      {agent.hostname && <small>{agent.hostname}</small>}
                    </td>
                    <td><code>{agent.agent_id}</code></td>
                    <td>{properties.data?.find(property=>property.id===agent.property_id)?.name ?? "Assigned property"}</td>
                    <td><StatusBadge status={agent.status} /></td>
                    <td>{agent.version || "Unknown"}</td>
                    <td>{agent.last_heartbeat ? formatDateTime(agent.last_heartbeat) : "Never"}</td>
                    <td>
                      {agent.pending_queue}/{agent.queue_capacity}
                      {agent.pending_queue > agent.queue_capacity * 0.8 && <span className="warning">Near capacity</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <aside className="agent-detail">
          {!selected ? (
            <div className="agent-empty">
              <strong>Select an agent</strong>
              <span>View details, status, and management options.</span>
            </div>
          ) : (
            <>
              <header>
                <span>Agent Details</span>
                <h2>{selected.name}</h2>
                <StatusBadge status={selected.status} />
              </header>
              <dl>
                <Detail label="Computer ID" value={selected.agent_id} />
                <Detail label="Property" value={properties.data?.find(property=>property.id===selected.property_id)?.name ?? "Assigned property"} />
                <Detail label="Hostname" value={selected.hostname || "Unknown"} />
                <Detail label="Version" value={selected.version || "Unknown"} />
                <Detail label="Last Heartbeat" value={selected.last_heartbeat ? formatDateTime(selected.last_heartbeat) : "Never"} />
                <Detail label="Last Discovery" value={selected.last_discovery ? formatDateTime(selected.last_discovery) : "Never"} />
                <Detail label="Last Monitoring" value={selected.last_monitoring ? formatDateTime(selected.last_monitoring) : "Never"} />
                <Detail label="Uptime" value={selected.uptime_seconds ? `${Math.floor(selected.uptime_seconds / 3600)}h` : "Unknown"} />
                <Detail label="Pending Queue" value={`${selected.pending_queue}/${selected.queue_capacity}`} />
                <Detail label="Registered" value={formatDateTime(selected.registered_at)} />
              </dl>
              <div className="agent-actions">
                {selected.status !== "revoked" && (
                  <button className="danger-action" onClick={() => setRevokeId(selected.id)}>
                    Revoke Agent
                  </button>
                )}
              </div>
            </>
          )}
        </aside>
      </section>

      {showEnrollModal && (
        <Modal title="Connect a local agent" onClose={()=>{if(!enrolling)setShowEnrollModal(false)}}><div className="quick-navigation">
            {enrollError && <div className="error-message">{enrollError}</div>}
            <div className="form-group">
              <label>Computer Name *</label>
              <input
                type="text"
                value={enrollForm.name}
                onChange={(e) => setEnrollForm({ ...enrollForm, name: e.target.value })}
                placeholder="e.g., Front Desk Computer"
              />
            </div>
            <div className="form-group">
              <label>Property *</label>
              <select
                value={selectedPropertyId}
                onChange={(e) => setEnrollForm({ ...enrollForm, property_id: e.target.value })}
                disabled={properties.loading || Boolean(properties.error)}
              >
                <option value="">{properties.loading ? "Loading properties…" : "Select property..."}</option>
                {activeProperties.map((prop) => (
                  <option key={prop.id} value={prop.id}>{prop.name}</option>
                ))}
              </select>
              {properties.error && <small className="field-error">{properties.error}</small>}
              {!properties.loading && !properties.error && !activeProperties.length && <small className="field-error">No active property is available. Activate or create a property first.</small>}
            </div>
            <div className="form-group">
              <label>Code Expires In (minutes) *</label>
              <input
                type="number"
                min="5"
                max="60"
                value={enrollForm.expires_minutes}
                onChange={(e) => setEnrollForm({ ...enrollForm, expires_minutes: parseInt(e.target.value) })}
              />
              <small>Connection codes are one-time and expire after this period.</small>
            </div>
            <div className="modal-footer">
              <button onClick={() => setShowEnrollModal(false)} disabled={enrolling}>
                Cancel
              </button>
              <button className="primary-action" onClick={handleEnroll} disabled={enrolling || !enrollForm.name || !selectedPropertyId}>
                {enrolling ? "Creating..." : "Create connection code"}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </DashboardLayout>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
