import type { CSSProperties } from "react";

const COLORS = ["#C29F04", "#39d39f", "#e15567", "#5e93cc", "#9d79d6", "#7f8f89"];

export function DistributionChart({ title, data }: { title: string; data: Array<{ name: string; value?: number }> }) {
  const total = data.reduce((sum, item) => sum + (item.value ?? 0), 0);
  const gradient = data.map((item, index) => {
    const start = total ? data.slice(0, index).reduce((sum, entry) => sum + (entry.value ?? 0), 0) / total * 100 : 0;
    const end = total ? start + ((item.value ?? 0) / total) * 100 : 0;
    return `${COLORS[index % COLORS.length]} ${start}% ${end}%`;
  }).join(",");
  return <article className="report-chart-card"><header><h3>{title}</h3><span>{total} records</span></header>{data.length ? <div className="report-donut-layout"><div className="report-donut" style={{ "--segments": `conic-gradient(${gradient})` } as CSSProperties}><strong>{total}</strong><span>Total</span></div><div className="report-chart-legend">{data.map((item, index) => <div key={item.name}><i style={{ background: COLORS[index % COLORS.length] }} /><span>{item.name}</span><b>{item.value ?? 0}</b></div>)}</div></div> : <p className="report-chart-empty">No chart data in this period.</p>}</article>;
}

export function BarChart({ title, data }: { title: string; data: Array<{ name: string; value?: number }> }) {
  const max = Math.max(1, ...data.map((item) => item.value ?? 0));
  return <article className="report-chart-card"><header><h3>{title}</h3><span>{data.length} groups</span></header>{data.length ? <div className="report-bars">{data.slice(0, 8).map((item) => <div key={item.name}><span title={item.name}>{item.name}</span><i><b style={{ width: `${((item.value ?? 0) / max) * 100}%` }} /></i><strong>{item.value ?? 0}</strong></div>)}</div> : <p className="report-chart-empty">No chart data in this period.</p>}</article>;
}

export function TrendChart({ title, data }: { title: string; data: Array<{ name: string; value?: number; total?: number }> }) {
  const values = data.map((item) => item.total ?? item.value ?? 0); const max = Math.max(1, ...values); const width = 500; const height = 150;
  const points = values.map((value, index) => `${data.length === 1 ? width / 2 : (index / (data.length - 1)) * width},${height - (value / max) * (height - 16) - 8}`).join(" ");
  return <article className="report-chart-card report-trend-card"><header><h3>{title}</h3><span>{data.length} days</span></header>{data.length ? <><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${title} trend`}><defs><linearGradient id={`trend-${title.replaceAll(" ", "-")}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#C29F04" stopOpacity=".28"/><stop offset="1" stopColor="#C29F04" stopOpacity="0"/></linearGradient></defs><polyline className="report-trend-line" points={points}/></svg><div className="report-trend-axis"><span>{data[0]?.name}</span><span>{data[data.length - 1]?.name}</span></div></> : <p className="report-chart-empty">Historical data is unavailable for this period.</p>}</article>;
}
