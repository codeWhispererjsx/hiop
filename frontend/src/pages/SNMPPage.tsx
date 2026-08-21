import { useEffect, useState } from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import { PageTitle } from "./DashboardPage";
import { Feedback } from "../components/Feedback";
import { endpoints } from "../lib/api";
import type { SNMPCredential, SNMPTarget, SNMPPage } from "../lib/types";

export default function SNMPPage() {
  const [credentials, setCredentials] = useState<SNMPCredential[]>([]);
  const [targets, setTargets] = useState<SNMPTarget[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<"credentials" | "targets">("credentials");
  const [showCredentialModal, setShowCredentialModal] = useState(false);
  const [showTargetModal, setShowTargetModal] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newCredential, setNewCredential] = useState({
    name: "",
    version: "v2c",
    community: "public",
    username: "",
    authentication_protocol: "none",
    authentication_secret: "",
    privacy_protocol: "none",
    privacy_secret: "",
    security_level: "noAuthNoPriv",
    context_name: "",
    enabled: true,
    description: ""
  });
  const [newTarget, setNewTarget] = useState({
    name: "",
    ip_address: "",
    hostname: "",
    port: 161,
    version: "v2c",
    credential_id: "",
    enabled: true,
    polling_enabled: false,
    timeout_seconds: 5,
    retries: 1,
    transport: "udp",
    context_name: ""
  });

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [credsResponse, targetsResponse] = await Promise.all([
        endpoints.snmpCredentials(),
        endpoints.snmpTargets()
      ]);
      setCredentials(credsResponse.items);
      setTargets(targetsResponse.items);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "SNMP data could not be loaded.");
    } finally {
      setLoading(false);
    }
  };

  const handleCreateCredential = async () => {
    setCreating(true);
    setError("");
    try {
      // Only include fields relevant to the SNMP version
      const credentialData: import("../lib/types").SNMPCredentialInput = {
        name: newCredential.name,
        version: newCredential.version as "v1" | "v2c" | "v3",
        enabled: newCredential.enabled,
        description: newCredential.description
      };

      if (newCredential.version === "v2c") {
        credentialData.community = newCredential.community;
      } else {
        // For v3, include the v3-specific fields
        credentialData.username = newCredential.username || undefined;
        credentialData.authentication_protocol = newCredential.authentication_protocol;
        credentialData.privacy_protocol = newCredential.privacy_protocol;
        credentialData.security_level = newCredential.security_level;
        credentialData.context_name = newCredential.context_name || undefined;
        
        if (newCredential.authentication_secret) {
          credentialData.authentication_secret = newCredential.authentication_secret;
        }
        if (newCredential.privacy_secret) {
          credentialData.privacy_secret = newCredential.privacy_secret;
        }
      }

      await endpoints.createSNMPCredential(credentialData);
      setShowCredentialModal(false);
      setNewCredential({
        name: "",
        version: "v2c",
        community: "public",
        username: "",
        authentication_protocol: "none",
        authentication_secret: "",
        privacy_protocol: "none",
        privacy_secret: "",
        security_level: "noAuthNoPriv",
        context_name: "",
        enabled: true,
        description: ""
      });
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to create credential.");
    } finally {
      setCreating(false);
    }
  };

  const handleCreateTarget = async () => {
    setCreating(true);
    setError("");
    try {
      // Basic IP address validation
      const ipPattern = /^([0-9]{1,3}\.){3}[0-9]{1,3}$/;
      if (!ipPattern.test(newTarget.ip_address)) {
        throw new Error("Invalid IP address format. Use format: 192.168.1.1");
      }
      
      await endpoints.createSNMPTarget(newTarget as import("../lib/types").SNMPTargetInput);
      setShowTargetModal(false);
      setNewTarget({
        name: "",
        ip_address: "",
        hostname: "",
        port: 161,
        version: "v2c",
        credential_id: "",
        enabled: true,
        polling_enabled: false,
        timeout_seconds: 5,
        retries: 1,
        transport: "udp",
        context_name: ""
      });
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to create target.");
    } finally {
      setCreating(false);
    }
  };

  const handleDisableCredential = async (id: string) => {
    setCreating(true);
    setError("");
    try {
      await endpoints.disableSNMPCredential(id);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to disable credential.");
    } finally {
      setCreating(false);
    }
  };

  const handleDisableTarget = async (id: string) => {
    setCreating(true);
    setError("");
    try {
      await endpoints.disableSNMPTarget(id);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to disable target.");
    } finally {
      setCreating(false);
    }
  };

  const handleTestTarget = async (id: string) => {
    setCreating(true);
    setError("");
    try {
      await endpoints.testSNMPTarget(id);
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to test target.");
    } finally {
      setCreating(false);
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <DashboardLayout>
      <PageTitle
        eyebrow="Network Monitoring"
        title="SNMP Management"
        copy="Manage SNMP credentials and targets for network device monitoring."
      />
      <section className="operational-guide" aria-label="How SNMP monitoring works">
        <div><span>Purpose</span><strong>Read network-device health</strong><p>SNMP retrieves identity, uptime, interfaces, errors, and availability from supported switches, routers, printers, and access points.</p></div>
        <div><span>Setup</span><strong>Credential, then target</strong><p>Add a read-only SNMP credential, add an IP target in the correct property, test it, then enable polling.</p></div>
        <div><span>Real-time use</span><strong>Test and poll safely</strong><p>The Test action verifies connectivity immediately. Polling updates observed facts without applying device configuration.</p></div>
      </section>
      {error && <Feedback error={error} />}
      {loading ? (
        <Feedback loading />
      ) : (
        <div className="snmp-page">
          <div className="snmp-tabs">
            <button
              className={activeTab === "credentials" ? "active" : ""}
              onClick={() => setActiveTab("credentials")}
            >
              Credentials ({credentials.length})
            </button>
            <button
              className={activeTab === "targets" ? "active" : ""}
              onClick={() => setActiveTab("targets")}
            >
              Targets ({targets.length})
            </button>
          </div>

          {activeTab === "credentials" && (
            <section className="snmp-section">
              <div className="section-header">
                <h2>SNMP Credentials</h2>
                <button className="primary-action" onClick={() => setShowCredentialModal(true)}>+ Add Credential</button>
              </div>
              {credentials.length === 0 ? (
                <Feedback empty="No SNMP credentials configured." />
              ) : (
                <div className="snmp-list">
                  {credentials.map((cred) => (
                    <div key={cred.id} className="snmp-item">
                      <div className="snmp-item-main">
                        <strong>{cred.name}</strong>
                        <span className="badge">{cred.version}</span>
                        {cred.enabled ? (
                          <span className="badge success">Enabled</span>
                        ) : (
                          <span className="badge warning">Disabled</span>
                        )}
                      </div>
                      <div className="snmp-item-details">
                        <div>
                          <small>Username:</small> {cred.username || "N/A"}
                        </div>
                        <div>
                          <small>Auth Protocol:</small> {cred.authentication_protocol}
                        </div>
                        <div>
                          <small>Privacy Protocol:</small> {cred.privacy_protocol}
                        </div>
                        <div>
                          <small>Security Level:</small> {cred.security_level}
                        </div>
                        {cred.description && (
                          <div>
                            <small>Description:</small> {cred.description}
                          </div>
                        )}
                      </div>
                      <div className="snmp-item-actions">
                        <button className="secondary-action" disabled>Edit</button>
                        <button className="secondary-action" disabled>Test</button>
                        <button 
                          className="secondary-action" 
                          onClick={() => handleDisableCredential(cred.id)}
                          disabled={creating}
                        >
                          Disable
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}

          {activeTab === "targets" && (
            <section className="snmp-section">
              <div className="section-header">
                <h2>SNMP Targets</h2>
                <button className="primary-action" onClick={() => setShowTargetModal(true)}>+ Add Target</button>
              </div>
              {targets.length === 0 ? (
                <Feedback empty="No SNMP targets configured." />
              ) : (
                <div className="snmp-list">
                  {targets.map((target) => (
                    <div key={target.id} className="snmp-item">
                      <div className="snmp-item-main">
                        <strong>{target.name}</strong>
                        <span className="badge">{target.version}</span>
                        {target.enabled ? (
                          <span className="badge success">Enabled</span>
                        ) : (
                          <span className="badge warning">Disabled</span>
                        )}
                        {target.polling_enabled ? (
                          <span className="badge success">Polling</span>
                        ) : (
                          <span className="badge">Not Polling</span>
                        )}
                      </div>
                      <div className="snmp-item-details">
                        <div>
                          <small>IP Address:</small> {target.ip_address}
                        </div>
                        <div>
                          <small>Hostname:</small> {target.hostname || "N/A"}
                        </div>
                        <div>
                          <small>Port:</small> {target.port}
                        </div>
                        <div>
                          <small>Timeout:</small> {target.timeout_seconds}s
                        </div>
                        <div>
                          <small>Retries:</small> {target.retries}
                        </div>
                        {target.last_test_status && (
                          <div>
                            <small>Last Test:</small> {target.last_test_status}
                          </div>
                        )}
                      </div>
                      <div className="snmp-item-actions">
                        <button 
                          className="secondary-action"
                          onClick={() => handleTestTarget(target.id)}
                          disabled={creating}
                        >
                          Test Connection
                        </button>
                        <button className="secondary-action" disabled>Edit</button>
                        <button className="secondary-action" disabled>
                          {target.polling_enabled ? "Stop Polling" : "Start Polling"}
                        </button>
                        <button 
                          className="secondary-action"
                          onClick={() => handleDisableTarget(target.id)}
                          disabled={creating}
                        >
                          Disable
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}
        </div>
      )}

      {/* Credential Creation Modal */}
      {showCredentialModal && (
        <div className="modal-overlay" onClick={() => setShowCredentialModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Add SNMP Credential</h3>
            <div className="form-group">
              <label>Name *</label>
              <input
                type="text"
                value={newCredential.name}
                onChange={(e) => setNewCredential({ ...newCredential, name: e.target.value })}
                placeholder="Credential name"
              />
            </div>
            <div className="form-group">
              <label>Version *</label>
              <select
                value={newCredential.version}
                onChange={(e) => setNewCredential({ ...newCredential, version: e.target.value })}
              >
                <option value="v2c">SNMPv2c</option>
                <option value="v3">SNMPv3</option>
              </select>
            </div>
            {newCredential.version === "v2c" ? (
              <div className="form-group">
                <label>Community String *</label>
                <input
                  type="text"
                  value={newCredential.community}
                  onChange={(e) => setNewCredential({ ...newCredential, community: e.target.value })}
                  placeholder="public"
                />
              </div>
            ) : (
              <>
                <div className="form-group">
                  <label>Username *</label>
                  <input
                    type="text"
                    value={newCredential.username}
                    onChange={(e) => setNewCredential({ ...newCredential, username: e.target.value })}
                    placeholder="snmp-user"
                  />
                </div>
                <div className="form-group">
                  <label>Authentication Protocol</label>
                  <select
                    value={newCredential.authentication_protocol}
                    onChange={(e) => setNewCredential({ ...newCredential, authentication_protocol: e.target.value })}
                  >
                    <option value="none">None</option>
                    <option value="MD5">MD5</option>
                    <option value="SHA">SHA</option>
                    <option value="SHA224">SHA224</option>
                    <option value="SHA256">SHA256</option>
                    <option value="SHA384">SHA384</option>
                    <option value="SHA512">SHA512</option>
                  </select>
                </div>
                {newCredential.authentication_protocol !== "none" && (
                  <div className="form-group">
                    <label>Authentication Secret *</label>
                    <input
                      type="password"
                      value={newCredential.authentication_secret}
                      onChange={(e) => setNewCredential({ ...newCredential, authentication_secret: e.target.value })}
                      placeholder="Authentication secret (min 8 characters)"
                    />
                  </div>
                )}
                <div className="form-group">
                  <label>Privacy Protocol</label>
                  <select
                    value={newCredential.privacy_protocol}
                    onChange={(e) => setNewCredential({ ...newCredential, privacy_protocol: e.target.value })}
                  >
                    <option value="none">None</option>
                    <option value="DES">DES</option>
                    <option value="AES128">AES128</option>
                    <option value="AES192">AES192</option>
                    <option value="AES256">AES256</option>
                  </select>
                </div>
                {newCredential.privacy_protocol !== "none" && (
                  <div className="form-group">
                    <label>Privacy Secret *</label>
                    <input
                      type="password"
                      value={newCredential.privacy_secret}
                      onChange={(e) => setNewCredential({ ...newCredential, privacy_secret: e.target.value })}
                      placeholder="Privacy secret (min 8 characters)"
                    />
                  </div>
                )}
                <div className="form-group">
                  <label>Security Level</label>
                  <select
                    value={newCredential.security_level}
                    onChange={(e) => setNewCredential({ ...newCredential, security_level: e.target.value })}
                  >
                    <option value="noAuthNoPriv">No Auth, No Priv</option>
                    <option value="authNoPriv">Auth, No Priv</option>
                    <option value="authPriv">Auth, Priv</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>Context Name</label>
                  <input
                    type="text"
                    value={newCredential.context_name}
                    onChange={(e) => setNewCredential({ ...newCredential, context_name: e.target.value })}
                    placeholder="Optional context name"
                  />
                </div>
              </>
            )}
            <div className="form-group">
              <label>Description</label>
              <textarea
                value={newCredential.description}
                onChange={(e) => setNewCredential({ ...newCredential, description: e.target.value })}
                placeholder="Optional description"
                rows={3}
              />
            </div>
            <div className="modal-actions">
              <button
                className="secondary-action"
                onClick={() => setShowCredentialModal(false)}
                disabled={creating}
              >
                Cancel
              </button>
              <button
                className="primary-action"
                onClick={handleCreateCredential}
                disabled={creating || !newCredential.name}
              >
                {creating ? "Creating..." : "Create Credential"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Target Creation Modal */}
      {showTargetModal && (
        <div className="modal-overlay" onClick={() => setShowTargetModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Add SNMP Target</h3>
            <div className="form-group">
              <label>Name *</label>
              <input
                type="text"
                value={newTarget.name}
                onChange={(e) => setNewTarget({ ...newTarget, name: e.target.value })}
                placeholder="Target name"
              />
            </div>
            <div className="form-group">
              <label>IP Address *</label>
              <input
                type="text"
                value={newTarget.ip_address}
                onChange={(e) => setNewTarget({ ...newTarget, ip_address: e.target.value })}
                placeholder="192.168.1.1"
                pattern="^([0-9]{1,3}\.){3}[0-9]{1,3}$"
                title="Enter a valid IP address (e.g., 192.168.1.1)"
              />
              <small style={{ color: 'var(--text-muted)', fontSize: '9px' }}>Format: 192.168.1.1</small>
            </div>
            <div className="form-group">
              <label>Hostname</label>
              <input
                type="text"
                value={newTarget.hostname}
                onChange={(e) => setNewTarget({ ...newTarget, hostname: e.target.value })}
                placeholder="switch.example.com"
              />
            </div>
            <div className="form-group">
              <label>Credential *</label>
              <select
                value={newTarget.credential_id}
                onChange={(e) => setNewTarget({ ...newTarget, credential_id: e.target.value })}
                required
              >
                <option value="">Select a credential...</option>
                {credentials.map((cred) => (
                  <option key={cred.id} value={cred.id}>
                    {cred.name} ({cred.version})
                  </option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label>Port</label>
              <input
                type="number"
                value={newTarget.port}
                onChange={(e) => setNewTarget({ ...newTarget, port: parseInt(e.target.value) || 161 })}
                min={1}
                max={65535}
              />
            </div>
            <div className="modal-actions">
              <button
                className="secondary-action"
                onClick={() => setShowTargetModal(false)}
                disabled={creating}
              >
                Cancel
              </button>
              <button
                className="primary-action"
                onClick={handleCreateTarget}
                disabled={creating || !newTarget.name || !newTarget.ip_address || !newTarget.credential_id}
              >
                {creating ? "Creating..." : "Create Target"}
              </button>
            </div>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
