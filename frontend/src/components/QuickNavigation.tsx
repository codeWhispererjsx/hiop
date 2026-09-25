import { useState } from "react";
import { Link } from "react-router-dom";
import Modal from "./Modal";
import { isDesktopMode } from "../lib/appMode";
const pages=[
 ["Dashboard","/dashboard","all"],["Devices & assets","/devices","all"],["Discover & active scans","/discovery-intelligence","all"],["Network monitoring","/network","all"],["Alerts","/alerts","all"],["Incidents","/incidents","all"],["Reports","/reports","all"],["Knowledge","/knowledge","all"],["SNMP monitoring","/snmp","all"],
 ["Organisation","/administration/organization","admin"],["Departments","/administration/organization?tab=departments","admin"],["Locations","/administration/organization?tab=locations","admin"],["Properties & sites","/administration/properties","admin"],["Team & invitations","/users","admin"],
 ...(!isDesktopMode ? [["Billing","/administration/billing","admin"]] : []),
 [isDesktopMode ? "This Computer" : "Local agents","/administration/agents","admin"],["Audit export","/administration/audit","admin"],["Settings","/settings","admin"],["Naming rules","/discovery-intelligence/identity-rules","admin"],["HIOP Owner Console","/platform","platformadmin"]
];
export function QuickNavigation({role}:{role?:string}){const [open,setOpen]=useState(false);const [query,setQuery]=useState("");return <><button className="secondary-action" onClick={()=>setOpen(true)}>Go to page</button>{open&&<Modal title="Go to page" onClose={()=>setOpen(false)}><div className="quick-navigation"><label>Find a page<input autoFocus type="search" placeholder="Try departments, billing, or scans" value={query} onChange={e=>setQuery(e.target.value)}/></label><nav aria-label="Page shortcuts">{pages.filter(([title,,access])=>(access==="all"||access===role)&&title.toLowerCase().includes(query.toLowerCase())).map(([title,path])=><Link key={path} to={path} onClick={()=>setOpen(false)}>{title}</Link>)}</nav></div></Modal>}</>}
