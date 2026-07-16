import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Feedback } from "../components/Feedback";
import { Icon, type IconName } from "../components/Icon";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import { PageTitle } from "./DashboardPage";

const PAGE_SIZE = 10;

export default function UsersPage() {
  const users = useRequest(endpoints.users, []);
  const me = useRequest(endpoints.me, []);
  const roles = useRequest(endpoints.userRoles, []);
  const [query, setQuery] = useState("");
  const [role, setRole] = useState("all");
  const [active, setActive] = useState("all");
  const [page, setPage] = useState(1);

  const all = useMemo(() => users.data ?? [], [users.data]);
  const rows = useMemo(
    () => all.filter((user) =>
      `${user.username} ${user.email}`.toLowerCase().includes(query.trim().toLowerCase()) &&
      (role === "all" || user.role === role) &&
      (active === "all" || String(user.is_active) === active)),
    [all, query, role, active],
  );
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const currentPage = Math.min(page, pages);
  const visible = rows.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const stats: Array<{ label: string; value: number; icon: IconName; tone: string }> = [
    { label: "Total users", value: all.length, icon: "users", tone: "gold" },
    { label: "Active", value: all.filter((user) => user.is_active).length, icon: "check", tone: "success" },
    { label: "Inactive", value: all.filter((user) => !user.is_active).length, icon: "lock", tone: "muted" },
    { label: "Administrators", value: all.filter((user) => user.role === "admin").length, icon: "settings", tone: "gold" },
    { label: "Technicians", value: all.filter((user) => user.role === "technician").length, icon: "devices", tone: "success" },
  ];
  const resetPage = () => setPage(1);

  return <DashboardLayout>
    <div className="page-title-row users-title-row">
      <PageTitle eyebrow="Administration" title="Team & access" copy="Manage accounts, access levels, and sign-in availability across HIOP." />
      {me.data?.role === "admin" && <Link className="primary-action" to="/users/new"><Icon name="users" size={16} />Add user</Link>}
    </div>

    <section className="users-summary" aria-label="User account summary">
      {stats.map((stat) => <article className={`users-stat ${stat.tone}`} key={stat.label}>
        <span className="users-stat-icon"><Icon name={stat.icon} size={18} /></span>
        <div><span>{stat.label}</span><strong>{stat.value}</strong></div>
      </article>)}
    </section>

    <section className="panel users-directory">
      <header className="users-directory-head">
        <div><h2>User directory</h2><p>{rows.length} {rows.length === 1 ? "account" : "accounts"} shown</p></div>
        <div className="users-toolbar">
          <label className="users-search"><Icon name="search" size={16} /><input aria-label="Search users" value={query} onChange={(event) => { setQuery(event.target.value); resetPage(); }} placeholder="Search username or email" /></label>
          <select aria-label="Filter by role" value={role} onChange={(event) => { setRole(event.target.value); resetPage(); }}><option value="all">All roles</option>{roles.data?.map((item) => <option key={item} value={item}>{item[0].toUpperCase() + item.slice(1)}</option>)}</select>
          <select aria-label="Filter by status" value={active} onChange={(event) => { setActive(event.target.value); resetPage(); }}><option value="all">All statuses</option><option value="true">Active</option><option value="false">Inactive</option></select>
        </div>
      </header>

      {users.loading || users.error || !visible.length
        ? <Feedback loading={users.loading} error={users.error} empty={all.length ? "No users match these filters." : "No user accounts are available."} onRetry={users.reload} />
        : <div className="users-table-wrap"><table className="users-table"><thead><tr><th>User</th><th>Email</th><th>Role</th><th>Status</th><th>Created</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{visible.map((user) => <tr key={user.id}>
          <td data-label="User"><div className="users-person"><span className="avatar">{user.username.slice(0, 2).toUpperCase()}</span><div><strong>{user.username}</strong><small>{user.id === me.data?.id ? "Your account" : "Team member"}</small></div></div></td>
          <td data-label="Email"><a className="users-email" href={`mailto:${user.email}`}>{user.email}</a></td>
          <td data-label="Role"><span className={`role-badge role-${user.role}`}>{user.role}</span></td>
          <td data-label="Status"><span className={`status-badge ${user.is_active ? "online" : "offline"}`}><i />{user.is_active ? "Active" : "Inactive"}</span></td>
          <td data-label="Created"><time>{user.created_at ? new Date(user.created_at).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" }) : "Not tracked"}</time></td>
          <td className="users-actions"><Link className="users-view" to={`/users/${user.id}`}>View <Icon name="arrow" size={14} /></Link></td>
        </tr>)}</tbody></table></div>}

      {rows.length > PAGE_SIZE && <nav className="pagination users-pagination" aria-label="User pages"><button disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}>Previous</button>{Array.from({ length: pages }, (_, index) => index + 1).map((number) => <button className={number === currentPage ? "active" : ""} key={number} onClick={() => setPage(number)}>{number}</button>)}<button disabled={currentPage === pages} onClick={() => setPage(currentPage + 1)}>Next</button></nav>}
    </section>
  </DashboardLayout>;
}
