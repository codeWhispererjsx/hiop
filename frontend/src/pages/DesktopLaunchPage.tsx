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
  const siteServerUrl = window.hiopDesktop?.siteServerUrl;

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
        if (attempts >= 3) {
          setError(caught instanceof Error ? caught.message : "Unable to contact the HIOP Site Server.");
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
  }, [navigate, retry]);

  return <main className="public-site desktop-setup-page">
    <section className="first-run desktop-launch-card" aria-live="polite">
      <BrandLogo className="login-logo" />
      <p className="public-eyebrow">HIOP Desktop</p>
      <h1>{error ? "HIOP couldn’t connect" : "Connecting to your HIOP workspace"}</h1>
      <p>{error || (siteServerUrl
        ? `Checking your configured Site Server: ${siteServerUrl}`
        : "Starting this computer’s private HIOP Site Server and checking your workspace.")}</p>
      {error ? (
        <div className="desktop-launch-actions">
          <button className="public-button" type="button" onClick={() => setRetry(value => value + 1)}>Retry connection</button>
          {destination && <Link className="public-button secondary" to={destination}>Continue to {destination === "/login" ? "sign in" : "first-time setup"}</Link>}
          <Link className="public-button secondary" to="/desktop-connect" state={{ returnTo: "/desktop-launch" }}>
            {siteServerUrl ? "Change Site Server" : "Connect to an existing Site Server"}
          </Link>
        </div>
      ) : (
        <>
          <p role="status">Checking Site Server{attempt > 0 ? ` · attempt ${attempt + 1} of 3` : ""}…</p>
          {destination && <Link className="public-button secondary" to={destination}>Continue to {destination === "/login" ? "sign in" : "first-time setup"}</Link>}
          <Link className="public-button secondary" to="/desktop-connect" state={{ returnTo: "/desktop-launch" }}>
            {siteServerUrl ? "Change Site Server" : "Connect to an existing Site Server"}
          </Link>
        </>
      )}
    </section>
  </main>;
}
