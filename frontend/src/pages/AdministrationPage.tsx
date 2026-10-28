import { formatDateTime } from "../lib/dateTime";
import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Feedback } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import { downloadExportFile } from "../lib/brandedWordExport";
import { PageTitle } from "./DashboardPage";
import "../styles/administration.css";
import { isDesktopMode } from "../lib/appMode";

export default function AdministrationPage(){
  const location=useLocation(); const mode=location.pathname.endsWith("/roles")?"roles":location.pathname.endsWith("/audit")?"audit":"overview";
  const me=useRequest(endpoints.me,[]);
  const users=useRequest(endpoints.users,[]);
  const roles=useRequest(endpoints.roleDefinitions,[]);
  const [search,setSearch]=useState("");const [actor,setActor]=useState("");const [action,setAction]=useState("");const [entityType,setEntityType]=useState("");const [outcome,setOutcome]=useState<""|"success"|"failure">("");const [propertyId,setPropertyId]=useState("");const [startDate,setStartDate]=useState("");const [endDate,setEndDate]=useState("");const [page,setPage]=useState(1);
  const [exporting,setExporting]=useState(false);const [exportError,setExportError]=useState("");
  const [exportFormat,setExportFormat]=useState<"csv"|"word">("csv");
  const auditFilters={search:search||undefined,actor:actor||undefined,action:action||undefined,entity_type:entityType||undefined,outcome:outcome||undefined,property_id:propertyId||undefined,start_date:startDate?`${startDate}T00:00:00Z`:undefined,end_date:endDate?`${endDate}T23:59:59.999Z`:undefined,page,page_size:25,sort_order:"desc" as const};
  const audit=useRequest(()=>endpoints.auditLogs(auditFilters),[search,actor,action,entityType,outcome,propertyId,startDate,endDate,page]);
  const exportLogs=async()=>{setExporting(true);setExportError("");try{const {blob,filename}=await endpoints.exportAuditLogs({...auditFilters,page:undefined,page_size:undefined});await downloadExportFile(exportFormat,"Administrative Audit Log",filename,blob)}catch(x){setExportError(x instanceof Error?x.message:"Export failed. Please try again.")}finally{setExporting(false)}};
  const resetAuditFilters=()=>{setSearch("");setActor("");setAction("");setEntityType("");setOutcome("");setPropertyId("");setStartDate("");setEndDate("");setPage(1)};
  if(me.loading)return <DashboardLayout><Feedback loading/></DashboardLayout>;
  if(me.data?.role!=="admin")return <DashboardLayout><Feedback error="Administration is restricted to the Organization Administrator."/></DashboardLayout>;
  return <DashboardLayout><PageTitle eyebrow="Administration" title={mode==="roles"?"Roles & access":mode==="audit"?"Audit log":"Administration"} copy={mode==="roles"?"A small, explicit role model for hotel IT operations.":mode==="audit"?"Trace real administrative actions to authenticated users.":"Choose a focused administration workspace instead of searching through one large settings page."}/>
    {mode==="overview"&&<>
    <section className="operations-guide admin-guide" aria-label="Administration guide"><div><span>Configure</span><strong>Organization first</strong><p>Set up properties, departments, locations, and services before managing operational records.</p></div><div><span>Control</span><strong>Access and integrations</strong><p>Keep roles, credentials, and external connections under administrator control.</p></div><div><span>Verify</span><strong>Audit what changed</strong><p>Use the audit log to confirm who changed administrative settings and when.</p></div></section>
    <section className="admin-access-grid">
      <article className="panel admin-entry"><Icon name="hierarchy"/><div><h2>Organization</h2><p>Manage organization details, departments, locations, and services.</p></div><Link className="primary-action" to="/administration/organization">Open organization</Link></article>
      <article className="panel admin-entry"><Icon name="users"/><div><h2>Users</h2><p>{users.data?.length??0} manageable account(s). Accounts are deactivated rather than deleted.</p></div><Link className="primary-action" to="/users">Manage users</Link></article>
      <article className="panel admin-entry"><Icon name="lock"/><div><h2>Roles & access</h2><p>Review organization roles and their backend-enforced permissions.</p></div><Link className="secondary-action" to="/administration/roles">Review roles</Link></article>
      <article className="panel admin-entry"><Icon name="network"/><div><h2>Integrations</h2><p>Configure SNMP, Active Directory, and other external system integrations.</p></div><Link className="secondary-action" to="/administration/integrations">Configure integrations</Link></article>
      <article className="panel admin-entry"><Icon name="audit"/><div><h2>Audit log</h2><p>Review organization administrative and security activity.</p></div><Link className="secondary-action" to="/administration/audit">Open audit log</Link></article>
      <article className="panel admin-entry"><Icon name="server"/><div><h2>Settings</h2><p>Existing operational configuration. Secrets and credentials are never displayed.</p></div><Link className="secondary-action" to="/settings">Open settings</Link></article>
      {isDesktopMode ? <article className="panel admin-entry"><Icon name="network"/><div><h2>Site Server</h2><p>Check this hotel's HIOP service, private database, and scheduler.</p></div><Link className="secondary-action" to="/administration/agents">Open Site Server status</Link></article> : <article className="panel admin-entry"><Icon name="devices"/><div><h2>Billing</h2><p>Review the organization's plan, trial, subscription status, usage and limits.</p></div><Link className="secondary-action" to="/administration/billing">Open billing</Link></article>}
    </section></>}
    {mode==="roles"&&<section className="panel admin-roles"><header><div><span>Organization access</span><h2>Roles and permissions</h2><p>Platform authority is private and managed only from the Platform Control Center.</p></div><strong>{roles.data?.length??3} organization roles</strong></header>{roles.loading||roles.error?<Feedback loading={roles.loading} error={roles.error}/>:<div>{roles.data?.map(role=><article key={role.key}><div><strong>{role.name}</strong><span>{role.description}</span></div><ul>{role.permissions.map(permission=><li key={permission}>{permission.replaceAll("_"," ").replaceAll("."," · ")}</li>)}</ul></article>)}</div>}</section>}
    {mode==="audit"&&<section className="panel admin-audit"><header><div><span>Accountability</span><h2>Administrative audit log</h2><p>{audit.data?`${audit.data.total} matching record(s)`:"Filter administrative activity by date, user, action, area, outcome, or property."}</p></div><label>Format<select value={exportFormat} onChange={event=>setExportFormat(event.target.value as "csv"|"word")}><option value="csv">CSV</option><option value="word">Word report (.docx)</option></select></label><button className="secondary-action" disabled={exporting} onClick={()=>void exportLogs()}>{exporting?"Preparing export…":`Export filtered results (${exportFormat==="csv"?"CSV":"Word"})`}</button></header>
      {exportError&&<p role="alert" className="form-error">{exportError}</p>}
      <form className="admin-audit-filters" onSubmit={event=>{event.preventDefault();setPage(1);void audit.reload()}}>
        <label>Search<input value={search} onChange={event=>{setSearch(event.target.value);setPage(1)}} placeholder="Description or record"/></label>
        <label>From<input type="date" value={startDate} onChange={event=>{setStartDate(event.target.value);setPage(1)}}/></label>
        <label>To<input type="date" value={endDate} onChange={event=>{setEndDate(event.target.value);setPage(1)}}/></label>
        <label>User<select value={actor} onChange={event=>{setActor(event.target.value);setPage(1)}}><option value="">All users</option>{audit.data?.options.actors.map(value=><option key={value}>{value}</option>)}</select></label>
        <label>Action<select value={action} onChange={event=>{setAction(event.target.value);setPage(1)}}><option value="">All actions</option>{audit.data?.options.actions.map(value=><option key={value} value={value}>{value.replaceAll("_"," ")}</option>)}</select></label>
        <label>Area / module<select value={entityType} onChange={event=>{setEntityType(event.target.value);setPage(1)}}><option value="">All areas</option>{audit.data?.options.entity_types.map(value=><option key={value}>{value}</option>)}</select></label>
        <label>Outcome<select value={outcome} onChange={event=>{setOutcome(event.target.value as ""|"success"|"failure");setPage(1)}}><option value="">All outcomes</option><option value="success">Successful</option><option value="failure">Failed</option></select></label>
        <label>Property<select value={propertyId} onChange={event=>{setPropertyId(event.target.value);setPage(1)}}><option value="">All properties in organization</option>{audit.data?.options.properties.map(value=><option key={value.id} value={value.id}>{value.name}</option>)}</select></label>
        <button type="button" className="secondary-action" onClick={resetAuditFilters}>Reset filters</button>
      </form>
      {exportError&&<p role="alert">{exportError}</p>}{audit.error?<Feedback error={audit.error}/>:audit.loading&&!audit.data?<Feedback loading/>:!audit.data?.items.length?<Feedback empty="No audit records match these filters."/>:<><div className="admin-audit-list">{audit.data.items.map(entry=><article key={entry.id}><div><strong>{entry.action.replaceAll("_"," ")}</strong><span>{entry.actor} · {entry.entity_type} {entry.entity_id} · {entry.outcome==="failure"?"Failed":"Successful"}</span><small>{entry.description}</small></div><time>{formatDateTime(entry.created_at)}</time></article>)}</div><footer className="admin-audit-pagination"><span>Page {audit.data.page} of {audit.data.pages}</span><button className="secondary-action" disabled={page<=1||audit.loading} onClick={()=>setPage(value=>value-1)}>Previous</button><button className="secondary-action" disabled={page>=audit.data.pages||audit.loading} onClick={()=>setPage(value=>value+1)}>Next</button></footer></>}</section>}
  </DashboardLayout>
}
