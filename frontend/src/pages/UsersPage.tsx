import { type FormEvent, useMemo, useState } from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import { PageTitle } from "./DashboardPage";
import { Feedback } from "../components/Feedback";
import { endpoints } from "../lib/api";
import { useRequest } from "../hooks/useRequest";

export default function UsersPage() {
  const users = useRequest(endpoints.users, []);
  const me = useRequest(endpoints.me, []);
  const [form, setForm] = useState({ username: "", email: "", password: "" });
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const rows = useMemo(() => (users.data ?? []).filter((user) => `${user.username} ${user.email} ${user.role}`.toLowerCase().includes(query.toLowerCase())), [users.data, query]);
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy("create"); setNotice("");
    try { const user = await endpoints.register(form); setNotice(`Created ${user.username}.`); setForm({ username: "", email: "", password: "" }); await users.reload(); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Could not create user"); }
    finally { setBusy(""); }
  };
  const update = async (id: string, body: { role?: string; is_active?: boolean }) => {
    setBusy(id); setNotice("");
    try { await endpoints.updateUser(id, body); setNotice("User updated."); await users.reload(); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Could not update user"); }
    finally { setBusy(""); }
  };

  return <DashboardLayout>
    <PageTitle eyebrow="Administration" title="Team & access" copy="Provision accounts, assign roles and manage active access."/>
    {notice && <div className="inline-notice">{notice}</div>}
    <section className="two-column">
      <article className="panel">
        <h2>User directory</h2>
        <div className="search-field"><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search users"/></div>
        {users.loading || users.error || !rows.length ? <Feedback loading={users.loading} error={users.error} empty="No users match this search." onRetry={users.reload}/> : <div className="compact-list">{rows.map((user) => <div key={user.id}>
          <span className={`pulse ${user.is_active ? "online" : "offline"}`}/><strong>{user.username}</strong><span>{user.email}</span>
          <select aria-label={`Role for ${user.username}`} value={user.role} disabled={busy === user.id} onChange={(event) => void update(user.id, { role: event.target.value })}><option value="admin">Admin</option><option value="technician">Technician</option><option value="staff">Staff</option></select>
          <button className="secondary-action" disabled={busy === user.id || user.id === me.data?.id} onClick={() => void update(user.id, { is_active: !user.is_active })}>{user.is_active ? "Deactivate" : "Activate"}</button>
        </div>)}</div>}
      </article>
      <article className="panel"><h2>Create account</h2><form className="modal-form" onSubmit={submit}>
        <label>Username<input required value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })}/></label>
        <label>Email<input required type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })}/></label>
        <label>Temporary password<input required minLength={8} type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })}/></label>
        <button className="primary-action" disabled={busy === "create"}>{busy === "create" ? "Creating…" : "Create account"}</button>
      </form></article>
    </section>
  </DashboardLayout>;
}
