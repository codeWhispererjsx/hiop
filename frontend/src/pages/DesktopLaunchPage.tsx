import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import BrandLogo from "../components/BrandLogo";
import { getDesktopStatus } from "../lib/publicApi";
import "../styles/public.css";

/** Keeps returning desktop users out of first-run setup while the local API wakes. */
export default function DesktopLaunchPage() {
  const navigate = useNavigate();
  const [retry, setRetry] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [error, setError] = useState("");
  const [destination, setDestination] = useState<"/desktop-setup" | "/login">();
  const [restarting, setRestarting] = useState(false);
  const siteServerUrl = window.hiopDesktop?.siteServerUrl;
  const maxAttempts = siteServerUrl ? 3 : 24;

  const retryConnection = async () => {
    setError("");
    setAttempt(0);
    if (!siteServerUrl && window.hiopDesktop) {
      setRestarting(true);
      try {
        await window.hiopDesktop.ensureLocalBackend();
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Unable to restart the local HIOP service.");
        setRestarting(false);
        return;
      }
      setRestarting(false);
    }
    setRetry(value => value + 1);
  };

  useEffect(() => {
    let active = true;
    let timer: number | undefined;
    let attempts = 0;
    const checkStatus = async () => {
      if (!active) return;
      try {
        const status = await getDesktopStatus();
        if (!active) return;
        const next = status.platform_owner_required || status.organization_required
          ? "/desktop-setup"
          : "/login";
        setDestination(next);
        navigate(next, { replace: true });
      } catch (caught) {
        if (!active) return;
        attempts += 1;
        setAttempt(attempts);
        if (attempts >= maxAttempts) {
          setError(caught instanceof Error ? caught.message : siteServerUrl
            ? "Unable to contact the configured HIOP Site Server."
            : "Unable to contact the local HIOP service.");
          return;
        }
        timer = window.setTimeout(() => void checkStatus(), 1500);
      }
    };
    setAttempt(0);
    setError("");
    setDestination(undefined);
    void checkStatus();
    return () => {
      active = false;
      if (timer) window.clearTimeout(timer);
    };
  }, [maxAttempts, navigate, retry]);

  return <main className="public-site desktop-setup-page">
    <section className="first-run desktop-launch-card" aria-live="polite">
      <BrandLogo className="login-logo" />
      <p className="public-eyebrow">HIOP Desktop</p>
      <h1>{error
        ? siteServerUrl ? "HIOP couldn’t connect" : "HIOP is taking longer to start"
        : siteServerUrl ? "Connecting to your HIOP Site Server" : "Starting HIOP on this computer"}</h1>
      <p>{error || (siteServerUrl
        ? `Checking your configured Site Server: ${siteServerUrl}`
        : "Starting this computer’s private HIOP service and checking your workspace.")}</p>
      {error && !siteServerUrl && <p>Your local service may still be starting. Retry startup; you do not need to enter another server address.</p>}
      {error ? (
        <div className="desktop-launch-actions">
          <button className="public-button" type="button" onClick={() => void retryConnection()} disabled={restarting}>
            {restarting ? "Starting local service…" : siteServerUrl ? "Retry connection" : "Retry local startup"}
          </button>
          {destination && <Link className="public-button secondary" to={destination}>Continue to {destination === "/login" ? "sign in" : "first-time setup"}</Link>}
          {siteServerUrl && <Link className="public-button secondary" to="/desktop-connect" state={{ returnTo: "/desktop-launch" }}>Change Site Server</Link>}
        </div>
      ) : (
        <>
          <p role="status">
            {restarting ? "Starting the local HIOP service…" : siteServerUrl ? "Checking Site Server" : "Checking this computer’s local service"}
            {attempt > 0 ? ` · attempt ${attempt + 1} of ${maxAttempts}` : ""}
          </p>
          {destination && <Link className="public-button secondary" to={destination}>Continue to {destination === "/login" ? "sign in" : "first-time setup"}</Link>}
          {siteServerUrl && <Link className="public-button secondary" to="/desktop-connect" state={{ returnTo: "/desktop-launch" }}>Change Site Server</Link>}
        </>
      )}
    </section>
  </main>;
}
