import type { CSSProperties } from "react";

type Point = { label: string; value: number | null; lower?: number; upper?: number; quality?: string };
const PALETTE = ["#c29f04", "#39d39f", "#e15567", "#5e93cc", "#9d79d6", "#7f8f89"];

function geometry(points: Point[], width = 720, height = 240) {
  const values = points.flatMap((point) => [point.value, point.lower, point.upper]).filter((value): value is number => value !== null && value !== undefined && Number.isFinite(value));
  const minimum = Math.min(0, ...values); const maximum = Math.max(1, ...values); const range = maximum - minimum || 1;
  const x = (index: number) => points.length < 2 ? width / 2 : 18 + index / (points.length - 1) * (width - 36);
  const y = (value: number) => height - 22 - (value - minimum) / range * (height - 44);
  return { x, y, minimum, maximum };
}

export function AnalyticsLineChart({ title, points, area = false, confidence = false, unit = "" }: {title:string;points:Point[];area?:boolean;confidence?:boolean;unit?:string}) {
  const usable = points.filter((point) => point.value !== null);
  if (!usable.length) return <ChartEmpty title={title}/>;
  const { x, y, minimum, maximum } = geometry(points);
  const line = points.map((point, index) => point.value === null ? null : `${x(index)},${y(point.value)}`).filter(Boolean).join(" ");
  const upper = confidence ? points.map((point, index) => point.upper === undefined ? null : `${x(index)},${y(point.upper)}`).filter(Boolean) : [];
  const lower = confidence ? points.map((point, index) => point.lower === undefined ? null : `${x(index)},${y(point.lower)}`).filter(Boolean).reverse() : [];
  const gradientId = `analytics-${title.replaceAll(/[^a-z0-9]/gi, "-")}`;
  return <article className="analytics-chart-card">
    <header><div><h3>{title}</h3><span>{usable.length} backend samples · {minimum.toFixed(1)}–{maximum.toFixed(1)} {unit}</span></div></header>
    <svg viewBox="0 0 720 240" role="img" aria-label={`${title}. ${usable.length} points from ${usable[0].label} to ${usable[usable.length-1].label}.`}>
      <defs><linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#c29f04" stopOpacity=".28"/><stop offset="1" stopColor="#c29f04" stopOpacity="0"/></linearGradient></defs>
      {[.25,.5,.75].map(level=><line key={level} className="analytics-gridline" x1="18" x2="702" y1={level*220} y2={level*220}/>)}
      {confidence&&upper.length>1&&<polygon className="analytics-confidence" points={[...upper,...lower].join(" ")}/>}
      {area&&<polygon fill={`url(#${gradientId})`} points={`18,218 ${line} 702,218`}/>}
      <polyline className="analytics-line" points={line}/>
      {points.map((point,index)=>point.value===null?null:<circle key={`${point.label}-${index}`} className={point.quality&&point.quality!=="good"?"quality-warning":""} cx={x(index)} cy={y(point.value)} r="3"><title>{point.label}: {point.value.toFixed(2)} {unit} ({point.quality??"forecast"})</title></circle>)}
    </svg>
    <div className="analytics-axis"><span>{usable[0].label}</span><span>{usable[usable.length-1].label}</span></div>
    <details className="chart-accessible-summary"><summary>View chart data</summary><table><thead><tr><th>Period</th><th>Value</th><th>Quality</th></tr></thead><tbody>{usable.slice(-30).map((point,index)=><tr key={`${point.label}-${index}`}><td>{point.label}</td><td>{point.value?.toFixed(2)} {unit}</td><td>{point.quality??"Projected"}</td></tr>)}</tbody></table></details>
  </article>;
}

export function AnalyticsBarChart({ title, items, unit = "" }: {title:string;items:Array<{label:string;value:number}>;unit?:string}) {
  const max = Math.max(1,...items.map(item=>item.value));
  return <article className="analytics-chart-card"><header><div><h3>{title}</h3><span>{items.length} groups</span></div></header>{items.length?<div className="analytics-bars" role="img" aria-label={`${title}: ${items.map(item=>`${item.label} ${item.value}`).join(", ")}`}>{items.slice(0,10).map((item,index)=><div key={item.label}><span>{item.label}</span><i><b style={{width:`${item.value/max*100}%`,background:PALETTE[index%PALETTE.length]}}/></i><strong>{item.value.toFixed(item.value%1?1:0)}{unit}</strong></div>)}</div>:<ChartEmpty title={title}/>}</article>;
}

export function AnalyticsDonut({ title, items, center }: {title:string;items:Array<{label:string;value:number}>;center:string}) {
  const total=items.reduce((sum,item)=>sum+item.value,0);
  const segments=items.reduce<{cursor:number;parts:string[]}>((result,item,index)=>{const start=total?result.cursor/total*100:0;const cursor=result.cursor+item.value;const end=total?cursor/total*100:0;return {cursor,parts:[...result.parts,`${PALETTE[index%PALETTE.length]} ${start}% ${end}%`]};},{cursor:0,parts:[]}).parts.join(",");
  return <article className="analytics-chart-card"><header><div><h3>{title}</h3><span>{total} records</span></div></header>{total?<div className="analytics-donut-layout" role="img" aria-label={`${title}: ${items.map(item=>`${item.label} ${item.value}`).join(", ")}`}><div className="analytics-donut" style={{"--analytics-segments":`conic-gradient(${segments})`} as CSSProperties}><strong>{center}</strong><span>Total</span></div><div className="analytics-legend">{items.map((item,index)=><div key={item.label}><i style={{background:PALETTE[index%PALETTE.length]}}/><span>{item.label}</span><b>{item.value}</b></div>)}</div></div>:<ChartEmpty title={title}/>}</article>;
}

export function AnalyticsHeatmap({ title, items }: {title:string;items:Array<{label:string;value:number}>}) {
  const max=Math.max(1,...items.map(item=>item.value));
  return <article className="analytics-chart-card"><header><div><h3>{title}</h3><span>Intensity reflects backend values</span></div></header>{items.length?<div className="analytics-heatmap" role="img" aria-label={`${title}: ${items.map(item=>`${item.label} ${item.value}`).join(", ")}`}>{items.slice(0,24).map(item=><div key={item.label} style={{"--heat":Math.max(.1,item.value/max)} as CSSProperties}><strong>{item.value.toFixed(1)}</strong><span>{item.label}</span></div>)}</div>:<ChartEmpty title={title}/>}</article>;
}

function ChartEmpty({title}:{title:string}) { return <div className="analytics-chart-empty"><strong>No data for {title}</strong><span>Adjust filters or wait for analytics processing.</span></div>; }
