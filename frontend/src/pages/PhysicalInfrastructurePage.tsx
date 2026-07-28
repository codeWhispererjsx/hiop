import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { Feedback } from "../components/Feedback";
import { StatCard } from "../components/StatCard";
import { endpoints } from "../lib/api";
import type { Building, Floor, Zone, Property } from "../lib/types";
import "../styles/hospitality.css";

export default function PhysicalInfrastructurePage() {
  const path=useLocation().pathname; const tab=path.includes("/floors")?"floors":path.includes("/zones")?"zones":"buildings";
  const [buildings,setBuildings]=useState<Building[]>([]),[floors,setFloors]=useState<Floor[]>([]),[zones,setZones]=useState<Zone[]>([]),[properties,setProperties]=useState<Property[]>([]),[error,setError]=useState(""),[open,setOpen]=useState<Record<string,boolean>>({});
  const load=async()=>{try{const [b,f,z,p]=await Promise.all([endpoints.buildings(),endpoints.floors(),endpoints.zones(),endpoints.properties()]);setBuildings(b.items);setFloors(f.items);setZones(z.items);setProperties(p.items);setError("")}catch(e){setError(e instanceof Error?e.message:"Unable to load physical infrastructure")}};
  useEffect(()=>{const timer=window.setTimeout(()=>{void load()},0);return()=>window.clearTimeout(timer)},[]); const count=tab==="buildings"?buildings.length:tab==="floors"?floors.length:zones.length;
  return <DashboardLayout><header className="page-title"><div><span className="eyebrow">HIOP v3 physical hierarchy</span><h1>{tab[0].toUpperCase()+tab.slice(1)}</h1><p>Property-aware buildings, floors and operational zones.</p></div></header><nav className="hospitality-tabs"><NavLink to="/buildings">Buildings</NavLink><NavLink to="/floors">Floors</NavLink><NavLink to="/zones">Zones</NavLink></nav>{error&&<Feedback error={error} onRetry={load}/>}<section className="stats-grid hospitality-stats"><StatCard label="Buildings" value={buildings.length} detail="Property structures" icon="hierarchy"/><StatCard label="Floors" value={floors.length} detail="Vertical levels" icon="hierarchy"/><StatCard label="Zones" value={zones.length} detail="Operational areas" icon="hierarchy"/><StatCard label="Current view" value={count} detail={tab} icon="check"/></section><section className="hospitality-panel"><div className="panel-heading"><div><h2>Property explorer</h2><span>Expand a property to inspect its physical hierarchy.</span></div></div><div className="hospitality-grid">{properties.map(p=><article className="hospitality-card" key={p.id}><button className="ghost-action" onClick={()=>setOpen(o=>({...o,[p.id]:!o[p.id]}))} aria-expanded={!!open[p.id]}>{open[p.id]?"▾":"▸"} {p.name}</button>{open[p.id]&&<div className="hierarchy-tree">{buildings.filter(b=>b.property_id===p.id).map(b=><div key={b.id}><strong>{b.name}</strong>{floors.filter(f=>f.building_id===b.id).map(f=><div className="tree-indent" key={f.id}>{f.display_name||f.name}{zones.filter(z=>z.floor_id===f.id).map(z=><div className="tree-indent" key={z.id}>{z.name} <small>{z.type}</small></div>)}</div>)}</div>)}</div>}</article>)}{!properties.length&&<Feedback empty="No properties configured yet."/>}</div></section></DashboardLayout>;
}

