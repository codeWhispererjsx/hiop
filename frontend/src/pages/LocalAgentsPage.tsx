import { FeatureGuide } from "../components/FeatureGuide";
import Modal from "../components/Modal";
import { formatDateTime } from "../lib/dateTime";
import { useEffect, useState } from "react";
import { Feedback } from "../components/Feedback";
import { StatusBadge } from "../components/StatusBadge";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import { Link } from "react-router-dom";
import type { LocalAgent } from "../lib/types";
import { PageTitle } from "./DashboardPage";
import "../styles/local-agents.css";

export default function LocalAgentsPage() {
  const [revokeId,setRevokeId]=useState<string>();
  const [notice,setNotice]=useState("");
  const [actionError,setActionError]=useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [departmentFilter, setDepartmentFilter] = useState("all");
  const [locationFilter, setLocationFilter] = useState("all");
  const [uptimeFilter, setUptimeFilter] = useState(false);
  const [selected, setSelected] = useState<LocalAgent>();
  const [commandAgentId, setCommandAgentId] = useState<string>();
  const [commandNotice, setCommandNotice] = useState("");
  const [showEnrollModal, setShowEnrollModal] = useState(false);
  const [enrollForm, setEnrollForm] = useState({ name: "", property_id: "", expires_minutes: 15 });
  const [enrolling, setEnrolling] = useState(false);
  const [enrollToken, setEnrollToken] = useState("");
  const [enrollName, setEnrollName] = useState("");
  const [tokenExpiry, setTokenExpiry] = useState("");
  const [enrollError, setEnrollError] = useState("");

  const agents = useRequest(endpoints.listLocalAgents, []);
  const reloadAgents = agents.reload;
  const history = useRequest(
    () => selected ? endpoints.getAgentHistory(selected.id) : Promise.resolve([]),
    [selected?.id],
  );
  const metrics = useRequest(
    () => selected ? endpoints.getAgentMetrics(selected.id) : Promise.resolve([]),
    [selected?.id],
  );
  const rows = Array.isArray(agents.data) ? agents.data : [];
  const onlineCount = rows.filter((agent) => agent.status === "online").length;
  const offlineCount = rows.filter((agent) => agent.status === "offline" || agent.status === "stale").length;
  const attentionCount = rows.filter((agent) => (agent.uptime_seconds ?? 0) > 48 * 60 * 60).length;
  const departments = [...new Set(rows.map((agent) => agent.department).filter((value): value is string => Boolean(value)))].sort();
  const locations = [...new Set(rows.map((agent) => agent.location).filter((value): value is string => Boolean(value)))].sort();
  const visibleAgents = rows.filter((agent) => {
    const term = search.trim().toLowerCase();
    const textMatch = !term || [agent.hostname, agent.name, agent.logged_user, agent.ip_address, agent.department, agent.location]
      .some((value) => value?.toLowerCase().includes(term));
    const statusMatch = statusFilter === "all" || agent.status === statusFilter;
    const departmentMatch = departmentFilter === "all" || agent.department === departmentFilter;
    const locationMatch = locationFilter === "all" || agent.location === locationFilter;
    const uptimeMatch = !uptimeFilter || (agent.uptime_seconds ?? 0) > 48 * 60 * 60;
    return textMatch && statusMatch && departmentMatch && locationMatch && uptimeMatch;
  });
  useEffect(() => { const timer=window.setInterval(()=>void reloadAgents(),10000); return ()=>window.clearInterval(timer); }, [reloadAgents]);
  useEffect(() => { if(!notice)return; const timer=window.setTimeout(()=>setNotice(""),5000); return ()=>window.clearTimeout(timer); }, [notice]);
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

  const runAction = async (agent: LocalAgent, action: "RESTART" | "SHUTDOWN" | "ENABLE_RDP" | "DISABLE_RDP" | "TRIGGER_WINDOWS_UPDATE") => {
    if (!agent.device_id) {
      setActionError("Link this agent to a managed Windows device before sending actions.");
      return;
    }
    const labels = {RESTART:"restart",SHUTDOWN:"shut down",ENABLE_RDP:"enable Remote Desktop",DISABLE_RDP:"disable Remote Desktop",TRIGGER_WINDOWS_UPDATE:"start a Windows Update scan"};
    if (!window.confirm(`Send a command to ${agent.hostname || agent.name} to ${labels[action]}?`)) return;
    setCommandAgentId(agent.id);
    setCommandNotice(`Command sent to ${agent.hostname || agent.name}. Waiting for the agent...`);
    setActionError("");
    try {
      const queued = await endpoints.createDeviceAgentAction(agent.device_id, action);
      for (let attempt = 0; attempt < 24; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 5000));
        const job = await endpoints.getAgentJobStatus(queued.id);
        if (job.status === "completed") {
          setCommandNotice(`${labels[action]} command completed on ${agent.hostname || agent.name}.`);
          void history.reload();
          return;
        }
        if (["failed", "timed_out", "cancelled"].includes(job.status)) {
          throw new Error(job.error || `The command ${job.status.replaceAll("_", " ")}.`);
        }
      }
      setCommandNotice(`Command is still queued for ${agent.hostname || agent.name}. Check history for the final result.`);
      void history.reload();
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "The command failed.");
      setCommandNotice("");
      void history.reload();
    } finally {
      setCommandAgentId(undefined);
    }
  };

  const wakeAgent = async (agent: LocalAgent) => {
    if (!agent.device_id || !window.confirm(`Send a Wake-on-LAN packet to ${agent.hostname || agent.name}?`)) return;
    setActionError("");
    try {
      await endpoints.wakeDevice(agent.device_id);
      setCommandNotice(`Wake-on-LAN packet sent to ${agent.hostname || agent.name}. Network equipment must allow it.`);
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "Wake-on-LAN failed.");
    }
  };

  const copyRdpCommand = async (agent: LocalAgent) => {
    if (!agent.ip_address) {
      setActionError("This agent has not reported an IP address.");
      return;
    }
    try {
      await navigator.clipboard.writeText(`mstsc /v:${agent.ip_address}`);
      setNotice("Native RDP command copied. The operator must be able to reach this PC.");
    } catch {
      setActionError("Could not copy the RDP command.");
    }
  };

  const copyToken = () => {
    void navigator.clipboard.writeText(enrollToken).then(()=>setNotice("Connection code copied.")).catch(()=>setActionError("Could not copy. Select and copy the code manually."));
  };

  return (
    <DashboardLayout>
      {notice&&<p role="status">{notice}</p>}{commandNotice&&<p className="agent-command-pending" role="status">{commandAgentId&&<span className="agent-command-spinner" aria-hidden="true"/>}{commandNotice}</p>}{actionError&&<p role="alert">{actionError}</p>}
      {revokeId&&<Modal title="Revoke local agent?" onClose={()=>setRevokeId(undefined)}><p>This computer will stop sending observations to HIOP. You will need a new enrollment to reconnect it.</p><div className="modal-actions"><button className="secondary-action" onClick={()=>setRevokeId(undefined)}>Keep agent</button><button className="danger-action" onClick={()=>void handleRevoke(revokeId)}>Revoke agent</button></div></Modal>}
      {enrollToken&&<Modal title="Connect this computer" onClose={()=>setEnrollToken("")}>
        <div className="connection-code-modal">
          <p className="connection-code-lead">Copy this one-time code, install the Windows agent if needed, then open the <strong>HIOP Agent</strong> tray icon and choose <strong>Connect or enroll...</strong>.</p>
          <div className="connection-code-box">
            <span>Connection code</span>
            <code>{enrollToken}</code>
            <button className="primary-action" onClick={copyToken}>Copy connection code</button>
          </div>
          <ol className="connection-steps">
            <li>Download and extract the Windows agent package.</li>
            <li>Run <strong>Install HIOP Agent.cmd</strong> and approve the Windows administrator prompt.</li>
            <li>Open the <strong>HIOP Agent</strong> tray icon and select <strong>Connect or enroll...</strong>.</li>
            <li>Paste the code in the native agent window and choose Connect.</li>
            <li>Wait for the agent to appear Online below.</li>
          </ol>
          <p className="settings-note">Waiting for {enrollName || "this computer"} to appear Online. This code expires at {formatDateTime(tokenExpiry)} and can only be used once.</p>
        </div>
      </Modal>}

      <PageTitle
        eyebrow="Administration"
        title="Agents - Managed Endpoints"
        copy="Track enrolled Windows computers, connectivity, inventory links, and recent agent commands. Agent actions are available only for an online agent securely linked to a managed Windows device."
        action={
          <div className="page-title-actions">
            <Link className="secondary-action" to="/download">Download Windows agent</Link>
            <button
              className="primary-action"
              onClick={() => setShowEnrollModal(true)}
            >
              Connect a computer
            </button>
          </div>
        }
      />

      <section className="agent-summary-grid" aria-label="Agent fleet status">
        <article><span>Total agents</span><strong>{rows.length}</strong><small>Registered endpoints</small></article>
        <article className="agent-summary-online"><span>Online now</span><strong>{onlineCount}</strong><small>Heartbeat received recently</small></article>
        <article className="agent-summary-offline"><span>Offline</span><strong>{offlineCount}</strong><small>Offline or heartbeat is stale</small></article>
        <article className="agent-summary-attention"><span>Needs attention</span><strong>{attentionCount}</strong><small>Uptime is over 48 hours</small></article>
      </section>

      <section className="operational-guide" aria-label="Connect your network">
        <div><span>1. Download</span><strong>Install the native Windows agent</strong><p>Download and extract the package, then run Install HIOP Agent.cmd and approve the administrator prompt. The service starts automatically and the tray app shows its status. No Python installation is required.</p><Link className="primary-action" to="/download">Download Windows agent</Link></div>
        <div><span>2. Connect</span><strong>Use a one-time HIOP code</strong><p>Select Connect a computer above. From the HIOP Agent tray icon choose Connect or enroll..., then paste the one-time code. It is bound to the property selected in HIOP and expires shortly.</p></div>
        <div><span>3. Scan and reconcile</span><strong>Keep inventory up to date</strong><p>Run a discovery scan for the same property and a network range containing the agent computer. HIOP links unambiguous matches to existing inventory and refreshes their technical/network details; unmatched or conflicting devices stay in Discovery for review before being added.</p></div>
      </section>
      <section className="operational-guide" aria-label="How local agents work">
        <div><span>Why it exists</span><strong>Observe the hotel network from inside</strong><p>A hosted HIOP server cannot directly see private hotel networks. A local agent securely sends approved discovery and monitoring observations. Agent-brokered remote desktop is not available; Native RDP is launched from the device page and requires direct network access.</p></div>
        <div><span>How to use it</span><strong>Install, enroll, verify</strong><p>After installation, create a short-lived code for the correct property and enroll from the tray app. To update an enrolled agent, run Install HIOP Agent.cmd from a fresh package; its registration and local queue are preserved. To remove it, run Remove HIOP Agent.cmd.</p></div>
        <div><span>Security</span><strong>Property-bound and restricted</strong><p>Credentials are machine-protected and enrollment is one-time. The service accepts allowlisted discovery, monitoring, and fixed Windows actions only; it does not accept arbitrary commands. Restart and shutdown are scheduled 60 seconds ahead. Lock requires an interactive signed-in session with the tray app running.</p></div>
      </section>
      <FeatureGuide kind="agent"/>

      <section className="agents-layout">
        <div className="agents-list">
          <div className="agents-toolbar">
            <label>
              Find hostname, staff, department, or IP
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search managed endpoints..."
              />
            </label>
            <label>
              Status
              <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                <option value="all">All statuses</option>
                <option value="online">Online</option>
                <option value="stale">Needs attention</option>
                <option value="offline">Offline</option>
                <option value="pending">Pending</option>
                <option value="revoked">Revoked</option>
              </select>
            </label>
            <label>
              Department
              <select value={departmentFilter} onChange={(event) => setDepartmentFilter(event.target.value)}>
                <option value="all">All departments</option>
                {departments.map((department) => <option key={department} value={department}>{department}</option>)}
              </select>
            </label>
            <label>
              Location
              <select value={locationFilter} onChange={(event) => setLocationFilter(event.target.value)}>
                <option value="all">All locations</option>
                {locations.map((location) => <option key={location} value={location}>{location}</option>)}
              </select>
            </label>
            <label className="agent-uptime-filter">
              <input type="checkbox" checked={uptimeFilter} onChange={(event) => setUptimeFilter(event.target.checked)} />
              Uptime over 48 hours
            </label>
          </div>

          {agents.loading || agents.error ? (
            <Feedback loading={agents.loading} error={agents.error} onRetry={agents.reload} />
          ) : rows.length === 0 ? (
            <div className="agent-empty-state">
              <span className="agent-empty-icon">H</span>
              <h2>No agents yet</h2>
              <p>Install the Windows agent on a company computer, then connect it with a one-time enrollment code.</p>
              <Link className="primary-action" to="/download">Download Windows agent</Link>
              <button className="secondary-action" onClick={() => setShowEnrollModal(true)}>Create enrollment code</button>
              <small>Only use enrollment codes generated by an HIOP administrator.</small>
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Status</th>
                  <th>Hostname</th>
                  <th>Assigned To / Logged-in User</th>
                  <th>Department</th>
                  <th>Location</th>
                  <th>Floor</th>
                  <th>IP</th>
                  <th>Last seen</th>
                  <th>Last update</th>
                  <th>Uptime</th>
                  <th>Version</th>
                  <th>Inventory</th>
                  <th>Property</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {visibleAgents.map((agent: LocalAgent) => (
                  <tr
                    key={agent.id}
                    className={selected?.id === agent.id ? "selected" : ""}
                    onClick={() => setSelected(agent)}
                  >
                    <td><StatusBadge status={agent.status} /></td>
                    <td><strong>{agent.hostname || agent.name}</strong></td>
                    <td>{agent.logged_user || "—"}</td>
                    <td>{agent.department || "—"}</td>
                    <td>{agent.location || "—"}</td>
                    <td>{agent.floor || "—"}</td>
                    <td>{agent.ip_address || "—"}</td>
                    <td>{agent.last_heartbeat ? formatDateTime(agent.last_heartbeat) : "Never"}</td>
                    <td>{agent.last_update ? formatDateTime(agent.last_update) : "—"}</td>
                    <td className={(agent.uptime_seconds ?? 0) > 48 * 60 * 60 ? "agent-uptime-warning" : ""}>{formatUptime(agent.uptime_seconds)}</td>
                    <td>{agent.version || "Unknown"}</td>
                    <td onClick={(event) => event.stopPropagation()}>
                      {agent.managed_asset_id
                        ? <Link to={`/assets/${agent.managed_asset_id}`}>{agent.managed_asset_name || "Managed asset"}</Link>
                        : agent.device_id
                          ? <Link to={`/devices/${agent.device_id}`}>Device linked</Link>
                          : "Not linked"}
                    </td>
                    <td>{properties.data?.find(property=>property.id===agent.property_id)?.name ?? "Assigned property"}</td>
                    <td className="agent-row-actions" onClick={(event) => event.stopPropagation()}>
                      <button disabled={agent.status !== "online" || !agent.device_id || commandAgentId === agent.id} onClick={() => void runAction(agent, "RESTART")}>Restart</button>
                      <button disabled={agent.status !== "online" || !agent.device_id || commandAgentId === agent.id} onClick={() => void runAction(agent, "SHUTDOWN")}>Shutdown</button>
                      <button disabled={agent.status !== "online" || !agent.device_id || commandAgentId === agent.id} onClick={() => void runAction(agent, "ENABLE_RDP")}>Enable RDP</button>
                      <button disabled={agent.status !== "online" || !agent.device_id || commandAgentId === agent.id} onClick={() => void runAction(agent, "DISABLE_RDP")}>Disable RDP</button>
                      <button disabled={agent.status !== "online" || !agent.device_id || commandAgentId === agent.id} onClick={() => void runAction(agent, "TRIGGER_WINDOWS_UPDATE")}>Update scan</button>
                      <button disabled={!agent.device_id || !agent.mac_address} onClick={() => void wakeAgent(agent)}>Wake</button>
                      <button disabled={!agent.ip_address} onClick={() => void copyRdpCommand(agent)}>Copy RDP</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {rows.length > 0 && visibleAgents.length === 0 && <p className="agent-no-matches">No agents match these filters.</p>}
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
                <Detail label="IP address" value={selected.ip_address || "Not reported"} />
                <Detail label="Department" value={selected.department || "Not assigned"} />
                <Detail label="Location" value={selected.location || "Not assigned"} />
                <Detail label="Floor" value={selected.floor || "Not assigned"} />
                <Detail label="Operating system" value={selected.operating_system || "Not reported"} />
                <Detail label="Logged-in user" value={selected.logged_user || "Not reported"} />
                <Detail label="Version" value={selected.version || "Unknown"} />
                <Detail label="Last Heartbeat" value={selected.last_heartbeat ? formatDateTime(selected.last_heartbeat) : "Never"} />
                <Detail label="Last Discovery" value={selected.last_discovery ? formatDateTime(selected.last_discovery) : "Never"} />
                <Detail label="Last Monitoring" value={selected.last_monitoring ? formatDateTime(selected.last_monitoring) : "Never"} />
                <Detail label="Uptime" value={selected.uptime_seconds ? `${Math.floor(selected.uptime_seconds / 3600)}h` : "Unknown"} />
                <Detail label="CPU" value={selected.cpu_percent === null ? "Not reported" : `${Math.round(selected.cpu_percent)}%`} />
                <Detail label="Memory" value={selected.memory_total_bytes ? `${formatBytes(selected.memory_total_bytes - (selected.memory_free_bytes ?? 0))} used / ${formatBytes(selected.memory_total_bytes)} total` : "Not reported"} />
                <Detail label="Disk free" value={selected.disk_free_bytes === null ? "Not reported" : formatBytes(selected.disk_free_bytes)} />
                <Detail label="Last Windows update" value={selected.last_update ? formatDateTime(selected.last_update) : "Not reported"} />
                <Detail label="Pending Queue" value={`${selected.pending_queue}/${selected.queue_capacity}`} />
                <Detail label="Registered" value={formatDateTime(selected.registered_at)} />
              </dl>
                <section className="agent-history">
                  <h3>Recent command history</h3>
                  {history.loading ? <p>Loading history...</p> : history.error ? <Feedback error={history.error} onRetry={history.reload} /> : history.data?.length ? history.data.map((job) => (
                    <article key={job.id}>
                      <strong>{job.action || job.job_type.replaceAll("_", " ")}</strong>
                      <StatusBadge status={job.status} />
                      <small>{formatDateTime(job.created_at)}</small>
                      {job.error && <p>{job.error}</p>}
                    </article>
                  )) : <p>No recent commands.</p>}
                </section>
                <section className="agent-history">
                  <h3>Endpoint health · last 7 days</h3>
                  {metrics.loading ? <p>Loading uptime history...</p> : metrics.error ? <Feedback error={metrics.error} onRetry={metrics.reload} /> : metrics.data?.length ? <MetricChart values={metrics.data.map((sample) => sample.uptime_seconds ?? 0)} /> : <p>Uptime history starts after the agent has checked in for at least five minutes.</p>}
                </section>
              <div className="agent-actions">
                {selected.status === "online" && selected.device_id && (
                  <div className="agent-command-buttons">
                    <button className="secondary-action" disabled={commandAgentId === selected.id} onClick={() => void runAction(selected, "RESTART")}>Restart</button>
                    <button className="secondary-action" disabled={commandAgentId === selected.id} onClick={() => void runAction(selected, "SHUTDOWN")}>Shutdown / Cool Off</button>
                    <button className="secondary-action" disabled={commandAgentId === selected.id} onClick={() => void runAction(selected, "ENABLE_RDP")}>Enable RDP</button>
                    <button className="secondary-action" disabled={commandAgentId === selected.id} onClick={() => void runAction(selected, "DISABLE_RDP")}>Disable RDP</button>
                    <button className="secondary-action" disabled={commandAgentId === selected.id} onClick={() => void runAction(selected, "TRIGGER_WINDOWS_UPDATE")}>Trigger Update Scan</button>
                  </div>
                )}
                {selected.device_id && <div className="agent-command-buttons">
                  <button className="secondary-action" disabled={!selected.mac_address} onClick={() => void wakeAgent(selected)}>Wake-on-LAN</button>
                  <button className="secondary-action" disabled={!selected.ip_address} onClick={() => void copyRdpCommand(selected)}>Copy RDP Command</button>
                </div>}
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

function formatUptime(seconds: number | null) {
  if (seconds === null) return "Unknown";
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  return days ? `${days}d ${hours}h` : `${hours}h`;
}

function formatBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes < 0) return "Unknown";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
  return `${value.toFixed(unit > 0 ? 1 : 0)} ${units[unit]}`;
}

function MetricChart({ values }: { values: number[] }) {
  const points = values.map((value, index) => {
    const x = values.length < 2 ? 50 : index / (values.length - 1) * 100;
    const y = 100 - Math.max(0, Math.min(100, value / (7 * 24 * 60 * 60) * 100));
    return `${x},${y}`;
  }).join(" ");
  return <div className="agent-metric-chart"><svg viewBox="0 0 100 100" role="img" aria-label="Device uptime trend over the last seven days"><polyline points={points} /></svg><span>Uptime · sampled every five minutes (seven-day scale)</span></div>;
}
