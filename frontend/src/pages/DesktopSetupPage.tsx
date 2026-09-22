import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import BrandLogo from "../components/BrandLogo";
import ThemeToggle from "../components/ThemeToggle";
import { bootstrapPlatformOwner, getDesktopStatus, registerCustomer, type DesktopStatus } from "../lib/publicApi";
import { setAuthToken, setOrganizationContext } from "../lib/auth";
import "../styles/public.css";

const timezones = ["Africa/Lagos", "Africa/Accra", "Africa/Nairobi", "Europe/London", "UTC"];

type SetupData = {
  platform_username: string; platform_email: string; platform_password: string;
  organization_name: string; organization_code: string; contact_email: string; country: string; timezone: string;
  property_name: string; property_code: string; property_city: string;
  admin_username: string; admin_email: string; admin_password: string;
};

export default function DesktopSetupPage() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<DesktopStatus | null>(null);
  const [step, setStep] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [data, setData] = useState<SetupData>({
    platform_username: "platform.owner", platform_email: "", platform_password: "",
    organization_name: "", organization_code: "", contact_email: "", country: "Nigeria", timezone: "Africa/Lagos",
    property_name: "", property_code: "", property_city: "Lagos",
    admin_username: "", admin_email: "", admin_password: "",
  });
  const set = (key: keyof SetupData, value: string) => setData(current => ({ ...current, [key]: value }));

  useEffect(() => {
    let active = true;
    let timer: number | undefined;
    let attempts = 0;
    const readStatus = async () => {
      try {
        const result = await getDesktopStatus();
        if (!active) return;
        setError("");
        setStatus(result);
        if (!result.platform_owner_required && result.organization_required) setStep(2);
        if (!result.platform_owner_required && !result.organization_required) navigate("/login", { replace: true });
      } catch (caught) {
        if (!active) return;
        attempts += 1;
        if (attempts < 90) {
          setError("Starting HIOP's private local service…");
          timer = window.setTimeout(readStatus, 1500);
          return;
        }
        setError(caught instanceof Error ? caught.message : "Unable to start the local HIOP service.");
      }
    };
    void readStatus();
    return () => { active = false; if (timer) window.clearTimeout(timer); };
  }, [navigate]);

  const createPlatformOwner = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      if (status?.platform_owner_required) {
        await bootstrapPlatformOwner({ username: data.platform_username, email: data.platform_email, password: data.platform_password });
      }
      setStep(2);
      setStatus(await getDesktopStatus());
    } catch (error) { setError(error instanceof Error ? error.message : "Unable to create platform owner."); }
    finally { setBusy(false); }
  };

  const createWorkspace = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      const result = await registerCustomer({
        plan_code: "core", organization_name: data.organization_name, organization_code: data.organization_code,
        contact_email: data.contact_email, country: data.country, timezone: data.timezone,
        property_name: data.property_name, property_code: data.property_code, property_city: data.property_city,
        admin_username: data.admin_username, admin_email: data.admin_email, admin_password: data.admin_password,
      });
      setAuthToken(result.access_token);
      setOrganizationContext(result.organization.id);
      window.localStorage.setItem("hiop.active_property_id", result.property.id);
      navigate("/dashboard", { replace: true });
    } catch (error) { setError(error instanceof Error ? error.message : "Unable to create desktop workspace."); }
    finally { setBusy(false); }
  };

  return <main className="public-site desktop-setup-page">
    <ThemeToggle className="public-theme-toggle" aria-label="Toggle theme" />
    <section className="first-run desktop-setup-card">
      <BrandLogo className="login-logo" />
      <p className="public-eyebrow">HIOP Desktop first run</p>
      <h1>Set up this Windows installation.</h1>
      <p>Create the local control owner, first organization, first property, and first organization administrator. This data stays in the private local database on this computer.</p>
      <div className="first-run-context">
        <div><span>Local API</span><strong>127.0.0.1:8765</strong></div>
        <div><span>Database</span><strong>Private bundled PostgreSQL</strong></div>
      </div>
      <ol>
        <li className={step > 1 || !status?.platform_owner_required ? "done" : "active"}><span>1</span>Platform owner</li>
        <li className={step > 2 || (status && !status.organization_required) ? "done" : step === 2 ? "active" : ""}><span>2</span>Organization and property</li>
        <li className={step === 3 ? "active" : ""}><span>3</span>Start operating</li>
      </ol>
      {!status && !error && <p>Checking local setup…</p>}
      {error && <p className="onboarding-error" role="alert">{error}</p>}
      {status && step === 1 && <form className="desktop-setup-form" onSubmit={createPlatformOwner}>
        <h2>Platform owner</h2>
        <p>This account controls Platform Control Center on this local installation.</p>
        <Field label="Username" value={data.platform_username} set={v => set("platform_username", v)} required />
        <Field label="Email" type="email" value={data.platform_email} set={v => set("platform_email", v)} required />
        <Field label="Password" type="password" value={data.platform_password} set={v => set("platform_password", v)} required minLength={12} />
        <div className="first-run-actions"><button className="public-button" disabled={busy}>{busy ? "Creating owner…" : "Create platform owner"}</button><Link to="/login" className="public-button secondary">I already have login</Link></div>
      </form>}
      {status && step === 2 && <form className="desktop-setup-form" onSubmit={createWorkspace}>
        <h2>First organization and property</h2>
        <div className="form-pair"><Field label="Organization name" value={data.organization_name} set={v => set("organization_name", v)} required /><Field label="Organization code" value={data.organization_code} set={v => set("organization_code", v)} required /></div>
        <div className="form-pair"><Field label="Contact email" type="email" value={data.contact_email} set={v => set("contact_email", v)} required /><Field label="Country" value={data.country} set={v => set("country", v)} required /></div>
        <label>Time zone<select value={data.timezone} onChange={e => set("timezone", e.target.value)}>{timezones.map(x => <option key={x}>{x}</option>)}</select></label>
        <div className="form-pair"><Field label="Property name" value={data.property_name} set={v => set("property_name", v)} required /><Field label="Property code" value={data.property_code} set={v => set("property_code", v)} required /></div>
        <Field label="Property city" value={data.property_city} set={v => set("property_city", v)} required />
        <h3>Organization administrator</h3>
        <div className="form-pair"><Field label="Admin username" value={data.admin_username} set={v => set("admin_username", v)} required /><Field label="Admin email" type="email" value={data.admin_email} set={v => set("admin_email", v)} required /></div>
        <Field label="Admin password" type="password" value={data.admin_password} set={v => set("admin_password", v)} required minLength={12} />
        <div className="first-run-actions"><button className="public-button" disabled={busy}>{busy ? "Creating workspace…" : "Create local workspace"}</button><Link to="/login" className="public-button secondary">Back to login</Link></div>
      </form>}
    </section>
  </main>;
}

function Field({ label, value, set, type = "text", required = false, minLength }: { label: string; value: string; set: (value: string) => void; type?: string; required?: boolean; minLength?: number }) {
  return <label>{label}<input type={type} value={value} onChange={event => set(event.target.value)} required={required} minLength={minLength} /></label>;
}
