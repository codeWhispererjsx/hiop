import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { PageTitle } from "./DashboardPage";
import { Feedback } from "../components/Feedback";
import UserForm from "../components/UserForm";
import { Toast } from "../components/Toast";
import { endpoints } from "../lib/api";
import { useRequest } from "../hooks/useRequest";
import type { UserInput } from "../lib/types";

export default function UserFormPage({ mode }: { mode: "create" | "edit" }) {
  const { id } = useParams(); const navigate = useNavigate();
  const roles = useRequest(endpoints.userRoles, []);
  const user = useRequest(() => id ? endpoints.user(id) : Promise.reject(new Error("Missing user")), [id]);
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const save = async (value: UserInput) => {
    setBusy(true); setError("");
    try {
      const result = mode === "create" ? await endpoints.createUser(value) : await endpoints.updateUser(id!, { username: value.username, email: value.email });
      navigate(`/users/${result.id}`, { state: { notice: mode === "create" ? "User created." : "User updated." } });
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not save user"); }
    finally { setBusy(false); }
  };
  const unavailable = (mode === "edit" && (user.loading || user.error)) || roles.loading || roles.error;
  return <DashboardLayout><div className="page-title-row"><PageTitle eyebrow="Administration" title={mode === "create" ? "Add user" : "Edit user"} copy={mode === "create" ? "Create a secured HIOP account." : "Update non-sensitive account information."}/><Link className="secondary-action" to={id ? `/users/${id}` : "/users"}>Cancel</Link></div>{error && <Toast message={error} tone="error"/>}{unavailable ? <Feedback loading={user.loading || roles.loading} error={user.error || roles.error} onRetry={() => { void user.reload(); void roles.reload(); }}/> : <section className="panel form-panel"><UserForm user={mode === "edit" ? (user.data ?? undefined) : undefined} roles={roles.data ?? []} busy={busy} onSubmit={save}/></section>}</DashboardLayout>;
}
