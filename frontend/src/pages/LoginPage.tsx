import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Icon } from "../components/Icon";
import ThemeToggle from "../components/ThemeToggle";
import { endpoints } from "../lib/api";
import { setAuthToken } from "../lib/auth";
import "../App.css";

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
      setPassword("");
      navigate("/dashboard");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to sign in");
    } finally {
      setBusy(false);
    }
  };

  return <main className="login-page">
    <ThemeToggle className="login-theme-toggle" />
    <section className="login-story">
      <div className="brand-lockup"><span className="brand-mark">HI</span><div><strong>HIOP</strong><span>Hotel IT Operations Portal</span></div></div>
      <div className="login-copy"><p className="login-kicker">One property. Complete visibility.</p><h1>Quiet technology. Exceptional hospitality.</h1><p>Monitor critical hotel systems, resolve service interruptions and keep guest-facing operations running from one secure command centre.</p></div>
      <div className="login-stats"><div className="login-stat"><strong><i className="status-dot" />Operational</strong><span>Platform status</span></div><div className="login-stat"><strong>24 / 7</strong><span>Infrastructure watch</span></div><div className="login-stat"><strong>Secure</strong><span>Role-based access</span></div></div>
    </section>
    <section className="login-panel">
      <div className="login-card">
        <div className="login-card-head"><p className="login-kicker">Authorised personnel</p><h2>Welcome back</h2><p>Sign in to enter the operations workspace.</p></div>
        <form className="login-form" onSubmit={submit}>
          <label className="field-label">Work email<div className="field-wrap"><Icon name="mail" className="field-icon" /><input type="email" value={email} onChange={event => setEmail(event.target.value)} autoComplete="username" required /></div></label>
          <label className="field-label">Password<div className="field-wrap"><Icon name="lock" className="field-icon" /><input type="password" value={password} onChange={event => setPassword(event.target.value)} autoComplete="current-password" required /></div></label>
          <button className="submit-button" disabled={busy}>{busy ? "Verifying access…" : "Enter operations portal"}</button>
        </form>
        <p className="login-message" role="alert">{message && <><Icon name="warning" size={16} />{message}</>}</p>
        <p className="login-security">Protected access. Activity inside HIOP is recorded in the hotel IT audit trail.</p>
      </div>
    </section>
  </main>;
}
