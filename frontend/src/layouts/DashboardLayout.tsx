import { useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import Header from "../components/Header";
import Sidebar from "../components/Sidebar";
import { endpoints } from "../lib/api";
import type { LiveEvent, PublicSettings, User } from "../lib/types";
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
      socket = new WebSocket(
        import.meta.env.VITE_WS_URL ?? "ws://127.0.0.1:8000/ws/dashboard",
      );
      socket.onopen = () => { setLive(true); onLiveStateChange?.(true); };
      socket.onmessage = (e) => {
        try {
          onLiveEvent?.(JSON.parse(e.data) as LiveEvent);
        } catch {
          /* malformed event */
        }
      };
      socket.onerror = () => { setLive(false); onLiveStateChange?.(false); };
      socket.onclose = () => {
        setLive(false);
        onLiveStateChange?.(false);
        if (!closed) retry = window.setTimeout(connect, 2500);
      };
    };
    connect();
    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      socket?.close();
    };
  }, [onLiveEvent, onLiveStateChange]);
  const logout = () => {
    localStorage.removeItem("hiop_token");
    navigate("/login");
  };
  return (
    <div className="app-shell">
      <Sidebar open={open} onClose={() => setOpen(false)} />
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
