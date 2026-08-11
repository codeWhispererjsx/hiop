import { useEffect, useState } from "react";
import { Icon } from "./Icon";

export function Toast({ message, tone = "success" }: { message: string; tone?: "success" | "error" }) {
  const [visible, setVisible] = useState(true);
  const [leaving, setLeaving] = useState(false);
  useEffect(() => {
    const leaveTimer = window.setTimeout(() => setLeaving(true), 4600);
    const removeTimer = window.setTimeout(() => setVisible(false), 5000);
    return () => {
      window.clearTimeout(leaveTimer);
      window.clearTimeout(removeTimer);
    };
  }, []);
  const dismiss = () => {
    setLeaving(true);
    window.setTimeout(() => setVisible(false), 240);
  };
  if (!visible) return null;
  return <div className={`toast-notification ${tone} ${leaving ? "is-leaving" : ""}`} role={tone === "error" ? "alert" : "status"} aria-live="polite">
    <Icon name={tone === "error" ? "warning" : "check"} size={18} />
    <span>{message}</span>
    <button type="button" onClick={dismiss} aria-label="Dismiss notification"><Icon name="close" size={15} /></button>
  </div>;
}
