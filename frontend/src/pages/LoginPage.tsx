import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Icon } from "../components/Icon";
import BrandLogo from "../components/BrandLogo";
import ThemeToggle from "../components/ThemeToggle";
import { endpoints } from "../lib/api";
import { setAuthToken } from "../lib/auth";
import "../App.css";
import "../styles/product-polish.css";

export default function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setMessage("");
    setBusy(true);
    try {
      const data = await endpoints.login(email, password);
      setAuthToken(data.access_token);
      const user=await endpoints.me();
      setPassword("");
      navigate(user.role==="platformadmin"?"/platform":"/dashboard");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to sign in");
    } finally {
      setBusy(false);
    }
  };

  return <main className="login-page">
    <ThemeToggle className="login-theme-toggle" />
    <section className="login-story">
      <BrandLogo className="login-logo" />
      <div className="login-copy"><p className="login-kicker">Hospitality operations, beautifully connected</p><h1>Technology that stays behind the scenes.</h1><p>See every critical hotel system, respond before service is disrupted, and keep every guest-facing team moving from one secure workspace.</p><div className="login-proof"><span><Icon name="check" size={16}/>Live infrastructure visibility</span><span><Icon name="check" size={16}/>Incident-ready operations</span></div></div>
      <div className="login-stats"><div className="login-stat"><strong><i className="status-dot" />Operational</strong><span>Platform status</span></div><div className="login-stat"><strong>24 / 7</strong><span>Infrastructure watch</span></div><div className="login-stat"><strong>Secure</strong><span>Role-based access</span></div></div>
    </section>
    <section className="login-panel">
      <div className="login-card">
        <div className="login-card-head"><span className="login-access-mark"><Icon name="lock" size={18}/></span><p className="login-kicker">Secure operations access</p><h2>Welcome back</h2><p>Sign in to your Hospitality IT Ops workspace.</p></div>
        <form className="login-form" onSubmit={submit}>
          <label className="field-label">Work email<div className="field-wrap"><Icon name="mail" className="field-icon" /><input type="email" value={email} onChange={event => setEmail(event.target.value)} autoComplete="username" required /></div></label>
          <label className="field-label">Password<div className="field-wrap"><Icon name="lock" className="field-icon" /><input type="password" value={password} onChange={event => setPassword(event.target.value)} autoComplete="current-password" required /></div></label>
          <button className="submit-button" disabled={busy}>{busy ? "Verifying access…" : <><span>Enter operations portal</span><Icon name="arrow" size={18}/></>}</button>
        </form>
        <p className="login-message" role="alert">{message && <><Icon name="warning" size={16} />{message}</>}</p>
        <p className="login-security"><Icon name="lock" size={15}/>Protected access. Activity is recorded in the hospitality IT audit trail.</p>
        <p className="login-public-links"><Link to="/">Back to HIOP</Link><Link to="/get-started">Create an organization</Link></p>
      </div>
    </section>
  </main>;
}
