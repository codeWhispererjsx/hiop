import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import BrandLogo from "../components/BrandLogo";
import { getDesktopStatus } from "../lib/publicApi";
import "../styles/public.css";

/** Keeps returning desktop users out of first-run setup while the local API wakes. */
export default function DesktopLaunchPage() {
  const navigate = useNavigate();
  const [message, setMessage] = useState("Preparing your HIOP workspace…");

  useEffect(() => {
    let active = true;
    let attempts = 0;
    let timer: number | undefined;
    const continueLaunch = async () => {
      try {
        const status = await getDesktopStatus();
        if (!active) return;
        navigate(
          status.platform_owner_required || status.organization_required
            ? "/desktop-setup"
            : "/login",
          { replace: true },
        );
      } catch {
        attempts += 1;
        if (attempts >= 90) {
          setMessage("HIOP is taking longer than usual to start. Please keep this window open.");
          return;
        }
        timer = window.setTimeout(continueLaunch, 1500);
      }
    };
    void continueLaunch();
    return () => {
      active = false;
      if (timer) window.clearTimeout(timer);
    };
  }, [navigate]);

  return <main className="public-site desktop-setup-page">
    <section className="first-run desktop-launch-card" aria-live="polite">
      <BrandLogo className="login-logo" />
      <p className="public-eyebrow">HIOP Desktop</p>
      <h1>Opening HIOP…</h1>
      <p>{message}</p>
    </section>
  </main>;
}
