import { NavLink } from "react-router-dom";
import { Icon, type IconName } from "./Icon";

const links: { label: string; to: string; icon: IconName }[] = [
  { label: "Overview", to: "/dashboard", icon: "dashboard" }, { label: "Reports", to: "/reports", icon: "audit" }, { label: "Devices", to: "/devices", icon: "devices" }, { label: "Network monitor", to: "/network", icon: "network" }, { label: "Alerts", to: "/alerts", icon: "alerts" }, { label: "Service tickets", to: "/tickets", icon: "tickets" }, { label: "Team & access", to: "/users", icon: "users" }, { label: "Audit trail", to: "/audit", icon: "audit" }, { label: "Settings", to: "/settings", icon: "settings" },
];

export default function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  return <aside className={`sidebar ${open ? "is-open" : ""}`}>
    <div className="sidebar-brand"><span className="brand-mark">HI</span><div><strong>HIOP</strong><small>IT operations portal</small></div><button className="icon-button sidebar-close" onClick={onClose} aria-label="Close navigation"><Icon name="close"/></button></div>
    <nav className="sidebar-nav" aria-label="Primary navigation">
      <p className="nav-label">Workspace</p>
      {links.slice(0, 6).map(link => <NavLink key={link.to} to={link.to} onClick={onClose} className={({isActive}) => `nav-link ${isActive ? "active" : ""}`}><Icon name={link.icon}/><span>{link.label}</span></NavLink>)}
      <p className="nav-label nav-label-spaced">Administration</p>
      {links.slice(6).map(link => <NavLink key={link.to} to={link.to} onClick={onClose} className={({isActive}) => `nav-link ${isActive ? "active" : ""}`}><Icon name={link.icon}/><span>{link.label}</span></NavLink>)}
    </nav>
    <div className="sidebar-health"><div className="health-row"><span><i/> System health</span><strong>Operational</strong></div><div className="health-bar"><span/></div><small>Last sync less than a minute ago</small></div>
  </aside>;
}
