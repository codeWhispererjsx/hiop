import { type FormEvent, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import BrandLogo from "../components/BrandLogo";
import ThemeToggle from "../components/ThemeToggle";
import { clearAuthToken } from "../lib/auth";
import "../styles/public.css";

export default function DesktopConnectPage() {
  const location = useLocation();
  const returnTo = (location.state as { returnTo?: string } | null)?.returnTo;
  const backTo = returnTo === "/login" ? "/login" : "/desktop-launch";
  const [siteServerUrl, setSiteServerUrl] = useState(() => window.hiopDesktop?.siteServerUrl ?? "");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setSaving(true);
    try {
      if (!window.hiopDesktop) throw new Error("Site Server connections are available only in HIOP Desktop.");
      const serverUrl = new URL(siteServerUrl.trim());
      const localHttp = serverUrl.protocol === "http:" && ["localhost", "127.0.0.1"].includes(serverUrl.hostname);
      if (serverUrl.protocol !== "https:" && !localHttp) {
        throw new Error("Use the Site Server's HTTPS address. HTTP is allowed only for localhost testing.");
      }
      if (serverUrl.username || serverUrl.password || serverUrl.search || serverUrl.hash || !["", "/"].includes(serverUrl.pathname)) {
        throw new Error("Enter only the Site Server address, without credentials, paths, or query parameters.");
      }
      await clearAuthToken();
      await window.hiopDesktop.saveSiteServerUrl(serverUrl.origin);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The Site Server connection could not be saved.");
      setSaving(false);
    }
  };

  const switchToThisComputer = async () => {
    setError("");
    setSaving(true);
    try {
      if (!window.hiopDesktop) throw new Error("Site Server settings are available only in HIOP Desktop.");
      await clearAuthToken();
      await window.hiopDesktop.saveSiteServerUrl(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The local Site Server setting could not be restored.");
      setSaving(false);
    }
  };

  return <main className="public-site desktop-setup-page">
    <ThemeToggle className="public-theme-toggle" aria-label="Toggle theme" />
    <section className="first-run desktop-setup-card desktop-connect-card">
      <Link className="desktop-connect-back" to={backTo}>← Back to {backTo === "/login" ? "sign in" : "HIOP startup"}</Link>
      <BrandLogo className="login-logo" />
      <p className="public-eyebrow">HIOP Desktop connection</p>
      <h1>Connect to your Site Server.</h1>
      <p>Enter the HTTPS address provided by your hotel HIOP administrator. Your desktop connects to the Site Server API; the PostgreSQL database stays private on that server.</p>
      <form className="desktop-setup-form" onSubmit={(event) => void save(event)}>
        <label htmlFor="site-server-url">Site Server HTTPS address</label>
        <input
          id="site-server-url"
          type="url"
          value={siteServerUrl}
          onChange={(event) => setSiteServerUrl(event.target.value)}
          placeholder="https://hiop.hotel.example"
          autoComplete="url"
          required
        />
        {error && <p className="onboarding-error" role="alert">{error}</p>}
        <button className="public-button" disabled={saving}>{saving ? "Saving connection…" : "Connect to Site Server"}</button>
      </form>
      {window.hiopDesktop?.siteServerUrl && (
        <button className="public-button secondary" type="button" onClick={() => void switchToThisComputer()} disabled={saving}>
          Use this computer as the Site Server
        </button>
      )}
      <p className="desktop-connect-note">Changing the Site Server signs you out and restarts HIOP. No database connection details are stored on this computer.</p>
    </section>
  </main>;
}
