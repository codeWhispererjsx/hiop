import { useState } from "react";
import { Link } from "react-router-dom";
import { Feedback } from "../components/Feedback";
import { StatusBadge } from "../components/StatusBadge";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import type { V3CVlan, V3CVlanDetails } from "../lib/types";
import { PageTitle } from "./DashboardPage";
import "../styles/segmentation.css";

export default function SegmentationPage(){
  const [search,setSearch]=useState("");
  const [selected,setSelected]=useState<V3CVlan>();
  const [details,setDetails]=useState<V3CVlanDetails>();
  const vlans=useRequest(()=>endpoints.v3cVlans({search:search||undefined}),[search]);
  const stats=useRequest(endpoints.v3cStats,[]);
  const selectVlan=(vlan:V3CVlan)=>{setSelected(vlan);setDetails(undefined);void endpoints.v3cVlan(vlan.id).then(setDetails).catch(()=>setDetails(undefined))};
  return <DashboardLayout><PageTitle eyebrow="Network intelligence · Version 3C" title="Network segmentation" copy="Cached, read-only VLAN, subnet, switch, port, and device evidence. HIOP cannot modify network configuration." action={<Link className="secondary-action" to="/topology">Open topology</Link>}/>
    <section className="operational-guide" aria-label="How network segmentation works"><div><span>Purpose</span><strong>Understand how the network is separated</strong><p>VLANs divide devices and services into controlled broadcast and security zones, such as POS, guest Wi-Fi, CCTV, and staff systems.</p></div><div><span>How to use it</span><strong>Select a VLAN to inspect membership</strong><p>Review its subnet, gateway, switches, access ports, trunks, devices, source evidence, and confidence.</p></div><div><span>Safety</span><strong>Read-only evidence</strong><p>Unknown values remain unknown. HIOP does not create VLANs or change switch configuration from this page.</p></div></section>
    <section className="segment-stats" aria-label="VLAN intelligence summary">
      <Metric label="VLANs" value={stats.data?.vlans_discovered}/><Metric label="Subnets" value={stats.data?.subnets_identified}/><Metric label="Devices" value={stats.data?.devices_with_vlan_information}/><Metric label="Ports" value={stats.data?.ports_with_vlan_information}/><Metric label="Trunks" value={stats.data?.trunk_ports}/><Metric label="Unknown endpoints" value={stats.data?.unknown_vlan_relationships}/><Metric label="Security zones" value={stats.data?.security_zones || 0}/><Metric label="Critical VLANs" value={stats.data?.critical_vlans || 0}/><Metric label="High traffic VLANs" value={stats.data?.high_traffic_vlans || 0}/><Metric label="Avg devices/VLAN" value={stats.data?.average_devices_per_vlan || 0}/><Metric label="VLAN coverage" value={`${stats.data?.vlan_coverage_percentage || 0}%`}/><Metric label="Last scan" value={`${stats.data?.last_scan_minutes_ago || 0}m ago`}/><Metric label="Trunk % of ports" value={`${stats.data?.trunk_port_percentage || 0}%`}/><Metric label="Access % of ports" value={`${stats.data?.access_port_percentage || 0}%`}/>
    </section>
    <section className="segment-layout"><div className="segment-list"><div className="segment-toolbar"><label>Find VLAN, subnet, device, switch, or port<input aria-label="Search network segmentation" value={search} onChange={event=>setSearch(event.target.value)} placeholder="VLAN 120, POS, 10.50.21.0/24…"/></label></div>
      {vlans.loading||vlans.error?<Feedback loading={vlans.loading} error={vlans.error} onRetry={vlans.reload}/>:!vlans.data?.items.length?<Feedback emptyTitle="No VLAN information available" empty={vlans.data?.message||"Supported switches have not supplied VLAN evidence yet. Unknown information remains unknown."}/>:<table><thead><tr><th>VLAN</th><th>Name</th><th>Subnet</th><th>Status</th><th>Devices</th><th>Ports</th></tr></thead><tbody>{vlans.data.items.map(vlan=><tr key={vlan.id} className={selected?.id===vlan.id?"selected":""} onClick={()=>selectVlan(vlan)}><td><strong>{vlan.vlan_id}</strong></td><td>{vlan.name}</td><td>{vlan.subnet||"Unknown"}</td><td><StatusBadge status={vlan.status}/></td><td>{vlan.device_count}</td><td>{vlan.port_count}</td></tr>)}</tbody></table>}
    </div><aside className="segment-detail">{!selected?<div className="segment-empty"><strong>Select a VLAN</strong><span>Review its subnet, evidence, devices, access ports, and trunks.</span></div>:!details?<Feedback loading/>:<><header><span>VLAN {details.vlan_id}</span><h2>{details.name}</h2><p>{details.subnet||"Subnet unknown"} · {details.source.replaceAll("_"," ")} · {details.confidence}% confidence</p></header><dl><Detail label="Status" value={details.status}/><Detail label="Gateway" value={details.gateway||"Unknown"}/><Detail label="Last verified" value={new Date(details.last_observed_at).toLocaleString()}/></dl><h3>Devices and ports</h3>{details.memberships.filter(x=>x.state==="current").length===0?<p>No current port memberships.</p>:details.memberships.filter(x=>x.state==="current").map(row=><article key={row.id}><div><strong>{row.device?.hostname||"Multiple/Unknown endpoint"}</strong><span>{row.switch.hostname} → {row.interface.name||"Unknown port"}</span><small>{row.port_mode} · {row.membership_type} · {row.confidence}% confidence</small></div>{row.device&&<Link to={`/devices/${row.device.id}`}>Open device</Link>}</article>)}</>}</aside></section>
  </DashboardLayout>
}
function Metric({label,value}:{label:string;value?:number|string}){return <article><strong>{value??0}</strong><span>{label}</span></article>}
function Detail({label,value}:{label:string;value:string}){return <div><dt>{label}</dt><dd>{value}</dd></div>}
