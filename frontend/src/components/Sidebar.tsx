import { useLayoutEffect, useRef } from "react";
import { NavLink } from "react-router-dom";
import { Icon, type IconName } from "./Icon";

const links: { label: string; to: string; icon: IconName }[] = [
  { label: "Overview", to: "/dashboard", icon: "dashboard" },
  { label: "Reports", to: "/reports", icon: "audit" },
  { label: "Devices", to: "/devices", icon: "devices" },
  { label: "Inventory Import", to: "/imports", icon: "import" },
  { label: "Network monitor", to: "/network", icon: "network" },
  { label: "Discovery", to: "/discovery", icon: "discovery" },
  { label: "SNMP Monitoring", to: "/snmp", icon: "network" },
  { label: "Alerts", to: "/alerts", icon: "alerts" },
  { label: "Service tickets", to: "/tickets", icon: "tickets" },
  { label: "Locations & structure", to: "/hierarchy", icon: "hierarchy" },
  { label: "Team & access", to: "/users", icon: "users" },
  { label: "Audit trail", to: "/audit", icon: "audit" },
  { label: "Active Directory", to: "/active-directory", icon: "network" },
  { label: "Settings", to: "/settings", icon: "settings" },
];
const SIDEBAR_SCROLL_KEY = "hiop.sidebar.scroll";
let lastSidebarScroll = 0;

export default function Sidebar({
  open,
  onClose,
  role,
  live,
}: {
  open: boolean;
  onClose: () => void;
  role?: string;
  live: boolean;
}) {
  const navRef = useRef<HTMLElement>(null);
  useLayoutEffect(() => {
    const nav = navRef.current;
    if (!nav) return;
    const stored = Number(sessionStorage.getItem(SIDEBAR_SCROLL_KEY) ?? lastSidebarScroll);
    nav.scrollTop = stored;
    const frame = requestAnimationFrame(() => { nav.scrollTop = stored; });
    const remember = () => {
      lastSidebarScroll = nav.scrollTop;
      sessionStorage.setItem(SIDEBAR_SCROLL_KEY, String(lastSidebarScroll));
    };
    nav.addEventListener("scroll", remember, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      remember();
      nav.removeEventListener("scroll", remember);
    };
  }, []);
  const handleNavigation = () => {
    const nav = navRef.current;
    if (nav) {
      lastSidebarScroll = nav.scrollTop;
      sessionStorage.setItem(SIDEBAR_SCROLL_KEY, String(lastSidebarScroll));
    }
    if (window.matchMedia("(max-width: 820px)").matches) onClose();
  };
  const visibleLinks =
    role === "admin"
      ? links
      : links.filter(
          (link) =>
            !["/reports", "/users", "/audit", "/active-directory", "/settings"].includes(link.to),
        );
  return (
    <aside className={`sidebar ${open ? "is-open" : ""}`}>
      <div className="sidebar-brand">
        <span className="brand-mark">HI</span>
        <div>
          <strong>HIOP</strong>
          <small>IT operations portal</small>
        </div>
        <button
          className="icon-button sidebar-close"
          onClick={onClose}
          aria-label="Close navigation"
        >
          <Icon name="close" />
        </button>
      </div>
      <nav ref={navRef} className="sidebar-nav" aria-label="Primary navigation">
        <p className="nav-label">Workspace</p>
        {visibleLinks
          .filter((link) => links.indexOf(link) < 8)
          .map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              onClick={handleNavigation}
              className={({ isActive }) =>
                `nav-link ${isActive ? "active" : ""}`
              }
            >
              <Icon name={link.icon} />
              <span>{link.label}</span>
            </NavLink>
          ))}
        <p className="nav-label nav-label-spaced">Administration</p>
        {visibleLinks
          .filter((link) => links.indexOf(link) >= 8)
          .map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              onClick={handleNavigation}
              className={({ isActive }) =>
                `nav-link ${isActive ? "active" : ""}`
              }
            >
              <Icon name={link.icon} />
              <span>{link.label}</span>
            </NavLink>
          ))}
      </nav>
      <div className="sidebar-health">
        <div className="health-row">
          <span>
            <i className={live ? "" : "offline"} /> Live channel
          </span>
          <strong>{live ? "Connected" : "Reconnecting"}</strong>
        </div>
        <div className="health-bar">
          <span className={live ? "" : "offline"} />
        </div>
        <small>
          {live
            ? "Authenticated updates are active"
            : "Attempting to restore updates"}
        </small>
      </div>
    </aside>
  );
}
