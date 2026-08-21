import { type FormEvent, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import BrandLogo from "../components/BrandLogo";
import ThemeToggle from "../components/ThemeToggle";
import { endpoints } from "../lib/api";
import "../App.css";
import "../styles/product-polish.css";

type Mode = "forgot" | "reset" | "verify" | "invitation";

const copy: Record<Mode, { title: string; description: string; action: string }> = {
  forgot: { title: "Reset your password", description: "Enter your work email. If an account exists, we will send a secure reset link.", action: "Send reset link" },
  reset: { title: "Choose a new password", description: "Use at least 12 characters with uppercase, lowercase, and a number.", action: "Reset password" },
  verify: { title: "Verify your email", description: "Confirm this email address belongs to you.", action: "Verify email" },
  invitation: { title: "Accept your invitation", description: "Create your secure HIOP account to join the organization.", action: "Accept invitation" },
};

export default function AccountAccessPage({ mode }: { mode: Mode }) {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event?: FormEvent) => {
    event?.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      const result = mode === "forgot" ? await endpoints.requestPasswordRecovery(email)
        : mode === "reset" ? await endpoints.confirmPasswordRecovery(token, password)
        : mode === "verify" ? await endpoints.confirmEmailVerification(token)
        : await endpoints.acceptInvitation(token, username, password);
      setMessage(result.message); setPassword("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to complete this request."); }
    finally { setBusy(false); }
  };

  const needsPassword = mode === "reset" || mode === "invitation";
  return <main className="account-access-page">
    <ThemeToggle className="login-theme-toggle" aria-label="Toggle theme" />
    <section className="account-access-card" aria-labelledby="account-access-title">
      <BrandLogo className="account-access-logo" />
      <p className="login-kicker">Secure account access</p>
      <h1 id="account-access-title">{copy[mode].title}</h1>
      <p>{copy[mode].description}</p>
      {!token && mode !== "forgot" ? <div className="inline-alert danger" role="alert">This link is incomplete. Request a new secure link.</div> :
      <form className="login-form" onSubmit={submit}>
        {mode === "forgot" && <label className="field-label">Work email<input type="email" value={email} onChange={e=>setEmail(e.target.value)} autoComplete="email" required /></label>}
        {mode === "invitation" && <label className="field-label">Username<input value={username} onChange={e=>setUsername(e.target.value)} autoComplete="username" pattern="[A-Za-z0-9._-]+" required /><small>Letters, numbers, dots, underscores and hyphens only.</small></label>}
        {needsPassword && <label className="field-label">New password<input type="password" value={password} onChange={e=>setPassword(e.target.value)} autoComplete="new-password" minLength={12} required /><small>At least 12 characters with uppercase, lowercase and a number.</small></label>}
        <button className="submit-button" disabled={busy}>{busy ? "Please wait…" : copy[mode].action}</button>
      </form>}
      {message && <div className="inline-alert success" role="status">{message}</div>}
      {error && <div className="inline-alert danger" role="alert">{error}</div>}
      <p className="account-access-back"><Link to="/login">Back to sign in</Link></p>
    </section>
  </main>;
}
