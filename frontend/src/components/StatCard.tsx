import { Icon, type IconName } from "./Icon";

export function StatCard({ label, value, detail, icon, tone = "neutral", trend }: { label: string; value: number | string; detail: string; icon: IconName; tone?: "neutral" | "success" | "danger" | "warning"; trend?: string }) {
  return <article className={`stat-card tone-${tone}`}>
    <div className="stat-card-head"><span>{label}</span><span className="stat-icon"><Icon name={icon} size={19}/></span></div>
    <div className="stat-value-row"><strong>{value}</strong>{trend && <span className="trend">{trend}</span>}</div>
    <p>{detail}</p>
  </article>;
}

