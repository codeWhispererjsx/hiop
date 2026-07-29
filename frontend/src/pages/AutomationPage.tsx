import {useEffect,useState,type FormEvent} from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import {Feedback} from "../components/Feedback";
import {StatCard} from "../components/StatCard";
import {endpoints} from "../lib/api";
import type {AutomationApproval,AutomationEvent,AutomationRun,AutomationSchedule,AutomationTrigger,AutomationVersion,AutomationWorkflow} from "../lib/types";

export default function AutomationPage(){
  const [workflows,setWorkflows]=useState<AutomationWorkflow[]>([]);
  const [runs,setRuns]=useState<AutomationRun[]>([]);
  const [approvals,setApprovals]=useState<AutomationApproval[]>([]);
  const [triggers,setTriggers]=useState<AutomationTrigger[]>([]);
  const [schedules,setSchedules]=useState<AutomationSchedule[]>([]);
  const [events,setEvents]=useState<AutomationEvent[]>([]);
  const [schedulerRunning,setSchedulerRunning]=useState(false);
  const [selected,setSelected]=useState<AutomationWorkflow>();
  const [versions,setVersions]=useState<AutomationVersion[]>([]);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);

  const load=async()=>{
    try{
      const [w,r,a,t,s,h,e]=await Promise.all([
        endpoints.automationWorkflows(),endpoints.automationRuns(),endpoints.automationApprovals(),
        endpoints.automationTriggers(),endpoints.automationSchedules(),endpoints.automationSchedulerStatus(),
        endpoints.automationEvents(),
      ]);
      setWorkflows(w.items);setRuns(r.items);setApprovals(a.items);setTriggers(t.items);
      setSchedules(s.items);setSchedulerRunning(h.scheduler_running);setEvents(e.items);setError("");
    }catch(e){setError(e instanceof Error?e.message:"Unable to load automation")}
  };
  useEffect(()=>{
    let active=true;
    void Promise.all([
      endpoints.automationWorkflows(),endpoints.automationRuns(),endpoints.automationApprovals(),
      endpoints.automationTriggers(),endpoints.automationSchedules(),endpoints.automationSchedulerStatus(),
      endpoints.automationEvents(),
    ]).then(([w,r,a,t,s,h,e])=>{
      if(!active)return;
      setWorkflows(w.items);setRuns(r.items);setApprovals(a.items);setTriggers(t.items);
      setSchedules(s.items);setSchedulerRunning(h.scheduler_running);setEvents(e.items);
    }).catch(e=>{if(active)setError(e instanceof Error?e.message:"Unable to load automation")});
    return()=>{active=false};
  },[]);

  const choose=async(workflow:AutomationWorkflow)=>{
    setSelected(workflow);
    try{setVersions((await endpoints.automationVersions(workflow.id)).items)}
    catch(e){setError(e instanceof Error?e.message:"Unable to load versions")}
  };
  const create=async(e:FormEvent<HTMLFormElement>)=>{
    e.preventDefault();const form=e.currentTarget;const data=new FormData(form);setBusy(true);
    try{
      await endpoints.createAutomationWorkflow({property_id:localStorage.getItem("hiop.active_property_id")||null,name:String(data.get("name")),code:String(data.get("code")),workflow_category:String(data.get("category"))});
      form.reset();await load();
    }catch(err){setError(err instanceof Error?err.message:"Unable to create workflow")}finally{setBusy(false)}
  };
  const selectedVersion=versions.find(version=>version.status==="approved")??versions[0];
  const createSchedule=async(e:FormEvent<HTMLFormElement>)=>{
    e.preventDefault();if(!selected||!selectedVersion)return;const form=e.currentTarget;const data=new FormData(form);setBusy(true);
    try{
      await endpoints.createAutomationSchedule({workflow_id:selected.id,workflow_version_id:selectedVersion.id,property_id:selected.property_id,name:String(data.get("name")),schedule_type:"interval",timezone:"UTC",interval_minutes:Number(data.get("interval")),enabled:false,approval_mode:"use_workflow_policy",maintenance_behavior:"suppress"});
      form.reset();await load();
    }catch(err){setError(err instanceof Error?err.message:"Unable to create schedule")}finally{setBusy(false)}
  };
  const createTrigger=async(e:FormEvent<HTMLFormElement>)=>{
    e.preventDefault();if(!selected||!selectedVersion)return;const form=e.currentTarget;const data=new FormData(form);setBusy(true);
    try{
      await endpoints.createAutomationTrigger({workflow_id:selected.id,workflow_version_id:selectedVersion.id,property_id:selected.property_id,event_type:String(data.get("event")),trigger_mode:"request_approval",cooldown_seconds:300,deduplication_window_seconds:300,correlation_window_seconds:300,maximum_runs_per_window:5,run_window_seconds:3600,delay_seconds:0,approval_mode:"always_require",maintenance_behavior:"suppress",blackout_behavior:"suppress",filter_definition:{},condition_definition:{},input_mapping:{}});
      form.reset();await load();
    }catch(err){setError(err instanceof Error?err.message:"Unable to create trigger")}finally{setBusy(false)}
  };
  const changeSchedule=async(schedule:AutomationSchedule)=>{
    setBusy(true);try{await endpoints.setAutomationSchedule(schedule.id,!schedule.enabled);await load()}catch(e){setError(e instanceof Error?e.message:"Unable to update schedule")}finally{setBusy(false)}
  };
  const changeTrigger=async(trigger:AutomationTrigger)=>{
    setBusy(true);try{await endpoints.setAutomationTrigger(trigger.id,!trigger.enabled);await load()}catch(e){setError(e instanceof Error?e.message:"Unable to update trigger")}finally{setBusy(false)}
  };
  const runNow=async(schedule:AutomationSchedule)=>{
    if(!window.confirm(`Run ${schedule.name} now using its approved pinned version?`))return;
    setBusy(true);try{await endpoints.runAutomationSchedule(schedule.id);await load()}catch(e){setError(e instanceof Error?e.message:"Unable to start schedule")}finally{setBusy(false)}
  };

  return <DashboardLayout onLiveEvent={event=>{if((event.type??event.event)?.startsWith("automation_"))void load()}}>
    <header className="page-title"><div><span className="eyebrow">Approval-safe operations</span><h1>Automation</h1><p>Build approved workflows, manage bounded schedules and internal triggers, and review execution history.</p></div></header>
    {error&&<Feedback error={error}/>}
    <section className="stats-grid">
      <StatCard label="Workflows" value={workflows.length} detail="Property scoped" icon="settings"/>
      <StatCard label="Schedules" value={schedules.length} detail={schedulerRunning?"Scheduler running":"Scheduler unavailable"} icon="audit"/>
      <StatCard label="Event triggers" value={triggers.length} detail="Deduplicated and throttled" icon="network"/>
      <StatCard label="Pending approvals" value={approvals.length} detail="Human checkpoints" icon="alerts"/>
    </section>
    <section className="hospitality-panel"><div className="panel-heading"><div><h2>Create workflow</h2><span>Definitions remain inactive until separately approved and enabled.</span></div></div><form className="topology-form" onSubmit={create}><label>Name<input name="name" required maxLength={160}/></label><label>Code<input name="code" required maxLength={60}/></label><label>Category<select name="category"><option value="custom">Custom</option><option value="incident_response">Incident response</option><option value="notification">Notification</option><option value="reporting">Reporting</option></select></label><button disabled={busy}>{busy?"Creating…":"Create workflow"}</button></form></section>
    <section className="hospitality-panel"><div className="panel-heading"><div><h2>Workflow definitions</h2><span>Select a workflow to inspect immutable versions.</span></div></div>{!workflows.length?<Feedback empty="No workflows defined."/>:<div className="hospitality-grid">{workflows.map(workflow=><button className="hospitality-card" key={workflow.id} onClick={()=>void choose(workflow)}><strong>{workflow.name}</strong><span>{workflow.code} · {workflow.workflow_category}</span><small>{workflow.status}{workflow.enabled?" · enabled":""}</small></button>)}</div>}</section>
    {selected&&<section className="hospitality-panel"><div className="panel-heading"><div><h2>{selected.name} versions</h2><span>Checksum-backed history and approval status.</span></div></div>{!versions.length?<Feedback empty="No versions created yet."/>:<div className="hospitality-grid">{versions.map(version=><article className="hospitality-card" key={version.id}><strong>Version {version.version_number}</strong><span>{version.status}</span><small>{version.checksum?.slice(0,16)??"No checksum"}</small></article>)}</div>}</section>}
    {selected&&selectedVersion&&<section className="hospitality-panel"><div className="panel-heading"><div><h2>Safe orchestration</h2><span>New schedules and triggers are disabled or approval-gated by default.</span></div></div><div className="hospitality-grid"><form className="hospitality-card topology-form" onSubmit={createSchedule}><strong>Recurring schedule</strong><label>Name<input name="name" required maxLength={120}/></label><label>Interval minutes<input name="interval" type="number" min={5} max={10080} defaultValue={60}/></label><button disabled={busy}>Create disabled schedule</button></form><form className="hospitality-card topology-form" onSubmit={createTrigger}><strong>Internal event trigger</strong><label>Registered event<select name="event"><option value="device_offline">Device offline</option><option value="critical_alert_created">Critical alert created</option><option value="technology_service_degraded">Technology service degraded</option><option value="configuration_drift_detected">Configuration drift detected</option></select></label><button disabled={busy}>Create approval-gated trigger</button></form></div></section>}
    <section className="hospitality-panel"><div className="panel-heading"><div><h2>Schedules and triggers</h2><span>Stable jobs, cooldowns, replay protection, and storm limits are backend enforced.</span></div></div>{!schedules.length&&!triggers.length?<Feedback empty="No schedules or triggers configured."/>:<div className="hospitality-grid">{schedules.map(schedule=><article className="hospitality-card" key={schedule.id}><strong>{schedule.name}</strong><span>{schedule.schedule_type} · {schedule.enabled?"enabled":"disabled"}</span><small>{schedule.last_run_status??"Never run"}</small><button disabled={busy} onClick={()=>void changeSchedule(schedule)}>{schedule.enabled?"Disable":"Enable"}</button>{schedule.enabled&&<button disabled={busy} onClick={()=>void runNow(schedule)}>Run now</button>}</article>)}{triggers.map(trigger=><article className="hospitality-card" key={trigger.id}><strong>{trigger.event_type}</strong><span>{trigger.trigger_mode} · {trigger.enabled?"enabled":"disabled"}</span><small>{trigger.maximum_runs_per_window} runs / window · {trigger.approval_mode}</small><button disabled={busy} onClick={()=>void changeTrigger(trigger)}>{trigger.enabled?"Disable":"Enable"}</button></article>)}</div>}</section>
    <section className="hospitality-panel"><div className="panel-heading"><div><h2>Internal event explorer</h2><span>Safe envelope metadata only; payloads and secrets are not displayed.</span></div></div>{!events.length?<Feedback empty="No internal automation events."/>:<div className="table-shell"><table><thead><tr><th>Time</th><th>Event</th><th>Module</th><th>Severity</th><th>Processing</th></tr></thead><tbody>{events.slice(0,25).map(event=><tr key={event.id}><td>{new Date(event.occurred_at).toLocaleString()}</td><td>{event.event_type}</td><td>{event.source_module??"—"}</td><td>{event.severity??"—"}</td><td>{event.processing_status}</td></tr>)}</tbody></table></div>}</section>
    <section className="hospitality-panel"><div className="panel-heading"><div><h2>Recent runs</h2><span>Live updates refresh this bounded list.</span></div></div>{!runs.length?<Feedback empty="No workflow runs."/>:<div className="hospitality-grid">{runs.slice(0,12).map(run=><article className="hospitality-card" key={run.id}><strong>{run.status}</strong><span>{run.trigger_type}</span><small>{new Date(run.created_at).toLocaleString()}</small></article>)}</div>}</section>
  </DashboardLayout>
}
