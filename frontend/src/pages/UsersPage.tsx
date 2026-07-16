import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { PageTitle } from "./DashboardPage";
import { Feedback } from "../components/Feedback";
import { endpoints } from "../lib/api";
import { useRequest } from "../hooks/useRequest";

const PAGE_SIZE = 10;
export default function UsersPage() {
  const users = useRequest(endpoints.users, []); const me = useRequest(endpoints.me, []); const roles = useRequest(endpoints.userRoles, []);
  const [query,setQuery]=useState(""); const [role,setRole]=useState("all"); const [active,setActive]=useState("all"); const [page,setPage]=useState(1);
  const rows=useMemo(()=>(users.data??[]).filter(u=>(`${u.username} ${u.email}`.toLowerCase().includes(query.toLowerCase()))&&(role==="all"||u.role===role)&&(active==="all"||String(u.is_active)===active)),[users.data,query,role,active]);
  const pages=Math.max(1,Math.ceil(rows.length/PAGE_SIZE)); const currentPage=Math.min(page,pages); const visible=rows.slice((currentPage-1)*PAGE_SIZE,currentPage*PAGE_SIZE); const all=users.data??[];
  const stats=[['Total users',all.length],['Active',all.filter(u=>u.is_active).length],['Inactive',all.filter(u=>!u.is_active).length],['Administrators',all.filter(u=>u.role==='admin').length],['Technicians',all.filter(u=>u.role==='technician').length]];
  return <DashboardLayout><div className="page-title-row"><PageTitle eyebrow="Administration" title="Users & roles" copy="Manage real accounts, access levels and sign-in availability."/>{me.data?.role==='admin'&&<Link className="primary-action" to="/users/new">Add user</Link>}</div>
    <section className="metric-grid">{stats.map(([label,value])=><article className="metric-card" key={label}><span>{label}</span><strong>{value}</strong></article>)}</section>
    <section className="panel"><div className="users-toolbar"><input aria-label="Search users" value={query} onChange={e=>{setQuery(e.target.value);setPage(1)}} placeholder="Search username or email"/><select aria-label="Filter by role" value={role} onChange={e=>{setRole(e.target.value);setPage(1)}}><option value="all">All roles</option>{roles.data?.map(r=><option key={r} value={r}>{r[0].toUpperCase()+r.slice(1)}</option>)}</select><select aria-label="Filter by status" value={active} onChange={e=>{setActive(e.target.value);setPage(1)}}><option value="all">All statuses</option><option value="true">Active</option><option value="false">Inactive</option></select></div>
    {users.loading||users.error||!visible.length?<Feedback loading={users.loading} error={users.error} empty={all.length?"No users match these filters.":"No user accounts are available."} onRetry={users.reload}/>:<div className="table-scroll"><table className="data-table"><thead><tr><th>User</th><th>Email</th><th>Role</th><th>Status</th><th>Created</th><th>Actions</th></tr></thead><tbody>{visible.map(u=><tr key={u.id}><td><strong>{u.username}</strong></td><td>{u.email}</td><td><span className="role-badge">{u.role}</span></td><td><span className={`status-badge ${u.is_active?'online':'offline'}`}>{u.is_active?'Active':'Inactive'}</span></td><td>{u.created_at?new Date(u.created_at).toLocaleDateString():'Not tracked'}</td><td><Link className="table-link" to={`/users/${u.id}`}>View</Link></td></tr>)}</tbody></table></div>}
    {rows.length>PAGE_SIZE&&<nav className="pagination" aria-label="User pages"><button disabled={currentPage===1} onClick={()=>setPage(currentPage-1)}>Previous</button>{Array.from({length:pages},(_,i)=>i+1).map(n=><button className={n===currentPage?'active':''} key={n} onClick={()=>setPage(n)}>{n}</button>)}<button disabled={currentPage===pages} onClick={()=>setPage(currentPage+1)}>Next</button></nav>}</section></DashboardLayout>;
}
