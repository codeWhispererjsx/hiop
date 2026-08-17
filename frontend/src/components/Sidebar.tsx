import { useLayoutEffect, useRef } from "react";
import { NavLink } from "react-router-dom";
import { Icon, type IconName } from "./Icon";
import BrandLogo from "./BrandLogo";

const primaryLinks: { label: string; to: string; icon: IconName; adminOnly?: boolean }[] = [
  { label: "Overview", to: "/dashboard", icon: "dashboard" },
  { label: "Discover", to: "/discovery-intelligence", icon: "discovery" },
  { label: "Monitor", to: "/network", icon: "network" },
  { label: "Manage", to: "/devices", icon: "devices" },
  { label: "Automate", to: "/automation", icon: "settings" },
  { label: "Maintain", to: "/incidents", icon: "alerts" },
  { label: "Administration", to: "/administration", icon: "settings", adminOnly: true },
];

const monitorLinks: { label: string; to: string; icon: IconName }[] = [
  { label: "Alerts", to: "/alerts", icon: "alerts" },
  { label: "Topology", to: "/topology", icon: "hierarchy" },
  { label: "Segments", to: "/segmentation", icon: "network" },
];

const manageLinks: { label: string; to: string; icon: IconName }[] = [
  { label: "Reports", to: "/reports", icon: "audit" },
  { label: "Procurement", to: "/procurement", icon: "devices" },
  { label: "Vendors", to: "/vendors", icon: "users" },
];

const administrationLinks: { label: string; to: string; icon: IconName }[] = [
  { label: "Organization", to: "/administration/organization", icon: "hierarchy" },
  { label: "Properties", to: "/administration/properties", icon: "server" },
  { label: "Users", to: "/users", icon: "users" },
  { label: "Roles & access", to: "/administration/roles", icon: "lock" },
  { label: "Audit log", to: "/administration/audit", icon: "audit" },
  { label: "Billing", to: "/administration/billing", icon: "devices" },
  { label: "Settings", to: "/settings", icon: "server" },
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
    // Wait until the authenticated role is known. Restoring while role-gated
    // links are still absent clamps a saved lower position back to zero.
    if (!nav || role === undefined) return;
    
    const stored = Number(sessionStorage.getItem(SIDEBAR_SCROLL_KEY) ?? lastSidebarScroll);
    nav.scrollTop = stored;
    
    const frame = requestAnimationFrame(() => {
      nav.scrollTop = stored;
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
  
  const isAdmin = role === "admin";
  const visiblePrimary = primaryLinks.filter((link) => !link.adminOnly || isAdmin);
  
  return (
    <aside 
      className={`sidebar ${open ? "is-open" : ""}`}
      aria-label="Main navigation"
    >
      <div className="sidebar-brand">
        <BrandLogo compact />
        <button
          className="icon-button sidebar-close"
          onClick={onClose}
          aria-label="Close navigation"
        >
          <Icon name="close" aria-hidden="true" />
        </button>
      </div>
      <nav ref={navRef} className="sidebar-nav" aria-label="Primary navigation">
        <p className="nav-label">Workspace</p>
        {visiblePrimary.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            onClick={handleNavigation}
            className={({ isActive }) =>
              `nav-link ${isActive ? "active" : ""}`
            }
            aria-current={({ isActive }) => isActive ? "page" : undefined}
          >
            <Icon name={link.icon} aria-hidden="true" />
            <span>{link.label}</span>
          </NavLink>
        ))}
        <p className="nav-label nav-label-spaced">Manage intelligence</p>
        {manageLinks.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            onClick={handleNavigation}
            className={({ isActive }) => `nav-link nav-sublink ${isActive ? "active" : ""}`}
            aria-current={({ isActive }) => isActive ? "page" : undefined}
          >
            <Icon name={link.icon} aria-hidden="true" />
            <span>{link.label}</span>
          </NavLink>
        ))}
        <p className="nav-label nav-label-spaced">Monitor intelligence</p>
        {monitorLinks.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            onClick={handleNavigation}
            className={({ isActive }) => `nav-link nav-sublink ${isActive ? "active" : ""}`}
            aria-current={({ isActive }) => isActive ? "page" : undefined}
          >
            <Icon name={link.icon} aria-hidden="true" />
            <span>{link.label}</span>
          </NavLink>
        ))}
        {isAdmin && (
          <>
            <p className="nav-label nav-label-spaced">Administration tools</p>
            {administrationLinks.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                onClick={handleNavigation}
                className={({ isActive }) => `nav-link nav-sublink ${isActive ? "active" : ""}`}
                aria-current={({ isActive }) => isActive ? "page" : undefined}
              >
                <Icon name={link.icon} aria-hidden="true" />
                <span>{link.label}</span>
              </NavLink>
            ))}
          </>
        )}
      </nav>
      <div className="sidebar-health" aria-live="polite" aria-atomic="true">
        <div className="health-row">
          <span>
            <i className={live ? "" : "offline"} aria-hidden="true" /> Live channel
          </span>
          <strong>{live ? "Connected" : "Reconnecting"}</strong>
        </div>
        <div className="health-bar">
          <span className={live ? "" : "offline"} aria-hidden="true" />
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
