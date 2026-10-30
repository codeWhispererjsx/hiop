import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import BrandLogo from "../components/BrandLogo";
import { Icon } from "../components/Icon";
import { PublicLayout } from "../components/PublicLayout";
import { downloadPublicAgent, getPublicAgentServerUrl, getPublicAgentStatus, type PublicAgentStatus } from "../lib/publicApi";
import "../styles/public.css";

export default function AgentDownloadPage() {
  const navigate = useNavigate();
  const [server, setServer] = useState<PublicAgentStatus>();
  const [serverError, setServerError] = useState("");
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [notice, setNotice] = useState("");
  const serverUrl = getPublicAgentServerUrl();
  const serverAddress = new URL(serverUrl);
  const httpsRequired = serverAddress.protocol !== "https:"
    && !["localhost", "127.0.0.1", "::1"].includes(serverAddress.hostname);
  const goBack = () => {
    if (window.history.length > 1) {
      navigate(-1);
      return;
    }
    navigate("/");
  };

  useEffect(() => {
    let active = true;
    void getPublicAgentStatus()
      .then((result) => { if (active) setServer(result); })
      .catch((caught: unknown) => { if (active) setServerError(caught instanceof Error ? caught.message : "Server status is unavailable."); });
    return () => { active = false; };
  }, []);

  const download = async () => {
    setDownloading(true);
    setError("");
    setNotice("");
    try {
      await downloadPublicAgent();
      setNotice("Download started. Run the EXE, enter the HIOP server address, then enroll with a one-time code.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Agent download failed.");
    } finally {
      setDownloading(false);
    }
  };

  const copyServerUrl = () => {
    void navigator.clipboard.writeText(serverUrl)
      .then(() => setNotice("HIOP server address copied."))
      .catch(() => setError(`Copy failed. Use this address: ${serverUrl}`));
  };

  return (
    <PublicLayout agentDownload>
      <section className="agent-download-page">
        <button type="button" className="agent-download-back" onClick={goBack}>
          <Icon name="arrow" size={18} />
          Back
        </button>
        <header className="agent-download-brand">
          <BrandLogo />
          <p>HIOP agent distribution</p>
        </header>
        <div className={`agent-server-status ${server ? "is-online" : serverError ? "is-unavailable" : ""}`} role={serverError ? "alert" : "status"}>
          <i aria-hidden="true" />
          {serverError ? serverError : server ? `HIOP server online · ${server.server_ip || serverAddress.host} · ${server.downloads} downloads recorded` : "Checking hotel HIOP server..."}
        </div>
        <section className="agent-download-card" aria-labelledby="agent-download-title">
          <span className="agent-download-icon"><Icon name="devices" size={30} aria-hidden="true" /></span>
          <p className="public-eyebrow">Company computers only</p>
          <h1 id="agent-download-title">HIOP Agent for Windows</h1>
          <p className="agent-download-lead">Device health, IT notices, and safe end-of-day power habits for company-managed Windows computers on the hotel admin network.</p>
          <div className="agent-package-facts">
            <span>Windows service + tray app</span>
            <span>Single-file Windows installer (EXE)</span>
            <span>Admin network only</span>
          </div>
          <button className="public-button agent-download-button" onClick={() => void download()} disabled={!server || downloading}>
            {downloading ? "Preparing download..." : "Download HIOP Agent for Windows"}
          </button>
          {notice && <p className="agent-download-notice" role="status">{notice}</p>}
          {error && <p className="agent-download-error" role="alert">{error}</p>}
          <p className="agent-download-security"><Icon name="lock" size={16} aria-hidden="true" /> Enrollment requires an administrator-generated, single-use code.</p>
        </section>
        {httpsRequired && <p className="agent-download-warning" role="note">This HIOP address uses HTTP. The package can download, but Windows agents need HTTPS with a certificate trusted by company PCs before they can enroll from another computer.</p>}

        <section className="agent-install-steps" aria-labelledby="agent-install-title">
          <p className="public-eyebrow">Installation</p>
          <h2 id="agent-install-title">Connect a company computer</h2>
          <ol>
            <li><span>1</span><div><strong>Download and run</strong><p>Save the EXE on a company Windows computer and double-click it.</p></div></li>
            <li><span>2</span><div><strong>Connect to your HIOP server</strong><p>Enter the HIOP server address shown below and approve the Windows administrator prompt.</p></div></li>
            <li><span>3</span><div><strong>Enter an enrollment code</strong><p>Ask an HIOP administrator to create a one-time code under Administration → Agents - Managed Endpoints for the correct hotel property.</p></div></li>
            <li><span>4</span><div><strong>Confirm the endpoint</strong><p>Enter the code in the HIOP Agent tray window. The code expires and can only be used once.</p></div></li>
            <li><span>5</span><div><strong>Check the dashboard</strong><p>The computer appears in Managed Endpoints after its first heartbeat.</p></div></li>
          </ol>
        </section>

        <section className="agent-admin-deploy">
          <h2>For IT administrators</h2>
          <p>For USB or managed group deployment, distribute this installer only through approved company channels. Create a separate one-time enrollment code for each computer or enrollment batch. The installer requires a trusted HTTPS server address and does not accept a reusable shared secret.</p>
          <div className="agent-server-copy">
            <code>{serverUrl}</code>
            <button type="button" className="secondary-action" onClick={copyServerUrl}>Copy server address</button>
          </div>
        </section>
        <footer className="agent-download-footer">
          <span>Help: Contact your HIOP administrator</span>
          <span>Works only on the hotel admin network · No internet access required for agent communication</span>
          <span>For company-managed devices only</span>
        </footer>
      </section>
    </PublicLayout>
  );
}
