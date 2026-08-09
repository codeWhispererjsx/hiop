import { useLayoutEffect, useRef } from "react";
import { NavLink } from "react-router-dom";
import { Icon, type IconName } from "./Icon";
import BrandLogo from "./BrandLogo";

const primaryLinks: { label: string; to: string; icon: IconName }[] = [
  { label: "Overview", to: "/dashboard", icon: "dashboard" },
  { label: "Discover", to: "/discovery-intelligence", icon: "discovery" },
  { label: "Monitor", to: "/network", icon: "network" },
  { label: "Topology", to: "/topology", icon: "hierarchy" },
  { label: "Manage", to: "/devices", icon: "devices" },
  { label: "Automate", to: "/automation", icon: "settings" },
  { label: "Maintain", to: "/incidents", icon: "alerts" },
  { label: "Administration", to: "/settings", icon: "settings" },
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
  const isAdmin=["admin","superadmin"].includes(role??"");
  const visiblePrimary=primaryLinks.filter(link=>isAdmin||link.to!=="/settings");
  return (
    <aside className={`sidebar ${open ? "is-open" : ""}`}>
      <div className="sidebar-brand">
        <BrandLogo compact />
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
        {visiblePrimary.map((link) => (
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
