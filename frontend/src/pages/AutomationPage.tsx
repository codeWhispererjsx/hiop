import {useEffect,useState} from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import {Feedback} from "../components/Feedback";
import {PageTitle} from "./DashboardPage";
import {endpoints} from "../lib/api";
import type {SettingsBundle} from "../lib/types";

export default function AutomationPage(){
  const [settings,setSettings]=useState<SettingsBundle>();
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [saving,setSaving]=useState(false);
  useEffect(()=>{let active=true;endpoints.settings().then(value=>{if(active)setSettings(value)}).catch(e=>{if(active)setError(e instanceof Error?e.message:"Settings could not be loaded.")});return()=>{active=false}},[]);
  if(error||!settings)return <DashboardLayout><PageTitle eyebrow="Automate" title="Simple automation" copy="Schedule routine operational checks."/><Feedback loading={!error} error={error||undefined}/></DashboardLayout>;
  const save=async()=>{setSaving(true);setNotice("");try{let next=await endpoints.updateNetworkSettings(settings.network);next=await endpoints.updateNotificationSettings(settings.notifications);setSettings(next);setNotice("Automation settings saved.")}catch(e){setError(e instanceof Error?e.message:"Settings could not be saved.")}finally{setSaving(false)}};
  const network=settings.network,notifications=settings.notifications;
  return <DashboardLayout><PageTitle eyebrow="Automate" title="Simple automation" copy="Schedule scans, monitoring, notifications, and offline-device incidents."/>{notice&&<p className="inline-notice" role="status">{notice}</p>}<section className="panel automation-panel"><header className="section-head"><div><h2>Operational schedules</h2><p>Choose which routine checks HIOP should run automatically.</p></div></header><div className="settings-toggles"><Toggle label="Scheduled network scans" detail={`Every ${network.scan_interval_minutes} minutes`} checked={network.automatic_scanning} onChange={checked=>setSettings({...settings,network:{...network,automatic_scanning:checked}})}/><Toggle label="Scheduled monitoring" detail="Continuously check approved devices" checked={network.automatic_scanning} onChange={checked=>setSettings({...settings,network:{...network,automatic_scanning:checked}})}/><Toggle label="Email notifications" detail="Send configured operational notifications" checked={notifications.email_notifications} onChange={checked=>setSettings({...settings,notifications:{...notifications,email_notifications:checked}})}/><Toggle label="Automatic offline incidents" detail="Create an incident when a device becomes unreachable" checked={network.automatic_offline_tickets} onChange={checked=>setSettings({...settings,network:{...network,automatic_offline_tickets:checked}})}/></div><div className="automation-controls"><label><span>Scan interval</span><small>Minutes between automatic network scans</small><input type="number" min="5" max="1440" value={network.scan_interval_minutes} onChange={e=>setSettings({...settings,network:{...network,scan_interval_minutes:Number(e.target.value)}})}/></label><button className="primary-action" disabled={saving} onClick={()=>void save()}>{saving?"Saving...":"Save automation"}</button></div></section></DashboardLayout>;
}

function Toggle({label,detail,checked,onChange}:{label:string;detail:string;checked:boolean;onChange:(checked:boolean)=>void}){return <label className="settings-toggle"><input type="checkbox" checked={checked} onChange={event=>onChange(event.target.checked)}/><span><strong>{label}</strong><small>{detail}</small></span></label>}
