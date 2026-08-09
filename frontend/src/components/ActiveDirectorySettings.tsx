/* eslint-disable react-hooks/set-state-in-effect */
import { useEffect, useState, type FormEvent } from "react";
import { Feedback } from "./Feedback";
import { endpoints } from "../lib/api";
import type { ADConnection } from "../lib/types";

const initial={name:"",domain_name:"",server_host:"",server_port:636,base_dn:"",computer_search_base:"",bind_username:"",bind_secret:"",use_ssl:true,use_start_tls:false,verify_tls:true,authentication_method:"ldaps",connection_timeout_seconds:10,page_size:100,enabled:true};

export function ActiveDirectorySettings(){
  const [connections,setConnections]=useState<ADConnection[]>([]);const [form,setForm]=useState(initial);const [loading,setLoading]=useState(true);const [busy,setBusy]=useState("");const [message,setMessage]=useState("");const [error,setError]=useState("");
  const load=async()=>{setLoading(true);try{setConnections((await endpoints.adConnections()).items)}catch(caught){setError(caught instanceof Error?caught.message:"Active Directory configuration could not be loaded.")}finally{setLoading(false)}};
  useEffect(()=>{void load()},[]);
  const create=async(event:FormEvent)=>{event.preventDefault();setBusy("create");setError("");try{await endpoints.createADConnection({...form,computer_search_base:form.computer_search_base||null,user_search_base:null,group_search_base:null});setForm(initial);setMessage("Read-only Active Directory connection saved.");await load()}catch(caught){setError(caught instanceof Error?caught.message:"Connection could not be saved.")}finally{setBusy("")}};
  const test=async(row:ADConnection)=>{setBusy(row.id);setError("");try{const response=await endpoints.testADConnection(row.id);setMessage(response.overall_status==="success"?`${row.name} connected successfully.`:`${row.name} connection test failed safely.`);await load()}catch(caught){setError(caught instanceof Error?caught.message:"Connection test failed.")}finally{setBusy("")}};
  const toggle=async(row:ADConnection)=>{setBusy(row.id);try{await endpoints.updateADConnection(row.id,{enabled:!row.enabled});await load()}catch(caught){setError(caught instanceof Error?caught.message:"Connection status could not be changed.")}finally{setBusy("")}};
  if(loading)return <Feedback loading/>;
  return <div className="settings-panel-body"><p>Configure a bounded, read-only computer-object lookup. LDAPS and certificate verification are enabled by default. Passwords are encrypted and never returned.</p>{error&&<Feedback error={error}/>} {message&&<p role="status" className="settings-note">{message}</p>}
    {connections.length>0&&<div className="hierarchy-summary">{connections.map(row=><article key={row.id}><div><strong>{row.name}</strong><span>{row.domain_name} · {row.server_host}:{row.server_port} · {row.use_ssl?"LDAPS":"StartTLS"}</span><small>{row.secret_configured?"Credential securely stored":"Credential not configured"} · {row.last_test_status||"Not tested"}</small></div><div className="row-actions"><button disabled={busy===row.id} onClick={()=>void test(row)}>Test connection</button><button disabled={busy===row.id} onClick={()=>void toggle(row)}>{row.enabled?"Disable":"Enable"}</button></div></article>)}</div>}
    <form className="settings-form-grid" onSubmit={create}>
      <label><span>Connection name</span><input required value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></label>
      <label><span>Domain</span><input required placeholder="adlosha.local" value={form.domain_name} onChange={e=>setForm({...form,domain_name:e.target.value})}/></label>
      <label><span>LDAPS server</span><input required placeholder="dc01.adlosha.local" value={form.server_host} onChange={e=>setForm({...form,server_host:e.target.value})}/></label>
      <label><span>Port</span><input required type="number" min="1" max="65535" value={form.server_port} onChange={e=>setForm({...form,server_port:Number(e.target.value)})}/></label>
      <label><span>Base DN</span><input required placeholder="DC=adlosha,DC=local" value={form.base_dn} onChange={e=>setForm({...form,base_dn:e.target.value})}/></label>
      <label><span>Computer search base (optional)</span><input placeholder="OU=Computers,DC=adlosha,DC=local" value={form.computer_search_base} onChange={e=>setForm({...form,computer_search_base:e.target.value})}/></label>
      <label><span>Service account</span><input required autoComplete="username" value={form.bind_username} onChange={e=>setForm({...form,bind_username:e.target.value})}/></label>
      <label><span>Bind password</span><input required type="password" autoComplete="new-password" value={form.bind_secret} onChange={e=>setForm({...form,bind_secret:e.target.value})}/></label>
      <label><span>Secure transport</span><select value={form.use_ssl?"ldaps":"start_tls"} onChange={e=>setForm({...form,use_ssl:e.target.value==="ldaps",use_start_tls:e.target.value==="start_tls",server_port:e.target.value==="ldaps"?636:389,authentication_method:e.target.value})}><option value="ldaps">LDAPS</option><option value="start_tls">LDAP with StartTLS</option></select></label>
      <label><span>Enabled</span><select value={form.enabled?"yes":"no"} onChange={e=>setForm({...form,enabled:e.target.value==="yes"})}><option value="yes">Enabled</option><option value="no">Disabled</option></select></label>
      <button className="primary-action" disabled={busy==="create"}>{busy==="create"?"Saving…":"Save AD connection"}</button>
    </form><p className="settings-note">HIOP only reads computer attributes. It cannot create, modify, move, disable, or delete Active Directory objects.</p>
  </div>;
}
