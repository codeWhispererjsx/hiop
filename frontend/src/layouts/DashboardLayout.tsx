/* eslint-disable react-hooks/refs */
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import Header from "../components/Header";
import Sidebar from "../components/Sidebar";
import { endpoints } from "../lib/api";
import type { LiveEvent, PublicSettings, User } from "../lib/types";
import { clearAuthToken, getAuthToken } from "../lib/auth";
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
  const [open, setOpen] = useState(false);
  const [live, setLive] = useState(false);
  const [user, setUser] = useState<User>();
  const [branding, setBranding] = useState<PublicSettings>();
  const liveEventRef = useRef(onLiveEvent);
  const liveStateRef = useRef(onLiveStateChange);
  liveEventRef.current = onLiveEvent;
  liveStateRef.current = onLiveStateChange;
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
      const defaultWebSocketUrl = import.meta.env.DEV
        ? "ws://127.0.0.1:8001/ws/dashboard"
        : `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws/dashboard`;
      socket = new WebSocket(
        import.meta.env.VITE_WS_URL ?? defaultWebSocketUrl,
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
      <Sidebar open={open} onClose={() => setOpen(false)} role={user?.role} />
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
        <main className="page-content">{children}</main>
      </div>
    </div>
  );
}
