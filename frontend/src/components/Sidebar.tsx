import { useLayoutEffect, useRef } from "react";
import { NavLink } from "react-router-dom";
import { Icon, type IconName } from "./Icon";

const links: { label: string; to: string; icon: IconName }[] = [
  { label: "Overview", to: "/dashboard", icon: "dashboard" },
  { label: "Reports", to: "/reports", icon: "audit" },
  { label: "Analytics", to: "/analytics", icon: "dashboard" },
  { label: "Devices", to: "/devices", icon: "devices" },
  { label: "Inventory Import", to: "/imports", icon: "import" },
  { label: "Network monitor", to: "/network", icon: "network" },
  { label: "Discovery Intelligence", to: "/discovery-intelligence", icon: "discovery" },
  { label: "SNMP Monitoring", to: "/snmp", icon: "network" },
  { label: "Network Topology", to: "/topology", icon: "hierarchy" },
  { label: "Organizations", to: "/organizations", icon: "users" },
    { label: "Properties", to: "/properties", icon: "hierarchy" },
    { label: "Buildings", to: "/buildings", icon: "hierarchy" },
    { label: "Property Operations", to: "/operations", icon: "dashboard" },
    { label: "Configuration Management", to: "/configuration-management", icon: "settings" },
    { label: "Automation", to: "/automation", icon: "settings" },
    { label: "Incidents", to: "/incidents", icon: "alerts" },
    { label: "Problem Management", to: "/problems", icon: "search" },
    { label: "Asset & Procurement", to: "/assets", icon: "devices" },
    { label: "Executive BI", to: "/business-intelligence", icon: "dashboard" },
    { label: "Corporate Management", to: "/enterprise", icon: "hierarchy" },
    { label: "Knowledge & Runbooks", to: "/knowledge", icon: "audit" },
    { label: "Change Management", to: "/changes", icon: "settings" },
    { label: "CMDB", to: "/cmdb", icon: "hierarchy" },
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
    const frame = requestAnimationFrame(() => {
      nav.scrollTop = stored;
      const active = nav.querySelector<HTMLElement>(".nav-link.active");
      if (active) {
        const navBounds = nav.getBoundingClientRect();
        const activeBounds = active.getBoundingClientRect();
        const hiddenAbove = activeBounds.top < navBounds.top;
        const hiddenBelow = activeBounds.bottom > navBounds.bottom;
        if (hiddenAbove || hiddenBelow) {
          nav.scrollTop = Math.max(
            0,
            active.offsetTop - (nav.clientHeight - active.clientHeight) / 2,
          );
        }
      }
      lastSidebarScroll = nav.scrollTop;
      sessionStorage.setItem(SIDEBAR_SCROLL_KEY, String(lastSidebarScroll));
    });
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
  }, [role]);
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
          <small>Hospitality IT operations</small>
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
          .filter((link) => links.indexOf(link) < 12)
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
          .filter((link) => links.indexOf(link) >= 12)
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
