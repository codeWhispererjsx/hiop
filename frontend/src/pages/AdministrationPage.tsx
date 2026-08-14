import { Link, useLocation } from "react-router-dom";
import { Feedback } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import { PageTitle } from "./DashboardPage";
import "../styles/administration.css";

export default function AdministrationPage(){
  const location=useLocation(); const mode=location.pathname.endsWith("/roles")?"roles":location.pathname.endsWith("/audit")?"audit":"overview";
  const me=useRequest(endpoints.me,[]);
  const users=useRequest(endpoints.users,[]);
  const roles=useRequest(endpoints.roleDefinitions,[]);
  const audit=useRequest(endpoints.administrationAudit,[]);
  if(me.loading)return <DashboardLayout><Feedback loading/></DashboardLayout>;
  if(me.data?.role!=="admin")return <DashboardLayout><Feedback error="Administration is restricted to the Organization Administrator."/></DashboardLayout>;
  return <DashboardLayout><PageTitle eyebrow="V3 operational access checkpoint" title={mode==="roles"?"Roles & access":mode==="audit"?"Audit log":"Administration"} copy={mode==="roles"?"A small, explicit role model for hotel IT operations.":mode==="audit"?"Trace real administrative actions to authenticated users.":"Choose a focused administration workspace instead of searching through one large settings page."}/>
    {mode==="overview"&&<>
    <section className="admin-access-grid">
      <article className="panel admin-entry"><Icon name="hierarchy"/><div><h2>Organization</h2><p>Manage organization details, departments, locations, services and passive local-agent registrations.</p></div><Link className="primary-action" to="/administration/organization">Open organization</Link></article>
      <article className="panel admin-entry"><Icon name="users"/><div><h2>Users</h2><p>{users.data?.length??0} manageable account(s). Accounts are deactivated rather than deleted.</p></div><Link className="primary-action" to="/users">Manage users</Link></article>
      <article className="panel admin-entry"><Icon name="lock"/><div><h2>Roles & access</h2><p>Review organization roles and their backend-enforced permissions.</p></div><Link className="secondary-action" to="/administration/roles">Review roles</Link></article>
      <article className="panel admin-entry"><Icon name="audit"/><div><h2>Audit log</h2><p>Review organization administrative and security activity.</p></div><Link className="secondary-action" to="/administration/audit">Open audit log</Link></article>
      <article className="panel admin-entry"><Icon name="server"/><div><h2>Settings</h2><p>Existing operational configuration. Secrets and credentials are never displayed.</p></div><Link className="secondary-action" to="/settings">Open settings</Link></article>
      <article className="panel admin-entry"><Icon name="devices"/><div><h2>Billing</h2><p>Review the organization's plan, trial, subscription status, usage and limits.</p></div><Link className="secondary-action" to="/administration/billing">Open billing</Link></article>
    </section></>}
    {mode==="roles"&&<section className="panel admin-roles"><header><div><span>Organization access</span><h2>Roles and permissions</h2><p>Platform authority is private and managed only from the Platform Control Center.</p></div><strong>{roles.data?.length??3} organization roles</strong></header>{roles.loading||roles.error?<Feedback loading={roles.loading} error={roles.error}/>:<div>{roles.data?.map(role=><article key={role.key}><div><strong>{role.name}</strong><span>{role.description}</span></div><ul>{role.permissions.map(permission=><li key={permission}>{permission.replaceAll("_"," ").replaceAll("."," · ")}</li>)}</ul></article>)}</div>}</section>}
    {mode==="audit"&&<section className="panel admin-audit"><header><div><span>Accountability</span><h2>Administrative audit log</h2></div><strong>{audit.data?.length??0} recent events</strong></header>{audit.loading||audit.error?<Feedback loading={audit.loading} error={audit.error}/>:!audit.data?.length?<Feedback empty="No actual administrative events have been recorded."/>:<div className="admin-audit-list">{audit.data.slice(0,100).map(entry=><article key={entry.id}><div><strong>{entry.action.replaceAll("_"," ")}</strong><span>{entry.actor} · {entry.entity_type} {entry.entity_id}</span><small>{entry.description}</small></div><time>{new Date(entry.created_at).toLocaleString()}</time></article>)}</div>}</section>}
  </DashboardLayout>
}
