import { Icon } from "./Icon";
import ThemeToggle from "./ThemeToggle";

export default function Header({onMenu,live,onLogout,user,propertyName,propertyContext,onPropertyChange}:{onMenu:()=>void;live:boolean;onLogout:()=>void;user?:{username:string;role:string};propertyName?:string;propertyContext?:import("../lib/types").PropertyContext;onPropertyChange?:(id:string)=>void}){
  return <header className="topbar">
    <button className="icon-button mobile-menu" onClick={onMenu} aria-label="Open navigation"><Icon name="menu"/></button>
    <div className="property-context"><span>{propertyContext?.organization.name??"Property"}</span>{propertyContext?.properties.length?<select aria-label="Current property" value={propertyContext.active_property_id??"organization"} onChange={e=>onPropertyChange?.(e.target.value)}>{user?.role==="admin"||user?.role==="platformadmin"?<option value="organization">All properties</option>:null}{propertyContext.properties.map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select>:<strong>{propertyName??"Hospitality IT Operations"}</strong>}</div>
    <div className="topbar-actions"><div className={`live-pill ${live?"connected":""}`}><span/>{live?"Live monitoring":"Reconnecting"}</div><ThemeToggle/><div className="profile"><span className="avatar">{(user?.username??"HI").slice(0,2).toUpperCase()}</span><div><strong>{user?.username??"HIOP user"}</strong><small>{user?.role??"Loading account"}</small></div></div><button className="icon-button" onClick={onLogout} aria-label="Sign out"><Icon name="logout"/></button></div>
  </header>
}
