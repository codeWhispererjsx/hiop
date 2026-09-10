import {useEffect,useState} from "react";
import {endpoints} from "../lib/api";
import type {PlatformBillingOverview} from "../lib/types";
import {Feedback} from "./Feedback";
import {StatCard} from "./StatCard";
import {StatusBadge} from "./StatusBadge";

const when=(value?:string|null)=>value?new Date(value).toLocaleString():"Not scheduled";
const defaultReason="Testing phase: keep this organization active outside billing.";

export function PlatformBilling({data}:{data?:PlatformBillingOverview|null}){
  const [rows,setRows]=useState(data?.items??[]);
  const [busy,setBusy]=useState<string>();
  const [error,setError]=useState("");
  useEffect(()=>{setRows(data?.items??[])},[data]);
  if(!data)return <Feedback empty="No billing information is available."/>;
  const exempted=rows.filter(row=>row.billing_exempt).length;
  const setExemption=async(organizationId:string,exempt:boolean)=>{
    setBusy(organizationId);setError("");
    try{
      const next=await endpoints.setBillingExemption(organizationId,exempt,exempt?defaultReason:"");
      setRows(current=>current.map(row=>row.organization.id===organizationId?{...row,...next}:row));
    }catch(reason){setError(reason instanceof Error?reason.message:"Billing exemption could not be updated.")}
    finally{setBusy(undefined)}
  };
  return <><section className="platform-stats"><StatCard label="Subscriptions" value={rows.length} detail={`${data.active} active`} icon="devices"/><StatCard label="Testing exemptions" value={exempted} detail="Manually kept active" icon="check" tone="success"/><StatCard label="Past due" value={data.past_due} detail="Payment attention required" icon="warning" tone="danger"/><StatCard label="Plans" value={data.plans} detail="Configured offers" icon="audit"/></section>{error&&<Feedback error={error}/>}<section className="panel platform-table-panel"><div className="platform-section-heading"><div><h2>Organization subscriptions</h2><p>Control billing without blocking testing organizations. Exempt organizations stay active and receive no payment prompts.</p></div></div>{rows.length?<div className="platform-table-wrap"><table><thead><tr><th>Organization</th><th>Plan</th><th>Status</th><th>Renewal / trial end</th><th>Usage</th><th>Payment</th><th>Platform control</th></tr></thead><tbody>{rows.map(row=><tr key={row.id}><td><strong>{row.organization.name}</strong>{row.billing_exempt&&<small>{row.billing_exemption_reason||"Billing exempt"}</small>}</td><td>{row.plan.name}<small>{row.billing_interval}</small></td><td><StatusBadge status={row.billing_exempt?"active":row.status}/></td><td>{row.billing_exempt?"Manual exemption":when(row.renewal_date||row.trial_end||row.current_period_end)}</td><td><small>{row.usage.assets??0} / {row.limits.assets??"Unlimited"} assets</small><small>{row.usage.properties??0} / {row.limits.properties??"Unlimited"} properties</small></td><td><StatusBadge status={row.billing_exempt?"exempt":row.payment_status}/></td><td><button className={row.billing_exempt?"platform-button secondary":"platform-button primary"} disabled={busy===row.organization.id} onClick={()=>void setExemption(row.organization.id,!row.billing_exempt)}>{busy===row.organization.id?"Updating...":row.billing_exempt?"Remove exemption":"Exempt from billing"}</button></td></tr>)}</tbody></table></div>:<Feedback empty="No organizations have billing yet."/>}</section></>;
}
