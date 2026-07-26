/* eslint-disable react-hooks/set-state-in-effect */
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import {
  Background, Controls, Handle, MarkerType, MiniMap, Position, ReactFlow,
  type Edge, type Node, type NodeProps, type OnSelectionChangeParams,
  useEdgesState, useNodesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import DashboardLayout from "../layouts/DashboardLayout";
import { Feedback } from "../components/Feedback";
import Modal from "../components/Modal";
import { StatusBadge } from "../components/StatusBadge";
import { endpoints } from "../lib/api";
import type {
  NodePosition, SnapshotComparison, Topology, TopologyChange, TopologyConflict,
  TopologyFilterState, TopologyGraph, TopologyGraphEvent, TopologyImpact,
  TopologyLayoutMode, TopologyLink, TopologyNode, TopologyPathResult,
  TopologyReviewItem, TopologySnapshot, TopologyStats, User,
  TopologyAlertEvent, TopologyAlertRule, TopologyHealth, TopologyOperationalRun,
  TopologyRetentionPreview, TopologySchedule, TopologySchedulerStatus,
} from "../lib/types";
import "../styles/topology.css";

type DeviceNodeData = { node:TopologyNode; selectedPath:boolean; impacted:boolean; conflicted:boolean };
type CanvasNode = Node<DeviceNodeData,"device">;
const statusText = (value:string) => value.replaceAll("_"," ");
const fmt = (value?:string|null) => value ? new Date(value).toLocaleString() : "Never";
const message = (error:unknown) => error instanceof Error ? error.message : "The operation could not be completed.";
const pageFor = (pathname:string) => pathname.split("/").filter(Boolean).slice(2);
const emptyFilters:TopologyFilterState = {search:"",status:"",deviceType:"",layer:"",role:"",vendor:"",linkType:"",confidence:0,includeHidden:false,orphanOnly:false,conflictOnly:false};

function DeviceNode({data,selected}:NodeProps<CanvasNode>){
  const node=data.node, provisional=!node.is_manual||node.source_type!=="manual";
  return <article tabIndex={0} aria-label={`${node.label}, ${statusText(node.status)}, ${node.layer} layer`}
    className={`topology-node topology-node-${node.status} ${selected?"selected":""} ${data.selectedPath?"path-node":""} ${data.impacted?"impact-node":""} ${data.conflicted?"conflict-node":""}`}>
    <Handle type="target" position={Position.Top}/>
    <div className="topology-node-icon" aria-hidden="true">{nodeIcon(node)}</div>
    <div><strong>{node.label}</strong><span>{statusText(node.layer||node.role||"unknown")} · {statusText(node.status)}</span>{node.management_ip&&<small>{node.management_ip}</small>}</div>
    <footer>{provisional&&<span title="Provisional confidence">◌ {node.confidence_score}%</span>}{data.conflicted&&<span title="Conflict">⚠ Conflict</span>}</footer>
    <Handle type="source" position={Position.Bottom}/>
  </article>
}

function nodeIcon(node:TopologyNode){
  const kind=(node.node_type+" "+node.role+" "+node.layer).toLowerCase();
  if(kind.includes("internet")||kind.includes("external"))return "◎";
  if(kind.includes("firewall"))return "⬡";
  if(kind.includes("router"))return "◆";
  if(kind.includes("switch"))return "▰";
  if(kind.includes("wireless")||kind.includes("access_point"))return "⌁";
  if(kind.includes("printer"))return "▤";
  if(kind.includes("ups"))return "▣";
  if(kind.includes("server")||kind.includes("service"))return "▥";
  if(kind.includes("endpoint"))return "▱";
  return "◇";
}

const nodeTypes={device:DeviceNode};

export default function TopologyPage(){
  const location=useLocation(), navigate=useNavigate(), parts=pageFor(location.pathname), topologyId=parts[0];
  const [user,setUser]=useState<User>(),[live,setLive]=useState(false),[eventTick,setEventTick]=useState(0);
  useEffect(()=>{void endpoints.me().then(setUser).catch(()=>undefined)},[]);
  const onEvent=useCallback((event:TopologyGraphEvent)=>{
    if((event.type??event.event)?.startsWith("topology_")&&(!topologyId||!event.topology_id||event.topology_id===topologyId))setEventTick(value=>value+1);
  },[topologyId]);
  let content:ReactNode;
  if(!topologyId)content=<Landing user={user}/>;
  else if(parts[1]==="review")content=<ReviewWorkspace topologyId={topologyId} user={user} mode="review"/>;
  else if(parts[1]==="conflicts")content=<ReviewWorkspace topologyId={topologyId} user={user} mode="conflicts"/>;
  else if(parts[1]==="snapshots"&&parts[2])content=<SnapshotViewer topologyId={topologyId} snapshotId={parts[2]}/>;
  else if(parts[1]==="snapshots")content=<Snapshots topologyId={topologyId} user={user}/>;
  else if(parts[1]==="changes")content=<Changes topologyId={topologyId}/>;
  else if(parts[1]==="settings")content=<TopologySettings topologyId={topologyId} user={user}/>;
  else content=<TopologyMap topologyId={topologyId} user={user} live={live} eventTick={eventTick}/>;
  return <DashboardLayout onLiveEvent={onEvent} onLiveStateChange={setLive}>
    <div className="topology-page">
      {topologyId&&<TopologyNav topologyId={topologyId} active={parts[1]??"map"} onBack={()=>navigate("/topology")}/>}
      {content}
    </div>
  </DashboardLayout>
}

function TopologyNav({topologyId,active,onBack}:{topologyId:string;active:string;onBack:()=>void}){
  return <nav className="topology-subnav" aria-label="Topology sections">
    <button onClick={onBack}>← All topologies</button>
    {[["map","Map"],["review","Review"],["conflicts","Conflicts"],["snapshots","Snapshots"],["changes","Changes"],["settings","Settings"]].map(([key,label])=>
      <Link key={key} className={active===key?"active":""} to={`/topology/${topologyId}/${key}`}>{label}</Link>)}
  </nav>
}

function Landing({user}:{user?:User}){
  const [topologies,setTopologies]=useState<Topology[]>([]),[stats,setStats]=useState<Record<string,TopologyStats>>({}),[inference,setInference]=useState<Record<string,{conflicts:number;reviews:number;orphans:number}>>({}),[loading,setLoading]=useState(true),[error,setError]=useState(""),[create,setCreate]=useState(false);
  const load=useCallback(async()=>{
    setLoading(true);setError("");
    try{
      const page=await endpoints.topologies({page_size:100});
      setTopologies(page.items);
      const rows=await Promise.all(page.items.map(async t=>{
        const [s,i]=await Promise.all([endpoints.topologyStats(t.id),endpoints.topologyInference(t.id)]);
        return [t.id,s,{conflicts:i.open_conflicts,reviews:i.pending_review_items,orphans:i.orphans.orphan_node_ids.length}] as const;
      }));
      setStats(Object.fromEntries(rows.map(([id,s])=>[id,s])));
      setInference(Object.fromEntries(rows.map(([id,,i])=>[id,i])));
    }catch(e){setError(message(e))}finally{setLoading(false)}
  },[]);
  useEffect(()=>{void load()},[load]);
  if(loading||error)return <Feedback loading={loading} error={error} onRetry={load}/>;
  const totals=topologies.reduce((a,t)=>{const s=stats[t.id],i=inference[t.id];return {nodes:a.nodes+(s?.nodes??0),links:a.links+(s?.links??0),confirmed:a.confirmed+(s?.confirmed_links??0),orphans:a.orphans+(i?.orphans??0),conflicts:a.conflicts+(i?.conflicts??0),reviews:a.reviews+(i?.reviews??0)}},{nodes:0,links:0,confirmed:0,orphans:0,conflicts:0,reviews:0});
  return <>
    <header className="topology-hero"><div><span>Network intelligence</span><h1>Network topology</h1><p>Explore explainable infrastructure relationships without changing inventory or device configuration.</p></div>
      {user?.role==="admin"&&<div><button onClick={()=>setCreate(true)}>Create topology</button><button className="primary-action" disabled={!topologies.length} onClick={()=>void endpoints.bootstrapTopology((topologies.find(t=>t.is_default)??topologies[0]).id,{dry_run:true,include_snmp_managed_devices:true,include_discovered_devices:false,include_only_active_inventory:true,create_provisional_nodes:false})}>Preview bootstrap</button></div>}
    </header>
    <section className="topology-kpis" aria-label="Topology summary">
      <Kpi label="Topologies" value={topologies.length}/><Kpi label="Nodes" value={totals.nodes}/><Kpi label="Links" value={totals.links}/><Kpi label="Confirmed" value={totals.confirmed}/><Kpi label="Orphans" value={totals.orphans}/><Kpi label="Conflicts" value={totals.conflicts}/><Kpi label="Pending review" value={totals.reviews}/>
    </section>
    <Panel title="Managed topologies" copy="Open a bounded live graph or review its current operational state.">
      {!topologies.length?<Feedback empty="No topology exists. An administrator can create one, then run a reviewed bootstrap."/>:
      <Table heads={["Name","Type / scope","State","Nodes","Links","Confirmed","Conflicts","Updated","Actions"]}>{topologies.map(t=><tr key={t.id}>
        <td><strong>{t.name}</strong>{t.is_default&&<small>Default topology</small>}</td><td>{statusText(t.topology_type)}<small>{statusText(t.scope_type)}</small></td>
        <td><StatusBadge status={t.enabled?"enabled":"disabled"}/></td><td>{stats[t.id]?.nodes??0}</td><td>{stats[t.id]?.links??0}</td><td>{stats[t.id]?.confirmed_links??0}</td><td>{inference[t.id]?.conflicts??0}</td><td>{fmt(t.updated_at)}</td>
        <td className="topology-actions"><Link to={`/topology/${t.id}/map`}>Open map</Link><Link to={`/topology/${t.id}/conflicts`}>Review</Link>{user?.role==="admin"&&<button onClick={()=>void endpoints.createTopologySnapshot(t.id,{name:`Manual snapshot ${new Date().toLocaleDateString()}`,snapshot_type:"manual"}).then(load)}>Snapshot</button>}</td>
      </tr>)}</Table>}
    </Panel>
    {create&&<TopologyForm onClose={()=>setCreate(false)} onSaved={()=>{setCreate(false);void load()}}/>}
  </>;
}

function TopologyForm({onClose,onSaved}:{onClose:()=>void;onSaved:()=>void}){
  const [name,setName]=useState(""),[error,setError]=useState("");
  const submit=async(e:FormEvent)=>{e.preventDefault();try{await endpoints.createTopology({name,description:null,topology_type:"physical",scope_type:"global",enabled:true,is_default:false,layout_mode:"manual"});onSaved()}catch(err){setError(message(err))}};
  return <Modal title="Create topology" onClose={onClose}><form className="topology-form" onSubmit={submit}><label>Name<input autoFocus required minLength={2} maxLength={120} value={name} onChange={e=>setName(e.target.value)}/></label><p>Creation does not collect neighbors or add inventory automatically.</p>{error&&<p role="alert">{error}</p>}<footer><button type="button" onClick={onClose}>Cancel</button><button className="primary-action">Create topology</button></footer></form></Modal>
}

function TopologyMap({topologyId,user,live,eventTick}:{topologyId:string;user?:User;live:boolean;eventTick:number}){
  const [graph,setGraph]=useState<TopologyGraph>(),[positions,setPositions]=useState<NodePosition[]>([]),[stats,setStats]=useState<TopologyStats>(),[inference,setInference]=useState<{open_conflicts:number;pending_review_items:number;orphans:{orphan_node_ids:string[]}}>(),[conflictEntities,setConflictEntities]=useState<Set<string>>(new Set()),[loading,setLoading]=useState(true),[error,setError]=useState("");
  const [filters,setFilters]=useUrlFilters(),[layout,setLayout]=useState<TopologyLayoutMode>("hierarchical"),[nodes,setNodes,onNodesChange]=useNodesState<CanvasNode>([]),[edges,setEdges,onEdgesChange]=useEdgesState<Edge>([]);
  const [selectedNode,setSelectedNode]=useState<TopologyNode>(),[selectedLink,setSelectedLink]=useState<TopologyLink>(),[path,setPath]=useState<TopologyPathResult>(),[impact,setImpact]=useState<TopologyImpact>(),[mode,setMode]=useState<"browse"|"path"|"impact">("browse"),[pathType,setPathType]=useState("any"),[pathSource,setPathSource]=useState<string>(),[notice,setNotice]=useState(""),[showFilters,setShowFilters]=useState(false),[linkForm,setLinkForm]=useState(false),[full,setFull]=useState(false);
  const refreshTimer=useRef<number|undefined>(undefined);
  const load=useCallback(async()=>{
    setLoading(true);setError("");
    try{
      const [g,p,s,i,c]=await Promise.all([
        endpoints.topologyGraph(topologyId,{include_hidden:filters.includeHidden,confidence_minimum:filters.confidence}),
        endpoints.topologyLayout(topologyId),endpoints.topologyStats(topologyId),endpoints.topologyInference(topologyId),endpoints.topologyConflicts(topologyId,{page_size:100,status:"open"}),
      ]);
      setGraph(g);setPositions(p.items);setStats(s);setInference(i);setConflictEntities(new Set(c.items.flatMap(item=>[item.entity_id,...item.related_entity_ids].filter(Boolean) as string[])));
    }catch(e){setError(message(e))}finally{setLoading(false)}
  },[topologyId,filters.includeHidden,filters.confidence]);
  useEffect(()=>{void load()},[load]);
  useEffect(()=>{if(!eventTick)return;clearTimeout(refreshTimer.current);refreshTimer.current=window.setTimeout(()=>void load(),500);return()=>clearTimeout(refreshTimer.current)},[eventTick,load]);
  const filtered=useMemo(()=>filterGraph(graph,filters,inference?.orphans.orphan_node_ids??[],conflictEntities),[graph,filters,inference,conflictEntities]);
  useEffect(()=>{
    if(!graph)return;
    const positionMap=new Map(positions.map(p=>[p.node_id,{x:p.x_position,y:p.y_position}]));
    const laid=buildLayout(filtered.nodes,filtered.links,layout,positionMap);
    setNodes(laid.map(item=>({id:item.node.id,type:"device",position:item.position,data:{node:item.node,selectedPath:path?.paths?.some(p=>p.nodes.includes(item.node.id))??path?.nodes?.includes(item.node.id)??false,impacted:impact?.potentially_affected_nodes.some(n=>n.id===item.node.id)??false,conflicted:conflictEntities.has(item.node.id)}})));
    const pathEdges=new Set(path?.paths?.flatMap(p=>p.edges?.map(e=>e.id)??[])??path?.links??[]);
    setEdges(filtered.links.map(link=>({id:link.id,source:link.source_node_id,target:link.target_node_id,label:edgeLabel(link),className:`topology-edge topology-edge-${link.status} ${link.is_confirmed?"confirmed":"inferred"} ${pathEdges.has(link.id)?"path-edge":""}`,animated:pathEdges.has(link.id),markerEnd:{type:MarkerType.ArrowClosed},data:{link}})));
  },[graph,filtered,positions,layout,path,impact,conflictEntities,setNodes,setEdges]);
  const selection=useCallback(({nodes:selectedNodes,edges:selectedEdges}:OnSelectionChangeParams)=>{
    if(selectedNodes[0]){const node=(selectedNodes[0].data as DeviceNodeData).node;setSelectedNode(node);setSelectedLink(undefined);if(mode==="impact")void endpoints.topologyImpact(topologyId,node.id).then(setImpact);if(mode==="path"){if(!pathSource){setPathSource(node.id);setNotice("Source selected. Choose a destination.")}else if(pathSource!==node.id)void endpoints.topologyPath(topologyId,pathSource,node.id,pathType).then(result=>{setPath(result);setNotice(result.paths?.length?`${result.paths.length} path option(s) found.`:"No supported path found.");setPathSource(undefined)})}}
    else if(selectedEdges[0]){setSelectedLink((selectedEdges[0].data as {link:TopologyLink}).link);setSelectedNode(undefined)}
  },[mode,pathSource,pathType,topologyId]);
  const saveLayout=async()=>{try{const payload=nodes.map(n=>({node_id:n.id,x_position:n.position.x,y_position:n.position.y,group_id:null,locked:false,layout_version:1}));await endpoints.saveTopologyLayout(topologyId,payload);setNotice(`Saved ${payload.length} node positions.`)}catch(e){setNotice(message(e))}};
  const runInference=async()=>{if(!confirm("Run bounded topology inference now? Manual links and inventory are preserved."))return;try{const run=await endpoints.runTopologyInference(topologyId);setNotice(`Inference ${run.status}: ${run.conflicts_detected} conflict(s), ${run.review_items_created} review item(s).`);void load()}catch(e){setNotice(message(e))}};
  if(loading&&!graph||error)return <Feedback loading={loading&&!graph} error={error} onRetry={load}/>;
  if(!graph)return null;
  return <section className={`topology-map-shell ${full?"fullscreen":""}`}>
    <header className="topology-map-header"><div><span>{graph.topology.scope_type} topology</span><h1>{graph.topology.name}</h1><p>{stats?.nodes??0} nodes · {stats?.links??0} links · {inference?.open_conflicts??0} conflicts</p></div><div className="topology-live"><i className={live?"online":""}/>{live?"Live updates":"Polling fallback"}</div></header>
    <div className="topology-toolbar" role="toolbar" aria-label="Topology map controls">
      <label className="topology-search">Search<input aria-label="Search topology" value={filters.search} onChange={e=>setFilters({...filters,search:e.target.value})} placeholder="Hostname, IP, vendor…"/></label>
      <button aria-pressed={showFilters} onClick={()=>setShowFilters(v=>!v)}>Filters {activeFilterCount(filters)>0&&`(${activeFilterCount(filters)})`}</button>
      <label>Layout<select value={layout} onChange={e=>setLayout(e.target.value as TopologyLayoutMode)}><option value="hierarchical">Layered</option><option value="force">Force-directed</option><option value="grid">Grid</option><option value="radial">Radial</option><option value="manual">Saved manual</option></select></label>
      <button className={mode==="path"?"active":""} onClick={()=>{setMode(mode==="path"?"browse":"path");setPath(undefined);setPathSource(undefined)}}>Path</button>
      {mode==="path"&&<label>Path type<select value={pathType} onChange={e=>setPathType(e.target.value)}><option value="physical">Physical</option><option value="dependency">Dependency</option><option value="layer_aware">Layer-aware</option><option value="any">Any modeled</option></select></label>}
      <button className={mode==="impact"?"active":""} onClick={()=>{setMode(mode==="impact"?"browse":"impact");setImpact(undefined)}}>Impact</button>
      <button onClick={()=>void load()}>Refresh</button><button onClick={()=>setFull(v=>!v)}>{full?"Exit full screen":"Full screen"}</button>
      {user?.role==="admin"&&<><button onClick={()=>void saveLayout()}>Save layout</button><button onClick={runInference}>Run inference</button><button onClick={()=>setLinkForm(true)}>Manual link</button><button onClick={()=>void endpoints.createTopologySnapshot(topologyId,{name:`Snapshot ${new Date().toLocaleString()}`,snapshot_type:"manual"}).then(()=>setNotice("Snapshot created."))}>Snapshot</button></>}
    </div>
    {showFilters&&<FilterBar value={filters} onChange={setFilters}/>}
    {graph.metadata.bounded&&<div className="topology-banner warning" role="status">The backend visual limit was reached. Narrow the graph with filters or use a grouped scope.</div>}
    {notice&&<div className="topology-banner" role="status">{notice}<button aria-label="Dismiss status" onClick={()=>setNotice("")}>×</button></div>}
    <div className="topology-canvas-wrap">
      <ReactFlow<CanvasNode,Edge> nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onSelectionChange={selection} fitView minZoom={0.08} maxZoom={2.4} nodesDraggable={user?.role==="admin"} elevateEdgesOnSelect onlyRenderVisibleElements>
        <Background gap={26}/><MiniMap pannable zoomable nodeColor={n=>statusColor((n.data as DeviceNodeData).node.status)}/><Controls showInteractive={false}/>
      </ReactFlow>
      <aside className="topology-legend" aria-label="Topology legend"><strong>Legend</strong><span><i className="healthy"/>Healthy</span><span><i className="degraded"/>Degraded</span><span><i className="missing"/>Missing</span><span><b/>Inferred link</span></aside>
      {(selectedNode||selectedLink||path||impact)&&<DetailPanel node={selectedNode} link={selectedLink} graph={graph} path={path} impact={impact} onClose={()=>{setSelectedNode(undefined);setSelectedLink(undefined);setPath(undefined);setImpact(undefined)}} onAction={async action=>{if(!selectedLink)return;await endpoints.topologyLinkAction(topologyId,selectedLink.id,action);setNotice(`Link ${action} completed.`);void load()}} admin={user?.role==="admin"}/>}
    </div>
    <GraphFallback nodes={filtered.nodes} links={filtered.links}/>
    {linkForm&&<ManualLinkForm topologyId={topologyId} nodes={graph.nodes} onClose={()=>setLinkForm(false)} onSaved={()=>{setLinkForm(false);void load()}}/>}
  </section>;
}

function useUrlFilters(){
  const [params,setParams]=useSearchParams();
  const filters:TopologyFilterState={...emptyFilters,search:params.get("search")??"",status:params.get("status")??"",deviceType:params.get("device_type")??"",layer:params.get("layer")??"",role:params.get("role")??"",vendor:params.get("vendor")??"",linkType:params.get("link_type")??"",confidence:Number(params.get("confidence")??0),includeHidden:params.get("hidden")==="true",orphanOnly:params.get("orphans")==="true",conflictOnly:params.get("conflicts")==="true"};
  const update=(next:TopologyFilterState)=>{const p=new URLSearchParams();Object.entries(next).forEach(([key,value])=>{if(value&&value!==0)p.set(key==="deviceType"?"device_type":key==="linkType"?"link_type":key==="includeHidden"?"hidden":key==="orphanOnly"?"orphans":key==="conflictOnly"?"conflicts":key,String(value))});setParams(p,{replace:true})};
  return [filters,update] as const;
}

function FilterBar({value,onChange}:{value:TopologyFilterState;onChange:(value:TopologyFilterState)=>void}){
  return <section className="topology-filters" aria-label="Graph filters">
    {[["status","Status",["","online","offline","degraded","unknown","missing","provisional"]],["deviceType","Device type",["","switch","router","firewall","server","printer","ups","access_point","endpoint","unknown"]],["layer","Layer",["","external","core","distribution","access","service","endpoint","unknown"]],["linkType","Link type",["","physical","logical","dependency","trunk","wireless","unknown"]]].map(([key,label,options])=><label key={key as string}>{label as string}<select value={String(value[key as keyof TopologyFilterState])} onChange={e=>onChange({...value,[key as string]:e.target.value})}>{(options as string[]).map(option=><option key={option} value={option}>{option?statusText(option):"All"}</option>)}</select></label>)}
    <label>Minimum confidence<input type="range" min="0" max="100" step="5" value={value.confidence} onChange={e=>onChange({...value,confidence:Number(e.target.value)})}/><span>{value.confidence}%</span></label>
    <label className="check"><input type="checkbox" checked={value.includeHidden} onChange={e=>onChange({...value,includeHidden:e.target.checked})}/>Hidden</label>
    <label className="check"><input type="checkbox" checked={value.orphanOnly} onChange={e=>onChange({...value,orphanOnly:e.target.checked})}/>Orphans only</label>
    <label className="check"><input type="checkbox" checked={value.conflictOnly} onChange={e=>onChange({...value,conflictOnly:e.target.checked})}/>Conflicts only</label>
    <button onClick={()=>onChange(emptyFilters)}>Reset filters</button>
  </section>
}

function filterGraph(graph:TopologyGraph|undefined,filters:TopologyFilterState,orphans:string[],conflicts:Set<string>){
  if(!graph)return {nodes:[],links:[]};
  const search=filters.search.toLowerCase(),orphanSet=new Set(orphans);
  const nodes=graph.nodes.filter(n=>(!search||[n.label,n.management_ip,n.vendor,n.model,n.node_type,n.role,n.layer].some(value=>String(value??"").toLowerCase().includes(search)))&&(!filters.status||n.status===filters.status)&&(!filters.deviceType||n.node_type===filters.deviceType)&&(!filters.layer||n.layer===filters.layer)&&(!filters.role||n.role===filters.role)&&(!filters.vendor||n.vendor===filters.vendor)&&(!filters.orphanOnly||orphanSet.has(n.id))&&(!filters.conflictOnly||conflicts.has(n.id)));
  const ids=new Set(nodes.map(n=>n.id));
  const links=graph.links.filter(l=>ids.has(l.source_node_id)&&ids.has(l.target_node_id)&&(!filters.linkType||l.link_type===filters.linkType));
  return {nodes,links};
}

function buildLayout(nodes:TopologyNode[],links:TopologyLink[],mode:TopologyLayoutMode,saved:Map<string,{x:number;y:number}>){
  if(mode==="manual"&&nodes.some(n=>saved.has(n.id)))return nodes.map((node,index)=>({node,position:saved.get(node.id)??{x:(index%8)*220,y:Math.floor(index/8)*150}}));
  if(mode==="hierarchical"){
    const ranks=["external","core","distribution","access","service","endpoint","unknown"];
    const groups=new Map(ranks.map(rank=>[rank,nodes.filter(n=>(n.layer||"unknown")===rank)]));
    return ranks.flatMap((rank,row)=>(groups.get(rank)??[]).map((node,column)=>({node,position:{x:column*230-(groups.get(rank)!.length-1)*115,y:row*175}})));
  }
  if(mode==="radial")return nodes.map((node,index)=>{const angle=index/Math.max(1,nodes.length)*Math.PI*2,radius=Math.max(220,nodes.length*18);return {node,position:{x:Math.cos(angle)*radius,y:Math.sin(angle)*radius}}});
  if(mode==="force"){
    const degree=new Map<string,number>();links.forEach(l=>{degree.set(l.source_node_id,(degree.get(l.source_node_id)??0)+1);degree.set(l.target_node_id,(degree.get(l.target_node_id)??0)+1)});
    return [...nodes].sort((a,b)=>(degree.get(b.id)??0)-(degree.get(a.id)??0)).map((node,index)=>{const ring=Math.floor(Math.sqrt(index)),angle=index*2.399;return {node,position:{x:Math.cos(angle)*ring*155,y:Math.sin(angle)*ring*155}}});
  }
  return nodes.map((node,index)=>({node,position:{x:(index%8)*220,y:Math.floor(index/8)*150}}));
}

function DetailPanel({node,link,graph,path,impact,onClose,onAction,admin}:{node?:TopologyNode;link?:TopologyLink;graph:TopologyGraph;path?:TopologyPathResult;impact?:TopologyImpact;onClose:()=>void;onAction:(action:"confirm"|"suppress"|"restore")=>Promise<void>;admin:boolean}){
  const byId=new Map(graph.nodes.map(n=>[n.id,n]));
  return <aside className="topology-detail" aria-label={node?"Node details":link?"Link details":"Analysis details"}>
    <header><div><span>{node?"Node":link?"Relationship":path?"Path analysis":"Impact analysis"}</span><h2>{node?.label??(link?`${byId.get(link.source_node_id)?.label} → ${byId.get(link.target_node_id)?.label}`:path?"Selected path":"Potential impact")}</h2></div><button aria-label="Close details" onClick={onClose}>×</button></header>
    {node&&<><DetailGrid rows={[["Status",node.status],["Type",node.node_type],["Role / layer",`${node.role} / ${node.layer}`],["Management IP",node.management_ip],["Vendor / model",[node.vendor,node.model].filter(Boolean).join(" ")],["Confidence",`${node.confidence_score}%`],["Source",node.source_type],["Network zone",node.network_zone_id],["Building / floor",[node.building_id,node.floor_id].filter(Boolean).join(" / ")] ]}/><p>{node.description||"No topology-specific description."}</p><div className="topology-panel-actions"><Link to={node.device_id?`/devices/${node.device_id}`:"#"} aria-disabled={!node.device_id}>Open inventory</Link><button>Trace path from node</button><button>Analyze impact</button></div></>}
    {link&&<><DetailGrid rows={[["Status",link.status],["Type / direction",`${link.link_type} / ${link.direction}`],["Source interface",link.source_interface_id],["Target interface",link.target_interface_id],["Speed",link.speed_bps?`${(link.speed_bps/1e9).toFixed(2)} Gbps`:null],["VLAN",link.vlan_id],["Confidence",`${link.confidence_score}%`],["Discovery",link.discovery_method],["Evidence",link.source_type],["First seen",fmt(link.created_at)],["Last updated",fmt(link.updated_at)]]}/><pre>{JSON.stringify(link.metadata,null,2)}</pre>{admin&&<div className="topology-panel-actions"><button onClick={()=>void onAction("confirm")}>Confirm</button><button onClick={()=>void onAction("suppress")}>Suppress</button><button onClick={()=>void onAction("restore")}>Restore</button></div>}</>}
    {path&&<AnalysisPath path={path} byId={byId}/>}
    {impact&&<><p className="topology-caution">{impact.confidence_note}</p><strong>{impact.count} potentially affected node(s)</strong><ol>{impact.potentially_affected_nodes.map(n=><li key={n.id}>{n.label}<small>{n.layer} · {n.status}</small></li>)}</ol></>}
  </aside>
}

function AnalysisPath({path,byId}:{path:TopologyPathResult;byId:Map<string,TopologyNode>}){
  const paths=path.paths??(path.nodes?[{nodes:path.nodes,links:path.links,hops:path.depth}]:[]);
  return <>{!paths.length?<Feedback empty="No supported path was found. This does not prove that no packet route exists."/>:paths.map((p,index)=><section className="topology-path-summary" key={index}><strong>{index?"Alternate path":`Shortest ${path.path_type} path`} · {p.hops??Math.max(0,p.nodes.length-1)} hops</strong><ol>{p.nodes.map(id=><li key={id}>{byId.get(id)?.label??id}</li>)}</ol></section>)}<p className="topology-caution">Paths reflect modeled physical and dependency evidence, not guaranteed packet routing.</p></>;
}

function ManualLinkForm({topologyId,nodes,onClose,onSaved}:{topologyId:string;nodes:TopologyNode[];onClose:()=>void;onSaved:()=>void}){
  const [source,setSource]=useState(""),[target,setTarget]=useState(""),[type,setType]=useState("physical"),[vlan,setVlan]=useState(""),[error,setError]=useState("");
  const submit=async(e:FormEvent)=>{e.preventDefault();if(source===target){setError("Source and target must be different.");return}try{await endpoints.createTopologyLink(topologyId,{source_node_id:source,target_node_id:target,source_interface_id:null,target_interface_id:null,link_type:type,direction:"bidirectional",status:"active",speed_bps:null,duplex:null,vlan_id:vlan?Number(vlan):null,lag_identifier:null,source_type:"manual",confidence_score:100,discovery_method:"manual",is_manual:true,is_confirmed:true,metadata:{notes:"Created from reviewed topology map"}});onSaved()}catch(e){setError(message(e))}};
  return <Modal title="Create reviewed manual link" onClose={onClose}><form className="topology-form" onSubmit={submit}><label>Source<select required value={source} onChange={e=>setSource(e.target.value)}><option value="">Select node</option>{nodes.map(n=><option key={n.id} value={n.id}>{n.label}</option>)}</select></label><label>Target<select required value={target} onChange={e=>setTarget(e.target.value)}><option value="">Select node</option>{nodes.map(n=><option key={n.id} value={n.id}>{n.label}</option>)}</select></label><label>Link type<select value={type} onChange={e=>setType(e.target.value)}><option>physical</option><option>logical</option><option>trunk</option><option>routed</option><option>wireless</option></select></label><label>VLAN<input type="number" min="1" max="4094" value={vlan} onChange={e=>setVlan(e.target.value)}/></label><p>Interface ownership and duplicate relationships are validated by the backend.</p>{error&&<p role="alert">{error}</p>}<footer><button type="button" onClick={onClose}>Cancel</button><button className="primary-action">Create link</button></footer></form></Modal>
}

function ReviewWorkspace({topologyId,user,mode}:{topologyId:string;user?:User;mode:"review"|"conflicts"}){
  const [reviews,setReviews]=useState<TopologyReviewItem[]>([]),[conflicts,setConflicts]=useState<TopologyConflict[]>([]),[loading,setLoading]=useState(true),[error,setError]=useState(""),[notice,setNotice]=useState("");
  const load=useCallback(async()=>{setLoading(true);try{const [r,c]=await Promise.all([endpoints.topologyReviewItems(topologyId,{page_size:100,status:"pending"}),endpoints.topologyConflicts(topologyId,{page_size:100,status:"open"})]);setReviews(r.items);setConflicts(c.items);setError("")}catch(e){setError(message(e))}finally{setLoading(false)}},[topologyId]);
  useEffect(()=>{void load()},[load]);
  const resolve=async(item:TopologyReviewItem,action:"approve"|"reject"|"ignore")=>{if(action==="approve"&&!confirm("Approve and apply this reviewed topology change?"))return;try{await endpoints.resolveTopologyReview(topologyId,item.id,action);setNotice(`Review item ${action}d.`);void load()}catch(e){setNotice(message(e))}};
  if(loading||error)return <Feedback loading={loading} error={error} onRetry={load}/>;
  const severity=(name:string)=>conflicts.filter(c=>c.severity===name).length;
  return <><header className="topology-title"><div><span>Administrator authority</span><h1>{mode==="conflicts"?"Topology conflicts":"Inference review"}</h1><p>Evidence and projected impact remain visible before graph-changing decisions.</p></div></header>
    <section className="topology-kpis"><Kpi label="Pending reviews" value={reviews.length}/><Kpi label="Critical" value={severity("critical")}/><Kpi label="High" value={severity("high")}/><Kpi label="Medium" value={severity("medium")}/><Kpi label="Low" value={severity("low")}/></section>
    {mode==="review"?<Panel title="Proposed graph changes" copy="Open graph context in a separate tab before approving ambiguous changes.">{!reviews.length?<Feedback empty="No inference review items are pending."/>:<Table heads={["Proposal","Entity","Confidence","Evidence","Impact","Created","Actions"]}>{reviews.map(item=><tr key={item.id}><td><strong>{statusText(item.review_type)}</strong><small>{JSON.stringify(item.proposed_change)}</small></td><td>{item.entity_type}</td><td>{item.confidence_score}%</td><td><code>{JSON.stringify(item.evidence)}</code></td><td><code>{JSON.stringify(item.impact)}</code></td><td>{fmt(item.created_at)}</td><td className="topology-actions"><Link to={`/topology/${topologyId}/map?search=${item.entity_id??""}`}>Graph context</Link>{user?.role==="admin"&&<><button onClick={()=>void resolve(item,"approve")}>Approve</button><button onClick={()=>void resolve(item,"reject")}>Reject</button><button onClick={()=>void resolve(item,"ignore")}>Ignore</button></>}</td></tr>)}</Table>}</Panel>:
    <Panel title="Detected conflicts" copy="Conflicts are evidence records; no inventory identity is changed automatically.">{!conflicts.length?<Feedback empty="No open topology conflicts."/>:<Table heads={["Conflict","Severity","Entity","Evidence","Confidence","Recommendation","Detected"]}>{conflicts.map(c=><tr key={c.id}><td>{statusText(c.conflict_type)}</td><td><StatusBadge status={c.severity}/></td><td>{c.entity_type}<small>{c.entity_id}</small></td><td><code>{JSON.stringify(c.evidence)}</code></td><td>{c.confidence_score}%</td><td>{c.suggested_resolution}</td><td>{fmt(c.detected_at)}</td></tr>)}</Table>}</Panel>}
    {notice&&<div className="topology-banner" role="status">{notice}</div>}
  </>;
}

function Snapshots({topologyId,user}:{topologyId:string;user?:User}){
  const [rows,setRows]=useState<TopologySnapshot[]>([]),[comparison,setComparison]=useState<SnapshotComparison>(),[loading,setLoading]=useState(true),[error,setError]=useState("");
  const load=useCallback(()=>endpoints.topologySnapshots(topologyId,{page_size:100}).then(r=>{setRows(r.items);setError("")}).catch(e=>setError(message(e))).finally(()=>setLoading(false)),[topologyId]);
  useEffect(()=>{void load()},[load]);
  if(loading||error)return <Feedback loading={loading} error={error} onRetry={load}/>;
  return <><header className="topology-title"><div><span>Historical evidence</span><h1>Topology snapshots</h1><p>Browse immutable graph captures and compare a snapshot with the current modeled topology.</p></div>{user?.role==="admin"&&<button className="primary-action" onClick={()=>void endpoints.createTopologySnapshot(topologyId,{name:`Snapshot ${new Date().toLocaleString()}`,snapshot_type:"manual"}).then(load)}>Create snapshot</button>}</header>
    <Panel title="Snapshots" copy="Historical graphs are read-only and never receive live overlays.">{!rows.length?<Feedback empty="No snapshots have been created."/>:<Table heads={["Name","Type","Status","Nodes","Links","Created","Actions"]}>{rows.map(s=><tr key={s.id}><td><strong>{s.name}</strong></td><td>{s.snapshot_type}</td><td><StatusBadge status={s.status}/></td><td>{s.node_count}</td><td>{s.link_count}</td><td>{fmt(s.created_at)}</td><td className="topology-actions"><Link to={`/topology/${topologyId}/snapshots/${s.id}`}>View</Link><button onClick={()=>void endpoints.compareTopologySnapshot(topologyId,s.id).then(setComparison)}>Compare current</button></td></tr>)}</Table>}</Panel>
    {comparison&&<Comparison data={comparison}/>}
  </>;
}

function SnapshotViewer({topologyId,snapshotId}:{topologyId:string;snapshotId:string}){
  const [data,setData]=useState<Awaited<ReturnType<typeof endpoints.topologySnapshotGraph>>>(),[error,setError]=useState("");
  useEffect(()=>{void endpoints.topologySnapshotGraph(topologyId,snapshotId).then(setData).catch(e=>setError(message(e)))},[topologyId,snapshotId]);
  if(!data||error)return <Feedback loading={!data&&!error} error={error}/>;
  const nodes:TopologyNode[]=data.nodes.map((n,index)=>({...n,id:n.source_topology_node_id??n.id,topology_id:topologyId,device_id:n.device_id??null,discovered_device_id:null,snmp_target_id:null,description:null,parent_node_id:null,network_zone_id:null,building_id:null,floor_id:null,room_id:null,department_id:null,vendor:null,model:null,source_type:"snapshot",confidence_score:100,is_manual:false,is_hidden:false,metadata:n.metadata??{},created_at:data.snapshot.created_at,updated_at:data.snapshot.created_at,management_ip:n.management_ip??null,label:n.label??`Node ${index+1}`}));
  const byId=new Map(nodes.map(n=>[n.id,n]));
  return <><div className="topology-banner historical">Historical snapshot · {data.snapshot.name} · {fmt(data.snapshot.created_at)} · read-only</div><div className="topology-canvas-wrap snapshot"><ReactFlow nodes={nodes.map((n,i)=>({id:n.id,type:"device",position:{x:(i%7)*220,y:Math.floor(i/7)*160},data:{node:n,selectedPath:false,impacted:false,conflicted:false}}))} edges={data.links.map(l=>({id:l.source_topology_link_id??l.id,source:l.source_node_reference??l.source_node_id,target:l.target_node_reference??l.target_node_id,label:l.link_type}))} nodeTypes={nodeTypes} fitView nodesDraggable={false}><Background/><MiniMap/><Controls/></ReactFlow></div><GraphFallback nodes={[...byId.values()]} links={[]}/></>;
}

function Comparison({data}:{data:SnapshotComparison}){
  return <Panel title="Snapshot compared with current graph" copy="Added, removed, and changed identifiers are shown as an accessible summary."><section className="topology-compare"><Kpi label="Added nodes" value={data.added_nodes.length}/><Kpi label="Removed nodes" value={data.removed_nodes.length}/><Kpi label="Added links" value={data.added_links.length}/><Kpi label="Removed links" value={data.removed_links.length}/><Kpi label="Layer changes" value={data.layer_changes.length}/><Kpi label="Parent changes" value={data.parent_changes.length}/></section></Panel>
}

function Changes({topologyId}:{topologyId:string}){
  const [rows,setRows]=useState<TopologyChange[]>([]),[error,setError]=useState("");
  useEffect(()=>{void endpoints.topologyChanges(topologyId,{page_size:100}).then(r=>setRows(r.items)).catch(e=>setError(message(e)))},[topologyId]);
  if(error)return <Feedback error={error}/>;
  return <><header className="topology-title"><div><span>Explainable history</span><h1>Topology changes</h1><p>Bounded change history across nodes, links, reviews, and inference.</p></div></header><Panel title="Change timeline" copy="Unchanged observations do not produce history noise.">{!rows.length?<Feedback empty="No topology changes are recorded."/>:<Table heads={["Time","Change","Entity","Source","Confidence","Before","After","Review"]}>{rows.map(c=><tr key={c.id}><td>{fmt(c.detected_at)}</td><td>{statusText(c.change_type)}</td><td>{c.entity_type}</td><td>{c.source_type}</td><td>{c.confidence_score??"—"}</td><td><code>{JSON.stringify(c.previous_values)}</code></td><td><code>{JSON.stringify(c.current_values)}</code></td><td><StatusBadge status={c.review_status}/></td></tr>)}</Table>}</Panel></>;
}

function TopologySettings({topologyId,user}:{topologyId:string;user?:User}){
  const [topology,setTopology]=useState<Topology>(),[schedule,setSchedule]=useState<TopologySchedule>(),[health,setHealth]=useState<TopologyHealth>(),[scheduler,setScheduler]=useState<TopologySchedulerStatus>(),[runs,setRuns]=useState<TopologyOperationalRun[]>([]),[rules,setRules]=useState<TopologyAlertRule[]>([]),[alerts,setAlerts]=useState<TopologyAlertEvent[]>([]),[retention,setRetention]=useState<TopologyRetentionPreview>(),[notice,setNotice]=useState(""),[error,setError]=useState("");
  const load=useCallback(async()=>{try{const [t,s,h,j,r,ar,ae,ret]=await Promise.all([endpoints.topology(topologyId),endpoints.topologySchedule(topologyId),endpoints.topologyHealth(topologyId),endpoints.topologySchedulerStatus(topologyId),endpoints.topologyOperationalRuns(topologyId,{page_size:20}),endpoints.topologyAlertRules({topology_id:topologyId,page_size:50}),endpoints.topologyAlerts({topology_id:topologyId,page_size:50}),endpoints.topologyRetentionPreview()]);setTopology(t);setSchedule(s);setHealth(h);setScheduler(j);setRuns(r.items);setRules(ar.items);setAlerts(ae.items);setRetention(ret);setError("")}catch(e){setError(message(e))}},[topologyId]);
  useEffect(()=>{void load()},[load]);
  if(error)return <Feedback error={error} onRetry={load}/>;
  if(!topology||!schedule||!health||!scheduler||!retention)return <Feedback loading/>;
  if(user?.role!=="admin")return <Feedback error="Administrator access is required to change topology settings."/>;
  const saveSchedule=async(e:FormEvent)=>{e.preventDefault();try{const body={neighbor_collection_enabled:schedule.neighbor_collection_enabled,neighbor_collection_interval_minutes:schedule.neighbor_collection_interval_minutes,inference_enabled:schedule.inference_enabled,inference_interval_minutes:schedule.inference_interval_minutes,snapshot_enabled:schedule.snapshot_enabled,snapshot_interval_hours:schedule.snapshot_interval_hours,change_evaluation_enabled:schedule.change_evaluation_enabled,change_evaluation_interval_minutes:schedule.change_evaluation_interval_minutes,protocol_mode:schedule.protocol_mode,dry_run_default:schedule.dry_run_default,maximum_targets_per_run:schedule.maximum_targets_per_run,maximum_run_duration:schedule.maximum_run_duration,jitter_seconds:schedule.jitter_seconds,stale_run_timeout_minutes:schedule.stale_run_timeout_minutes,missing_link_grace_runs:schedule.missing_link_grace_runs,automatic_review_threshold:schedule.automatic_review_threshold,alerting_enabled:schedule.alerting_enabled,enabled:schedule.enabled};setSchedule(await endpoints.updateTopologySchedule(topologyId,body));setNotice("Schedule reconciled with deterministic jobs.");void load()}catch(e){setNotice(message(e))}};
  const addRule=async()=>{try{await endpoints.createTopologyAlertRule({name:"Topology stale",topology_id:topologyId,rule_type:"topology_stale",severity:"warning",enabled:false,minimum_confidence:70,consecutive_occurrences:2,recovery_occurrences:2,suppress_during_maintenance:true,notification_enabled:true,ticket_creation_enabled:false});setNotice("Disabled alert rule created. Review and enable it explicitly.");void load()}catch(e){setNotice(message(e))}};
  const maintenance=async()=>{try{if(schedule.maintenance_mode)await endpoints.endTopologyMaintenance(topologyId);else{const reason=window.prompt("Maintenance reason (required)");if(!reason)return;await endpoints.startTopologyMaintenance(topologyId,reason)}setNotice(schedule.maintenance_mode?"Maintenance ended.":"Maintenance started; topology alerts are suppressed.");void load()}catch(e){setNotice(message(e))}};
  return <><header className="topology-title"><div><span>Production operations</span><h1>Topology operations</h1><p>Schedule bounded collection, inference, snapshots, health evaluation, alerts, and retention without changing inventory automatically.</p></div></header>
    <section className="topology-kpis"><Kpi label="Health" value={statusText(health.overall_status)}/><Kpi label="Evidence" value={health.evidence_freshness}/><Kpi label="Scheduler jobs" value={scheduler.jobs.length}/><Kpi label="Open alerts" value={alerts.filter(a=>a.is_open).length}/><Kpi label="Conflicts" value={health.conflict_count}/><Kpi label="Orphans" value={health.orphan_count}/><Kpi label="Protected snapshots" value={retention.protected_records}/></section>
    {health.stale_topology&&<div className="topology-banner warning" role="status">Topology evidence is stale. Review target availability and the scheduled collection run history.</div>}
    <Panel title="Topology configuration" copy="Disabling preserves graph history while preventing scheduled execution."><form className="topology-form" onSubmit={e=>{e.preventDefault();void endpoints.updateTopology(topologyId,{name:topology.name,description:topology.description,layout_mode:topology.layout_mode}).then(value=>{setTopology(value);setNotice("Topology settings saved.")}).catch(e=>setNotice(message(e)))}}><label>Name<input value={topology.name} onChange={e=>setTopology({...topology,name:e.target.value})}/></label><label>Description<textarea value={topology.description??""} onChange={e=>setTopology({...topology,description:e.target.value})}/></label><label>Default layout<select value={topology.layout_mode} onChange={e=>setTopology({...topology,layout_mode:e.target.value as TopologyLayoutMode})}><option value="manual">Manual</option><option value="hierarchical">Hierarchical</option><option value="force">Force</option><option value="grid">Grid</option></select></label><footer><button className="primary-action">Save settings</button><button type="button" onClick={()=>void endpoints.setDefaultTopology(topologyId).then(value=>{setTopology(value);setNotice("Default topology updated.")})}>Set default</button><button type="button" className="danger-action" onClick={()=>void endpoints.enableTopology(topologyId,!topology.enabled).then(setTopology)}>{topology.enabled?"Disable":"Enable"}</button></footer></form></Panel>
    <Panel title="Scheduled workflow" copy="Jobs are stable per topology, coalesced after downtime, jittered, and protected from overlap."><form className="topology-form topology-operations-form" onSubmit={saveSchedule}>
      <label className="topology-check"><input type="checkbox" checked={schedule.enabled} onChange={e=>setSchedule({...schedule,enabled:e.target.checked})}/>Enable topology scheduler</label>
      <label className="topology-check"><input type="checkbox" checked={schedule.neighbor_collection_enabled} onChange={e=>setSchedule({...schedule,neighbor_collection_enabled:e.target.checked})}/>Collect approved LLDP/CDP neighbors</label><label>Collection interval (minutes)<input type="number" min="15" max="10080" value={schedule.neighbor_collection_interval_minutes} onChange={e=>setSchedule({...schedule,neighbor_collection_interval_minutes:Number(e.target.value)})}/></label>
      <label className="topology-check"><input type="checkbox" checked={schedule.inference_enabled} onChange={e=>setSchedule({...schedule,inference_enabled:e.target.checked})}/>Run inference</label><label>Inference interval (minutes)<input type="number" min="15" max="10080" value={schedule.inference_interval_minutes} onChange={e=>setSchedule({...schedule,inference_interval_minutes:Number(e.target.value)})}/></label>
      <label className="topology-check"><input type="checkbox" checked={schedule.snapshot_enabled} onChange={e=>setSchedule({...schedule,snapshot_enabled:e.target.checked})}/>Create snapshots</label><label>Snapshot interval (hours)<input type="number" min="1" max="720" value={schedule.snapshot_interval_hours} onChange={e=>setSchedule({...schedule,snapshot_interval_hours:Number(e.target.value)})}/></label>
      <label className="topology-check"><input type="checkbox" checked={schedule.change_evaluation_enabled} onChange={e=>setSchedule({...schedule,change_evaluation_enabled:e.target.checked})}/>Evaluate changes</label><label>Evaluation interval (minutes)<input type="number" min="15" max="10080" value={schedule.change_evaluation_interval_minutes} onChange={e=>setSchedule({...schedule,change_evaluation_interval_minutes:Number(e.target.value)})}/></label>
      <label className="topology-check"><input type="checkbox" checked={schedule.alerting_enabled} onChange={e=>setSchedule({...schedule,alerting_enabled:e.target.checked})}/>Evaluate enabled alert rules</label><label>Protocol<select value={schedule.protocol_mode} onChange={e=>setSchedule({...schedule,protocol_mode:e.target.value as TopologySchedule["protocol_mode"]})}><option value="auto">Auto</option><option value="lldp">LLDP</option><option value="cdp">CDP</option><option value="both">Both</option></select></label>
      <label>Maximum targets per run<input type="number" min="1" max="500" value={schedule.maximum_targets_per_run} onChange={e=>setSchedule({...schedule,maximum_targets_per_run:Number(e.target.value)})}/></label><label>Jitter (seconds)<input type="number" min="0" max="900" value={schedule.jitter_seconds} onChange={e=>setSchedule({...schedule,jitter_seconds:Number(e.target.value)})}/></label>
      <footer><button className="primary-action">Save and reconcile jobs</button><button type="button" onClick={()=>void endpoints.pauseTopologySchedule(topologyId).then(()=>{setNotice("Topology jobs paused.");void load()})}>Pause jobs</button><button type="button" onClick={()=>void endpoints.resumeTopologySchedule(topologyId).then(()=>{setNotice("Topology jobs resumed.");void load()})}>Resume jobs</button><button type="button" onClick={()=>void maintenance()}>{schedule.maintenance_mode?"End maintenance":"Start maintenance"}</button></footer>
    </form></Panel>
    <Panel title="Scheduler state and runs" copy={`Scheduler ${scheduler.scheduler_running?"running":"stopped"}. Maintenance ${schedule.maintenance_mode?`active: ${schedule.maintenance_reason}`:"inactive"}.`}>{!runs.length?<Feedback empty="No scheduled topology operations have run."/>:<Table heads={["Started","Operation","Status","Targets","Succeeded","Failed","Changes","Alerts"]}>{runs.map(run=><tr key={run.id}><td>{fmt(run.started_at)}</td><td>{run.run_type}</td><td><StatusBadge status={run.status}/></td><td>{run.target_count}</td><td>{run.success_count}</td><td>{run.failure_count}</td><td>{run.changes_found}</td><td>{run.alerts_created}</td></tr>)}</Table>}</Panel>
    <Panel title="Topology alert rules" copy="Rules are disabled by default and require consecutive evidence before opening."><div className="topology-panel-actions"><button onClick={()=>void addRule()}>Add safe stale-topology rule</button></div>{!rules.length?<Feedback empty="No topology alert rules are configured."/>:<Table heads={["Rule","Type","Severity","Enabled","Occurrences","Actions"]}>{rules.map(rule=><tr key={rule.id}><td>{rule.name}</td><td>{statusText(rule.rule_type)}</td><td><StatusBadge status={rule.severity}/></td><td>{rule.enabled?"Yes":"No"}</td><td>{rule.consecutive_occurrences} breach / {rule.recovery_occurrences} recovery</td><td><button onClick={()=>void endpoints.updateTopologyAlertRule(rule.id,{enabled:!rule.enabled}).then(()=>void load())}>{rule.enabled?"Disable":"Enable"}</button></td></tr>)}</Table>}</Panel>
    <Panel title="Retention and exports" copy="Protected baselines and audit history are excluded from cleanup."><DetailGrid rows={[["Eligible snapshots",retention.eligible_snapshots],["Eligible stale observations",retention.eligible_observations],["Eligible operational runs",retention.eligible_runs],["Protected records",retention.protected_records]]}/><div className="topology-panel-actions"><button onClick={()=>void endpoints.topologyRetentionPreview().then(setRetention)}>Refresh preview</button><button className="danger-action" onClick={()=>{if(confirm("Delete only eligible unprotected topology records?"))void endpoints.runTopologyRetentionCleanup().then(value=>{setRetention(value);setNotice("Bounded retention cleanup completed.")})}}>Run cleanup</button><button onClick={()=>void endpoints.exportTopologyCsv(topologyId,"nodes").then(file=>downloadBlob(file.blob,file.filename))}>Export nodes CSV</button><button onClick={()=>void endpoints.exportTopologyCsv(topologyId,"links").then(file=>downloadBlob(file.blob,file.filename))}>Export links CSV</button></div></Panel>
    {notice&&<div className="topology-banner" role="status">{notice}</div>}</>;
}

function GraphFallback({nodes,links}:{nodes:TopologyNode[];links:TopologyLink[]}){
  return <details className="topology-fallback"><summary>Accessible graph table ({nodes.length} nodes, {links.length} links)</summary><Table heads={["Node","Status","Type","Layer","IP","Confidence"]}>{nodes.map(n=><tr key={n.id}><td>{n.label}</td><td>{n.status}</td><td>{n.node_type}</td><td>{n.layer}</td><td>{n.management_ip??"—"}</td><td>{n.confidence_score}%</td></tr>)}</Table></details>
}
function DetailGrid({rows}:{rows:Array<[string,unknown]>}){return <dl className="topology-detail-grid">{rows.filter(([,value])=>value!==null&&value!==undefined&&value!=="").map(([label,value])=><div key={label}><dt>{label}</dt><dd>{String(value)}</dd></div>)}</dl>}
function Kpi({label,value}:{label:string;value:string|number}){return <article className="topology-kpi"><span>{label}</span><strong>{value}</strong></article>}
function Panel({title,copy,children}:{title:string;copy:string;children:ReactNode}){return <section className="topology-panel"><header><h2>{title}</h2><p>{copy}</p></header>{children}</section>}
function Table({heads,children}:{heads:string[];children:ReactNode}){return <div className="topology-table-wrap"><table className="topology-table"><thead><tr>{heads.map(h=><th key={h} scope="col">{h}</th>)}</tr></thead><tbody>{children}</tbody></table></div>}
function activeFilterCount(filters:TopologyFilterState){return Object.entries(filters).filter(([key,value])=>key!=="search"&&value!==""&&value!==false&&value!==0).length}
function edgeLabel(link:TopologyLink){return [link.link_type,link.vlan_id?`VLAN ${link.vlan_id}`:"",link.speed_bps?`${Math.round(link.speed_bps/1e6)} Mbps`:""].filter(Boolean).join(" · ")}
function statusColor(status:string){return ({online:"#2fcf8f",healthy:"#2fcf8f",degraded:"#f7b955",offline:"#ee6b75",missing:"#8a93a5"} as Record<string,string>)[status]??"#8391a7"}
function downloadBlob(blob:Blob,filename:string){const url=URL.createObjectURL(blob),anchor=document.createElement("a");anchor.href=url;anchor.download=filename;anchor.click();URL.revokeObjectURL(url)}
