import { Icon } from "./Icon";
import ThemeToggle from "./ThemeToggle";

export default function Header({onMenu,live,onLogout,user,propertyName}:{onMenu:()=>void;live:boolean;onLogout:()=>void;user?:{username:string;role:string};propertyName?:string}){
  return <header className="topbar">
    <button className="icon-button mobile-menu" onClick={onMenu} aria-label="Open navigation"><Icon name="menu"/></button>
    <div className="property-context"><span>Property</span><strong>{propertyName??"Hotel IT Operations"}</strong></div>
    <div className="topbar-actions"><div className={`live-pill ${live?"connected":""}`}><span/>{live?"Live monitoring":"Reconnecting"}</div><ThemeToggle/><div className="profile"><span className="avatar">{(user?.username??"HI").slice(0,2).toUpperCase()}</span><div><strong>{user?.username??"HIOP user"}</strong><small>{user?.role??"Loading account"}</small></div></div><button className="icon-button" onClick={onLogout} aria-label="Sign out"><Icon name="logout"/></button></div>
  </header>
}
