import { useState } from "react";
import { Feedback } from "../components/Feedback";
import { StatusBadge } from "../components/StatusBadge";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import type { LocalAgent } from "../lib/types";
import { PageTitle } from "./DashboardPage";
import "../styles/local-agents.css";

export default function LocalAgentsPage() {
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<LocalAgent>();
  const [showEnrollModal, setShowEnrollModal] = useState(false);
  const [enrollForm, setEnrollForm] = useState({ name: "", property_id: "", expires_minutes: 15 });
  const [enrolling, setEnrolling] = useState(false);
  const [enrollToken, setEnrollToken] = useState("");
  const [enrollError, setEnrollError] = useState("");

  const agents = useRequest(() => endpoints.listLocalAgents({ search: search || undefined }), [search]);
  const properties = useRequest(endpoints.managedProperties, []);
  const activeProperties = properties.data?.filter((property) => property.status === "active") ?? [];
  const selectedPropertyId = enrollForm.property_id || (activeProperties.length === 1 ? activeProperties[0].id : "");

  const handleEnroll = async () => {
    setEnrolling(true);
    setEnrollError("");
    try {
      const result = await endpoints.createAgentEnrollment({ ...enrollForm, property_id: selectedPropertyId });
      setEnrollToken(result.enrollment_token);
      setShowEnrollModal(false);
      setEnrollForm({ name: "", property_id: "", expires_minutes: 15 });
    } catch (caught) {
      setEnrollError(caught instanceof Error ? caught.message : "Failed to create enrollment");
    } finally {
      setEnrolling(false);
    }
  };

  const handleRevoke = async (agentId: string) => {
    if (!confirm("Are you sure you want to revoke this agent? This will immediately stop all authenticated ingestion.")) return;
    try {
      await endpoints.revokeAgent(agentId);
      agents.reload();
    } catch (caught) {
      alert(caught instanceof Error ? caught.message : "Failed to revoke agent");
    }
  };

  const copyToken = () => {
    navigator.clipboard.writeText(enrollToken);
    alert("Enrollment token copied to clipboard");
  };

  return (
    <DashboardLayout>
      <PageTitle
        eyebrow="Administration"
        title="Local Agents"
        copy="Secure local observation and collection agents running inside hotel networks."
        action={
          <button
            className="primary-action"
            onClick={() => setShowEnrollModal(true)}
          >
            + Create Enrollment
          </button>
        }
      />

      <section className="operational-guide" aria-label="How local agents work">
        <div><span>Why it exists</span><strong>Observe the hotel network from inside</strong><p>A hosted HIOP server cannot directly see private hotel networks. A local agent securely sends approved discovery and monitoring observations.</p></div>
        <div><span>How to use it</span><strong>Create enrollment, install, verify</strong><p>Create a short-lived token for the correct property, enroll the agent on-site, then confirm its heartbeat and version here.</p></div>
        <div><span>Security</span><strong>Property-bound and read-only by default</strong><p>An agent cannot submit data for another property and does not provide arbitrary remote command execution.</p></div>
      </section>

      {enrollToken && (
        <div className="enrollment-success">
          <div className="enrollment-token">
            <strong>Enrollment Token Generated</strong>
            <code>{enrollToken.substring(0, 32)}...</code>
            <button onClick={copyToken}>Copy Token</button>
            <button onClick={() => setEnrollToken("")}>Close</button>
          </div>
          <p>Share this token with the agent installer. It expires in {enrollForm.expires_minutes} minutes.</p>
        </div>
      )}

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
                  <th>Agent ID</th>
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
                    <td>{agent.property_id}</td>
                    <td><StatusBadge status={agent.status} /></td>
                    <td>{agent.version || "Unknown"}</td>
                    <td>{agent.last_heartbeat ? new Date(agent.last_heartbeat).toLocaleString() : "Never"}</td>
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
                <Detail label="Agent ID" value={selected.agent_id} />
                <Detail label="Organization ID" value={selected.organization_id} />
                <Detail label="Property ID" value={selected.property_id} />
                <Detail label="Hostname" value={selected.hostname || "Unknown"} />
                <Detail label="Version" value={selected.version || "Unknown"} />
                <Detail label="Last Heartbeat" value={selected.last_heartbeat ? new Date(selected.last_heartbeat).toLocaleString() : "Never"} />
                <Detail label="Last Discovery" value={selected.last_discovery ? new Date(selected.last_discovery).toLocaleString() : "Never"} />
                <Detail label="Last Monitoring" value={selected.last_monitoring ? new Date(selected.last_monitoring).toLocaleString() : "Never"} />
                <Detail label="Uptime" value={selected.uptime_seconds ? `${Math.floor(selected.uptime_seconds / 3600)}h` : "Unknown"} />
                <Detail label="Pending Queue" value={`${selected.pending_queue}/${selected.queue_capacity}`} />
                <Detail label="Registered" value={new Date(selected.registered_at).toLocaleString()} />
              </dl>
              <div className="agent-actions">
                {selected.status !== "revoked" && (
                  <button className="danger-action" onClick={() => handleRevoke(selected.id)}>
                    Revoke Agent
                  </button>
                )}
              </div>
            </>
          )}
        </aside>
      </section>

      {showEnrollModal && (
        <div className="modal-overlay" onClick={() => setShowEnrollModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Create Agent Enrollment</h3>
            {enrollError && <div className="error-message">{enrollError}</div>}
            <div className="form-group">
              <label>Agent Name *</label>
              <input
                type="text"
                value={enrollForm.name}
                onChange={(e) => setEnrollForm({ ...enrollForm, name: e.target.value })}
                placeholder="e.g., Lagos Continental Main Agent"
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
              <label>Expires In (minutes) *</label>
              <input
                type="number"
                min="5"
                max="60"
                value={enrollForm.expires_minutes}
                onChange={(e) => setEnrollForm({ ...enrollForm, expires_minutes: parseInt(e.target.value) })}
              />
              <small>Enrollment tokens are one-time and expire after this period.</small>
            </div>
            <div className="modal-footer">
              <button onClick={() => setShowEnrollModal(false)} disabled={enrolling}>
                Cancel
              </button>
              <button className="primary-action" onClick={handleEnroll} disabled={enrolling || !enrollForm.name || !selectedPropertyId}>
                {enrolling ? "Creating..." : "Create Enrollment"}
              </button>
            </div>
          </div>
        </div>
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
