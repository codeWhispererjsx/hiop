import { useState } from "react";
import { NavLink, useLocation, useSearchParams } from "react-router-dom";
import { AnalyticsBarChart, AnalyticsDonut, AnalyticsHeatmap, AnalyticsLineChart } from "../components/AnalyticsCharts";
import { Feedback } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { StatCard } from "../components/StatCard";
import DashboardLayout from "../layouts/DashboardLayout";
import { analyticsApi, downloadAnalyticsJson } from "../lib/analyticsApi";
import { endpoints } from "../lib/api";
import type {
  Alert, AnalyticsAvailability, AnalyticsCapacityAssessment, AnalyticsForecast,
  AnalyticsHealthScore, AnalyticsMetricDefinition, AnalyticsReliability, AnalyticsRun,
  AnalyticsSLAMeasurement, AnalyticsSummary, AnalyticsTrend, CapacitySummary,
  DashboardData, ForecastSummary, ReliabilitySummary, SLASummary,
} from "../lib/types";
import { useRequest } from "../hooks/useRequest";
import { PageTitle } from "./DashboardPage";
import "../styles/analytics.css";

const TABS = ["dashboard","health","capacity","availability","sla","reliability","forecasts","trends","reports"] as const;
type Tab = typeof TABS[number];
const LABELS:Record<Tab,string>={dashboard:"Dashboard",health:"Health",capacity:"Capacity",availability:"Availability",sla:"SLA",reliability:"Reliability",forecasts:"Forecasts",trends:"Trends",reports:"Reports"};

function rangeStart(range:string){const end=new Date();const start=new Date(end);start.setDate(start.getDate()-Number(range||30));return {start:start.toISOString(),end:end.toISOString()}}
function percent(value:number|null|undefined){return value==null?"—":`${value.toFixed(1)}%`}
function duration(seconds:number|null|undefined){if(seconds==null)return "—";if(seconds<60)return `${Math.round(seconds)}s`;if(seconds<3600)return `${(seconds/60).toFixed(1)}m`;if(seconds<86400)return `${(seconds/3600).toFixed(1)}h`;return `${(seconds/86400).toFixed(1)}d`}
function dateLabel(value:string){return new Date(value).toLocaleDateString(undefined,{month:"short",day:"numeric"})}
function statusItems(values:Record<string,number>){return Object.entries(values).map(([label,value])=>({label:label.replaceAll("_"," "),value}))}

export default function AnalyticsPage(){
  const location=useLocation();const [searchParams,setSearchParams]=useSearchParams();
  const segment=location.pathname.split("/").filter(Boolean)[1] as Tab|undefined;const tab=TABS.includes(segment as Tab)?segment as Tab:"dashboard";
  const range=searchParams.get("range")??"30";const bucket=searchParams.get("bucket")??"1_day";const healthStatus=searchParams.get("health")??"";
  const data=useRequest(async()=>{const [summary,capacitySummary,slaSummary,reliabilitySummary,forecastSummary,health,availability,capacity,sla,reliability,forecasts,definitions,runs,dashboard,alerts]=await Promise.all([
    analyticsApi.summary(),analyticsApi.capacitySummary(),analyticsApi.slaSummary(),analyticsApi.reliabilitySummary(),analyticsApi.forecastSummary(),
    analyticsApi.health({page_size:100,status:healthStatus||undefined}),analyticsApi.availability({page_size:100}),analyticsApi.capacity({page_size:100}),
    analyticsApi.slaMeasurements({page_size:100}),analyticsApi.reliability({page_size:100}),analyticsApi.forecasts({page_size:100}),analyticsApi.metricDefinitions(),analyticsApi.runs(),
    endpoints.dashboard(),endpoints.alerts(),
  ]);return {summary,capacitySummary,slaSummary,reliabilitySummary,forecastSummary,health:health.items,availability:availability.items,capacity:capacity.items,sla:sla.items,reliability:reliability.items,forecasts:forecasts.items,definitions:definitions.items,runs:runs.items,dashboard,alerts}},[range,bucket,healthStatus]);
  const setFilter=(key:string,value:string)=>{const next=new URLSearchParams(searchParams);if(value)next.set(key,value);else next.delete(key);setSearchParams(next,{replace:true})};
  return <DashboardLayout><PageTitle eyebrow="Analytics workbench" title={tab==="dashboard"?"Executive analytics":LABELS[tab]} copy="Explainable, backend-calculated infrastructure health, performance, capacity and forecasts." action={<button className="secondary-action" onClick={()=>void data.reload()}><Icon name="network" size={15}/>Refresh</button>}/>
    <nav className="analytics-tabs" aria-label="Analytics sections">{TABS.map(item=><NavLink key={item} end={item==="dashboard"} to={item==="dashboard"?"/analytics":`/analytics/${item}`}>{LABELS[item]}</NavLink>)}</nav>
    <GlobalFilters range={range} bucket={bucket} health={healthStatus} setFilter={setFilter}/>
    {data.loading||data.error||!data.data?<AnalyticsLoading loading={data.loading} error={data.error} retry={data.reload}/>:<AnalyticsContent tab={tab} data={data.data} range={range} bucket={bucket}/>}
  </DashboardLayout>;
}

function GlobalFilters({range,bucket,health,setFilter}:{range:string;bucket:string;health:string;setFilter:(key:string,value:string)=>void}){
  return <section className="analytics-filters" aria-label="Global analytics filters">
    <label>Time range<select value={range} onChange={event=>setFilter("range",event.target.value)}><option value="1">24 hours</option><option value="7">7 days</option><option value="30">30 days</option><option value="90">90 days</option><option value="365">1 year</option></select></label>
    <label>Analytics bucket<select value={bucket} onChange={event=>setFilter("bucket",event.target.value)}><option value="5_minutes">5 minutes</option><option value="15_minutes">15 minutes</option><option value="1_hour">1 hour</option><option value="1_day">1 day</option><option value="1_week">1 week</option></select></label>
    <label>Health status<select value={health} onChange={event=>setFilter("health",event.target.value)}><option value="">All statuses</option>{["excellent","healthy","warning","degraded","critical","unknown"].map(item=><option key={item}>{item}</option>)}</select></label>
    {["Building","Floor","Department","Room","Network zone","Device type","Vendor"].map(label=><label key={label}>{label}<select disabled aria-label={`${label} filter`}><option>Backend scope unavailable</option></select></label>)}
  </section>;
}

type Loaded={
  summary:AnalyticsSummary;capacitySummary:CapacitySummary;slaSummary:SLASummary;
  reliabilitySummary:ReliabilitySummary;forecastSummary:ForecastSummary;
  health:AnalyticsHealthScore[];availability:AnalyticsAvailability[];
  capacity:AnalyticsCapacityAssessment[];sla:AnalyticsSLAMeasurement[];
  reliability:AnalyticsReliability[];forecasts:AnalyticsForecast[];
  definitions:AnalyticsMetricDefinition[];runs:AnalyticsRun[];dashboard:DashboardData;alerts:Alert[];
};
function AnalyticsContent({tab,data,range,bucket}:{tab:Tab;data:Loaded;range:string;bucket:string}){
  if(tab==="dashboard")return <Executive data={data}/>;
  if(tab==="health")return <Health data={data}/>;
  if(tab==="capacity")return <Capacity data={data}/>;
  if(tab==="availability")return <Availability data={data}/>;
  if(tab==="sla")return <SLA data={data}/>;
  if(tab==="reliability")return <Reliability data={data}/>;
  if(tab==="forecasts")return <Forecasts data={data}/>;
  if(tab==="trends")return <TrendExplorer data={data} range={range} bucket={bucket}/>;
  return <AnalyticsReports data={data}/>;
}

function Executive({data}:{data:Loaded}){
  const s=data.summary,c=data.capacitySummary,sl=data.slaSummary,r=data.reliabilitySummary,f=data.forecastSummary;
  const compliance=sl.measurement_count?sl.targets_met/sl.measurement_count*100:null;const confidence=f.highest_confidence?.confidence_score??null;
  return <><section className="stats-grid analytics-kpis">
    <StatCard label="Overall health" value={s.overall_system_health?`${s.overall_system_health.score.toFixed(0)}/100`:"—"} detail={s.overall_system_health?.status??"No system score"} icon="dashboard" tone={s.overall_system_health?.status==="critical"?"danger":"neutral"}/>
    <StatCard label="Device availability" value={percent(s.average_availability)} detail="Measured evidence only" icon="check" tone="success"/>
    <StatCard label="Capacity warnings" value={c.warning_count} detail={`${c.critical_count} critical assessments`} icon="warning" tone="warning"/>
    <StatCard label="SLA compliance" value={percent(compliance)} detail={`${sl.targets_breached} measured breaches`} icon="audit"/>
    <StatCard label="MTTR" value={duration(r.mttr)} detail={`${r.failure_count} confirmed failures`} icon="clock"/>
    <StatCard label="MTBF" value={duration(r.mtbf)} detail={duration(r.total_downtime)+" total downtime"} icon="network"/>
    <StatCard label="Forecast confidence" value={percent(confidence)} detail="Highest current confidence" icon="arrow"/>
    <StatCard label="Devices monitored" value={data.dashboard.devices.total} detail={`${data.dashboard.devices.online} online`} icon="devices"/>
    <StatCard label="Active alerts" value={data.alerts.filter(item=>!item.acknowledged).length} detail="Current operational alerts" icon="alerts" tone="danger"/>
    <StatCard label="Last analytics run" value={s.last_analytics_run?.status??"Never"} detail={s.last_analytics_run?.completed_at?new Date(s.last_analytics_run.completed_at).toLocaleString():"No completed run"} icon="clock"/>
  </section><section className="analytics-grid">
    <AnalyticsDonut title="Health distribution" center={String(Object.values(s.health_status_counts).reduce((a,b)=>a+b,0))} items={statusItems(s.health_status_counts)}/>
    <AnalyticsDonut title="Capacity distribution" center={String(c.normal_count+c.warning_count+c.critical_count)} items={[{label:"Normal",value:c.normal_count},{label:"Warning",value:c.warning_count},{label:"Critical",value:c.critical_count}]}/>
    <AnalyticsBarChart title="Analytics coverage" unit="%" items={[{label:"Metric coverage",value:Number(s.metric_coverage??0)},{label:"Availability",value:Number(s.average_availability??0)},{label:"SLA compliance",value:Number(compliance??0)},{label:"Forecast confidence",value:Number(confidence??0)}]}/>
    <RecentRuns items={data.runs}/>
  </section></>;
}

function Health({data}:{data:Loaded}){
  const filtered=data.health;const component=(key:keyof typeof filtered[number])=>filtered.slice(0,20).map(item=>({label:item.entity_id.slice(0,8),value:Number(item[key]??0)}));
  return <section className="analytics-grid"><AnalyticsDonut title="Health status" center={String(filtered.length)} items={statusItems(data.summary.health_status_counts)}/><AnalyticsHeatmap title="Latest entity health" items={filtered.map(item=>({label:item.entity_id.slice(0,8),value:item.score}))}/><AnalyticsBarChart title="Component breakdown" unit="%" items={[["Availability","availability_component"],["Performance","performance_component"],["Reliability","reliability_component"],["Capacity","capacity_component"],["Data quality","data_quality_component"]].map(([label,key])=>({label,value:component(key as keyof typeof filtered[number]).reduce((sum,item)=>sum+item.value,0)/Math.max(1,filtered.length)}))}/><Ranked title="Top degraded devices" items={[...filtered].sort((a,b)=>a.score-b.score).slice(0,8).map(item=>({label:item.entity_id,value:item.score,status:item.status}))}/><Ranked title="Top healthy devices" items={[...filtered].sort((a,b)=>b.score-a.score).slice(0,8).map(item=>({label:item.entity_id,value:item.score,status:item.status}))}/></section>;
}

function Capacity({data}:{data:Loaded}){
  const grouped=data.capacity.reduce<Record<string,AnalyticsCapacityAssessment[]>>((result,item)=>{(result[item.metric_key]??=[]).push(item);return result},{});
  const groups=Object.entries(grouped);
  return <><section className="analytics-grid">{groups.slice(0,6).map(([key,items])=><AnalyticsLineChart key={key} title={key} area unit="" points={items.sort((a,b)=>a.period_end.localeCompare(b.period_end)).map(item=>({label:dateLabel(item.period_end),value:item.average_value,quality:item.data_quality}))}/>)}</section>{!groups.length&&<Feedback emptyTitle="No capacity assessments" empty="Enable reviewed capacity policies and run analytics processing."/>}</>;
}

function Availability({data}:{data:Loaded}){
  const points=[...data.availability].sort((a,b)=>a.period_end.localeCompare(b.period_end)).map(item=>({label:dateLabel(item.period_end),value:item.availability_percent,quality:item.availability_percent==null?"unknown":"good"}));
  const longest=Math.max(0,...data.availability.map(item=>item.longest_outage_seconds));
  return <><section className="stats-grid"><StatCard label="Average availability" value={percent(data.summary.average_availability)} detail="Unknown time excluded" icon="check"/><StatCard label="Longest outage" value={duration(longest)} detail="Across returned entities" icon="clock" tone="danger"/><StatCard label="Measured outages" value={data.availability.reduce((sum,item)=>sum+item.outage_count,0)} detail="Confirmed transitions only" icon="warning"/></section><section className="analytics-grid"><AnalyticsLineChart title="Availability history" area unit="%" points={points}/><AnalyticsBarChart title="Availability by entity" unit="%" items={data.availability.slice(0,12).map(item=>({label:item.entity_id.slice(0,8),value:item.availability_percent??0}))}/></section></>;
}

function SLA({data}:{data:Loaded}){
  const summary=data.slaSummary;const points=[...data.sla].sort((a,b)=>a.period_end.localeCompare(b.period_end)).map(item=>({label:dateLabel(item.period_end),value:item.measured_availability_percent,quality:item.data_quality}));
  return <><section className="stats-grid"><StatCard label="Targets met" value={summary.targets_met} detail={`${summary.targets_breached} breached`} icon="check" tone="success"/><StatCard label="Average availability" value={percent(summary.average_availability)} detail={`${summary.definitions_measured} definitions measured`} icon="audit"/><StatCard label="Measurements" value={summary.measurement_count} detail="Unique SLA periods" icon="clock"/></section><section className="analytics-grid"><AnalyticsLineChart title="SLA availability trend" area unit="%" points={points}/><AnalyticsDonut title="SLA outcomes" center={String(summary.measurement_count)} items={[{label:"Met",value:summary.targets_met},{label:"Breached",value:summary.targets_breached},{label:"Unknown",value:Math.max(0,summary.measurement_count-summary.targets_met-summary.targets_breached)}]}/></section></>;
}

function Reliability({data}:{data:Loaded}){
  const summary=data.reliabilitySummary;const points=[...data.reliability].sort((a,b)=>a.period_end.localeCompare(b.period_end)).map(item=>({label:dateLabel(item.period_end),value:item.mtbf_seconds==null?null:item.mtbf_seconds/3600,quality:item.data_quality}));
  return <><section className="stats-grid"><StatCard label="MTTR" value={duration(summary.mttr)} detail="Mean recovery time" icon="clock"/><StatCard label="MTBF" value={duration(summary.mtbf)} detail="Mean time between failures" icon="network"/><StatCard label="Failures" value={summary.failure_count} detail={`${duration(summary.total_downtime)} downtime`} icon="warning" tone="danger"/></section><section className="analytics-grid"><AnalyticsLineChart title="MTBF history" unit="hours" points={points}/><AnalyticsBarChart title="Failures by entity" items={data.reliability.slice(0,12).map(item=>({label:item.entity_id.slice(0,8),value:item.failure_count}))}/></section></>;
}

function Forecasts({data}:{data:Loaded}){
  return <section className="analytics-grid">{data.forecasts.map(item=><ForecastCard key={item.id} forecast={item}/>)}{!data.forecasts.length&&<Feedback emptyTitle="No forecasts generated" empty="An administrator must run a deterministic forecast against eligible aggregate history."/>}</section>;
}
function ForecastCard({forecast}:{forecast:AnalyticsForecast}){return <AnalyticsLineChart title={`${forecast.metric_key} · ${forecast.forecast_method.replaceAll("_"," ")}`} confidence area points={forecast.prediction_points.map(point=>({label:dateLabel(point.timestamp),value:point.value,lower:point.lower_bound,upper:point.upper_bound,quality:`${forecast.confidence_score.toFixed(0)}% confidence`}))}/>}

function TrendExplorer({data,range,bucket}:{data:Loaded;range:string;bucket:string}){
  const enabled=data.definitions.filter(item=>item.enabled);const [metric,setMetric]=useState(enabled[0]?.metric_key??"");const [entityType,setEntityType]=useState(enabled[0]?.entity_type??"device");const [entityId,setEntityId]=useState("");const [aggregation,setAggregation]=useState("average");const [trend,setTrend]=useState<AnalyticsTrend|null>(null);const [loading,setLoading]=useState(false);const [error,setError]=useState("");
  const run=async()=>{if(!metric||!entityId){setError("Select a metric and enter an entity ID.");return}setLoading(true);setError("");try{const dates=rangeStart(range);setTrend(await analyticsApi.trends({metric_key:metric,entity_type:entityType,entity_id:entityId,start:dates.start,end:dates.end,bucket_size:bucket,aggregation,compare_previous_period:true}))}catch(caught){setError(caught instanceof Error?caught.message:"Trend request failed.")}finally{setLoading(false)}};
  return <><section className="analytics-explorer"><label>Metric<select value={metric} onChange={event=>{setMetric(event.target.value);const chosen=enabled.find(item=>item.metric_key===event.target.value);if(chosen)setEntityType(chosen.entity_type)}}>{enabled.map(item=><option key={item.id} value={item.metric_key}>{item.name} · {item.metric_key}</option>)}</select></label><label>Entity type<input value={entityType} readOnly/></label><label>Entity ID<input value={entityId} onChange={event=>setEntityId(event.target.value)} placeholder="UUID from inventory or analytics"/></label><label>Aggregation<select value={aggregation} onChange={event=>setAggregation(event.target.value)}>{["average","minimum","maximum","latest","sum","percentile"].map(item=><option key={item}>{item}</option>)}</select></label><button className="primary-action" disabled={loading} onClick={()=>void run()}>{loading?"Loading…":"Explore trend"}</button></section>{error&&<Feedback error={error} onRetry={()=>void run()}/>} {trend&&<section className="analytics-grid"><AnalyticsLineChart title={metric} area unit={trend.unit??""} points={trend.series.map(point=>({label:dateLabel(point.timestamp),value:point.value,quality:point.quality}))}/><AnalyticsBarChart title="Trend summary" unit={trend.unit??""} items={Object.entries(trend.summary).filter(([key])=>key!=="sample_count").map(([label,value])=>({label,value:Number(value??0)}))}/></section>}</>;
}

function AnalyticsReports({data}:{data:Loaded}){
  const [notice,setNotice]=useState("");const exportJson=()=>{downloadAnalyticsJson(`hiop-analytics-${new Date().toISOString().slice(0,10)}.json`,{generated_at:new Date().toISOString(),summary:data.summary,capacity:data.capacitySummary,sla:data.slaSummary,reliability:data.reliabilitySummary,forecasts:data.forecasts});setNotice("Analytics JSON exported.")};
  const exportCsv=async()=>{const report=await analyticsApi.forecastReport();const headers=["metric_key","entity_type","entity_id","forecast_method","projected_value","confidence_score","growth_rate","trend_direction","risk_level","forecast_end"];const safe=(value:unknown)=>{const text=String(value??"");const guarded=/^[=+\-@]/.test(text)?`'${text}`:text;return `"${guarded.replaceAll('"','""')}"`};const csv=[headers.join(","),...report.items.map(item=>headers.map(key=>safe(item[key as keyof AnalyticsForecast])).join(","))].join("\r\n");const blob=new Blob([csv],{type:"text/csv;charset=utf-8"});const url=URL.createObjectURL(blob);const a=document.createElement("a");a.href=url;a.download="hiop-analytics-forecasts.csv";a.click();URL.revokeObjectURL(url);setNotice("Formula-safe forecast CSV exported.")};
  return <><section className="analytics-report-actions"><button className="primary-action" onClick={exportJson}>Export JSON</button><button className="secondary-action" onClick={()=>void exportCsv()}>Export CSV</button><button className="secondary-action" onClick={()=>window.print()}>Print / Save PDF</button></section>{notice&&<div className="inline-notice" role="status">{notice}</div>}<section className="analytics-grid"><AnalyticsDonut title="Forecast direction" center={String(data.forecasts.length)} items={[{label:"Increasing",value:data.forecastSummary.increasing_metrics},{label:"Stable",value:data.forecastSummary.stable_metrics},{label:"Decreasing",value:data.forecastSummary.declining_metrics}]}/><AnalyticsBarChart title="Operational KPI report" items={[{label:"Capacity warnings",value:data.capacitySummary.warning_count},{label:"Capacity critical",value:data.capacitySummary.critical_count},{label:"SLA breaches",value:data.slaSummary.targets_breached},{label:"Failures",value:data.reliabilitySummary.failure_count}]}/></section></>;
}

function RecentRuns({items}:{items:Loaded["runs"]}){return <article className="analytics-chart-card"><header><div><h3>Recent analytics runs</h3><span>{items.length} returned</span></div></header>{items.length?<div className="analytics-run-list">{items.slice(0,8).map(item=><div key={item.id}><span className={`status-badge ${item.status}`}>{item.status}</span><strong>{item.run_type.replaceAll("_"," ")}</strong><time>{new Date(item.started_at).toLocaleString()}</time><b>{item.duration_ms==null?"—":`${item.duration_ms} ms`}</b></div>)}</div>:<div className="analytics-chart-empty">No analytics runs yet.</div>}</article>}
function Ranked({title,items}:{title:string;items:Array<{label:string;value:number;status:string}>}){return <article className="analytics-chart-card"><header><div><h3>{title}</h3><span>{items.length} entities</span></div></header><div className="analytics-ranked">{items.map(item=><div key={item.label}><strong>{item.label}</strong><span>{item.status}</span><b>{item.value.toFixed(0)}</b></div>)}</div></article>}
function AnalyticsLoading({loading,error,retry}:{loading:boolean;error:string;retry:()=>Promise<void>}){if(error)return <Feedback error={error} onRetry={()=>void retry()}/>;if(!loading)return <Feedback empty="No analytics records are available."/>;return <section className="analytics-skeletons" aria-label="Loading analytics"><i/><i/><i/><i/><i/><i/></section>}
