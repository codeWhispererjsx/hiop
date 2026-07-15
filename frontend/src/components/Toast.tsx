import { useEffect, useState } from "react";
import { Icon } from "./Icon";

export function Toast({ message, tone = "success" }: { message: string; tone?: "success" | "error" }) {
  const [visible, setVisible] = useState(true);
  useEffect(() => {
    const timer = window.setTimeout(() => setVisible(false), 5000);
    return () => window.clearTimeout(timer);
  }, []);
  if (!visible) return null;
  return <div className={`toast-notification ${tone}`} role={tone === "error" ? "alert" : "status"}>
    <Icon name={tone === "error" ? "warning" : "check"} size={18} />
    <span>{message}</span>
    <button type="button" onClick={() => setVisible(false)} aria-label="Dismiss notification"><Icon name="close" size={15} /></button>
  </div>;
}
