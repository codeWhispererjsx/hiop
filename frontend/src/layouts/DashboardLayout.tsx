/* eslint-disable react-hooks/refs */
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import Header from "../components/Header";
import Sidebar from "../components/Sidebar";
import { endpoints } from "../lib/api";
import type { LiveEvent, PublicSettings, User } from "../lib/types";
import { clearAuthToken, getAuthToken, getOrganizationContext, setOrganizationContext } from "../lib/auth";
import "../styles/dashboard.css";
export default function DashboardLayout({
  children,
  onLiveEvent,
  onLiveStateChange,
}: {
  children: ReactNode;
  onLiveEvent?: (event: LiveEvent) => void;
  onLiveStateChange?: (connected: boolean) => void;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [live, setLive] = useState(false);
  const [user, setUser] = useState<User>();
  const [branding, setBranding] = useState<PublicSettings>();
  const liveEventRef = useRef(onLiveEvent);
  const liveStateRef = useRef(onLiveStateChange);
  liveEventRef.current = onLiveEvent;
  liveStateRef.current = onLiveStateChange;
  useLayoutEffect(() => {
    const resetScroll = () => {
      window.scrollTo({ top: 0, left: 0, behavior: "auto" });
      document.documentElement.scrollTop = 0;
      document.body.scrollTop = 0;
    };
    resetScroll();
    const frame = requestAnimationFrame(resetScroll);
    const timer = window.setTimeout(resetScroll, 0);
    return () => {
      cancelAnimationFrame(frame);
      clearTimeout(timer);
    };
  }, [location.pathname]);
  useEffect(() => {
    void endpoints
      .me()
      .then(setUser)
      .catch(() => undefined);
  }, []);
  useEffect(() => { void endpoints.publicSettings().then(setBranding).catch(() => undefined); }, []);
  useEffect(() => {
    let closed = false;
    let socket: WebSocket | undefined;
    let retry: number | undefined;
    const connect = () => {
      const token = getAuthToken();
      if (!token) return;
      const defaultWebSocketUrl =
        `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws/dashboard`;
      const configuredWebSocketUrl = import.meta.env.VITE_WS_URL;
      const websocketUrl = configuredWebSocketUrl?.startsWith("/")
        ? `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}${configuredWebSocketUrl}`
        : configuredWebSocketUrl ?? defaultWebSocketUrl;
      socket = new WebSocket(
        websocketUrl,
        ["hiop", token],
      );
      socket.onopen = () => { setLive(true); liveStateRef.current?.(true); };
      socket.onmessage = (e) => {
        try {
          liveEventRef.current?.(JSON.parse(e.data) as LiveEvent);
        } catch {
          /* malformed event */
        }
      };
      socket.onerror = () => { setLive(false); liveStateRef.current?.(false); };
      socket.onclose = () => {
        setLive(false);
        liveStateRef.current?.(false);
        if (!closed) retry = window.setTimeout(connect, 2500);
      };
    };
    connect();
    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      socket?.close();
    };
  }, []);
  const logout = () => {
    clearAuthToken();
    navigate("/login");
  };
  return (
    <div className="app-shell">
      <Sidebar open={open} onClose={() => setOpen(false)} role={user?.role} live={live} />
      {open && (
        <button
          className="sidebar-scrim"
          aria-label="Close navigation"
          onClick={() => setOpen(false)}
        />
      )}
      <div className="app-main">
        <Header
          onMenu={() => setOpen(true)}
          live={live}
          onLogout={logout}
          user={user}
          propertyName={branding?.property_name}
        />
        {user?.role==="platformadmin"&&getOrganizationContext()&&<div className="platform-context-bar"><strong>Viewing organization: {branding?.property_name??"Selected organization"}</strong><button onClick={()=>{setOrganizationContext(null);navigate("/platform")}}>Return to Platform Control Center</button></div>}
        <main className="page-content">{children}</main>
      </div>
    </div>
  );
}
