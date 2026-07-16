import { useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { Feedback } from "../components/Feedback";
import { Icon } from "../components/Icon";
import Modal from "../components/Modal";
import { Toast } from "../components/Toast";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import { PageTitle } from "./DashboardPage";

type DialogName = "role" | "status" | "password";

export default function UserDetailsPage() {
  const { id } = useParams();
  const location = useLocation();
  const user = useRequest(() => endpoints.user(id!), [id]);
  const me = useRequest(endpoints.me, []);
  const roles = useRequest(endpoints.userRoles, []);
  const audits = useRequest(() => endpoints.userAudit(id!), [id]);
  const [dialog, setDialog] = useState<DialogName | null>(null);
  const [role, setRole] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState((location.state as { notice?: string } | null)?.notice ?? "");
  const [error, setError] = useState("");

  const closeDialog = () => {
    if (busy) return;
    setDialog(null);
    setPassword("");
    setConfirm("");
    setError("");
  };

  const act = async () => {
    if (!user.data) return;
    setBusy(true);
    setError("");
    try {
      if (dialog === "role") await endpoints.changeUserRole(user.data.id, role || user.data.role);
      if (dialog === "status") await endpoints.changeUserStatus(user.data.id, !user.data.is_active);
      if (dialog === "password") {
        if (password.length < 10) throw new Error("Temporary password must be at least 10 characters.");
        if (password !== confirm) throw new Error("Passwords do not match.");
        await endpoints.resetUserPassword(user.data.id, password);
      }
      setNotice(dialog === "password" ? "Temporary password set." : "User access updated.");
      setPassword("");
      setConfirm("");
      setDialog(null);
      await user.reload();
      await audits.reload();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Action failed");
    } finally {
      setBusy(false);
    }
  };

  if (user.loading || user.error || !user.data) return <DashboardLayout><Feedback loading={user.loading} error={user.error} empty="User not found." onRetry={user.reload} /></DashboardLayout>;

  const account = user.data;
  const isAdmin = me.data?.role === "admin";
  const isOwnAccount = account.id === me.data?.id;
  const formatDate = (value?: string | null) => value ? new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "Not tracked";

  return <DashboardLayout>
    <div className="page-title-row user-detail-title">
      <PageTitle eyebrow="Team & access" title="User details" copy="Review identity, permissions, account availability, and administrative activity." />
      <Link className="secondary-action" to="/users"><Icon name="arrow" className="icon-back" size={15} />Back to team</Link>
    </div>
    {notice && <Toast message={notice} />}

    <section className="user-detail-layout">
      <div className="user-detail-main">
        <article className="panel user-profile-card">
          <header className="user-profile-hero">
            <span className="avatar user-profile-avatar">{account.username.slice(0, 2).toUpperCase()}</span>
            <div className="user-profile-heading"><span>Account profile</span><h2>{account.username}</h2><a href={`mailto:${account.email}`}>{account.email}</a></div>
            <span className={`account-state ${account.is_active ? "active" : "inactive"}`}><i />{account.is_active ? "Active account" : "Inactive account"}</span>
          </header>

          <dl className="user-metadata">
            <div><dt><Icon name="lock" size={15} />Access role</dt><dd><span className={`role-badge role-${account.role}`}>{account.role}</span></dd></div>
            <div><dt><Icon name="check" size={15} />Sign-in status</dt><dd>{account.is_active ? "Sign-in permitted" : "Sign-in blocked"}</dd></div>
            <div><dt><Icon name="clock" size={15} />Created</dt><dd>{formatDate(account.created_at)}</dd></div>
            <div><dt><Icon name="clock" size={15} />Last updated</dt><dd>{formatDate(account.updated_at)}</dd></div>
          </dl>

          {isAdmin && <footer className="user-admin-actions">
            <div><strong>Administrative actions</strong><span>Changes are enforced by backend authorization.</span></div>
            <div className="user-action-buttons">
              <Link className="secondary-action" to={`/users/${account.id}/edit`}><Icon name="audit" size={14} />Edit</Link>
              <button className="secondary-action" onClick={() => { setRole(account.role); setDialog("role"); }}><Icon name="settings" size={14} />Change role</button>
              <button className={account.is_active ? "danger-action" : "secondary-action"} disabled={isOwnAccount && account.is_active} onClick={() => setDialog("status")}><Icon name={account.is_active ? "lock" : "check"} size={14} />{account.is_active ? "Deactivate" : "Activate"}</button>
              <button className="secondary-action" onClick={() => setDialog("password")}><Icon name="lock" size={14} />Reset password</button>
            </div>
          </footer>}
        </article>

        <aside className="user-security-note">
          <Icon name="lock" size={18} />
          <div><strong>Account security</strong><p>Passwords and authentication tokens are never displayed. Deactivating an account preserves its ticket and audit history.</p></div>
        </aside>
      </div>

      <article className="panel user-audit-card">
        <header><div><span>Account history</span><h2>Audit activity</h2></div><span className="audit-count">{audits.data?.length ?? 0}</span></header>
        {audits.loading || audits.error || !audits.data?.length
          ? <Feedback loading={audits.loading} error={audits.error} empty="No user activity has been recorded." onRetry={audits.reload} />
          : <div className="user-audit-timeline">{audits.data.map((entry) => <article key={entry.id}>
            <i />
            <div><strong>{entry.action.replaceAll("_", " ")}</strong><p>{entry.description}</p><small>{formatDate(entry.created_at)} <span>by {entry.actor}</span></small></div>
          </article>)}</div>}
      </article>
    </section>

    {dialog && <Modal title={dialog === "role" ? "Change access role" : dialog === "status" ? (account.is_active ? "Deactivate user" : "Activate user") : "Set temporary password"} onClose={closeDialog}>
      <div className="modal-form user-action-modal">
        <div className="modal-account-context"><span className="avatar">{account.username.slice(0, 2).toUpperCase()}</span><div><strong>{account.username}</strong><small>{account.email}</small></div></div>
        {dialog === "role" && <label>Access role<select value={role} onChange={(event) => setRole(event.target.value)}>{roles.data?.map((item) => <option key={item}>{item}</option>)}</select><small>Privilege changes take effect on the user's next authorized request.</small></label>}
        {dialog === "status" && <div className="modal-explainer"><Icon name={account.is_active ? "warning" : "check"} size={20} /><p>{account.is_active ? "This user will no longer be able to sign in. Historical references remain intact." : "This user will regain access to HIOP using their current credentials."}</p></div>}
        {dialog === "password" && <><div className="modal-explainer"><Icon name="lock" size={20} /><p>This sets an administrator-issued temporary password. No email will be sent.</p></div><label>Temporary password<input type="password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} /></label><label>Confirm password<input type="password" autoComplete="new-password" value={confirm} onChange={(event) => setConfirm(event.target.value)} /></label></>}
        {error && <p className="form-error">{error}</p>}
        <div className="modal-actions"><button className="secondary-action" disabled={busy} onClick={closeDialog}>Cancel</button><button className="primary-action" disabled={busy} onClick={() => void act()}>{busy ? "Working…" : "Confirm change"}</button></div>
      </div>
    </Modal>}
  </DashboardLayout>;
}
