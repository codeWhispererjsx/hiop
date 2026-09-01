import { useEffect, useMemo, useState, type CSSProperties, type ReactNode } from "react";
import { Link } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { Feedback } from "../components/Feedback";
import { Icon, type IconName } from "../components/Icon";
import { StatusBadge } from "../components/StatusBadge";
import { endpoints } from "../lib/api";
import type { V3ATopologyStats, V3CStats } from "../lib/types";
import { PageTitle } from "./DashboardPage";
import "../styles/network-performance.css";

export default function NetworkPerformancePage() {
  const [topology, setTopology] = useState<V3ATopologyStats>();
  const [segmentation, setSegmentation] = useState<V3CStats>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [updatedAt, setUpdatedAt] = useState<Date>();
  const load = async () => {
    setLoading(true); setError("");
    try {
      const [topologyData, segmentationData] = await Promise.all([endpoints.v3aTopologyStats(), endpoints.v3cStats()]);
      setTopology(topologyData); setSegmentation(segmentationData); setUpdatedAt(new Date());
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Performance data could not be loaded."); }
    finally { setLoading(false); }
  };
  useEffect(() => { const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer); }, []);
  const score = useMemo(() => healthScore(topology, segmentation), [topology, segmentation]);
  const health = healthState(score);
  const issues = (topology?.stale_relationships ?? 0) + (topology?.unresolved_relationships ?? 0) + (topology?.failed_snmp_polls ?? 0) + (segmentation?.unknown_vlan_relationships ?? 0);

  return <DashboardLayout>
    <PageTitle eyebrow="Monitor · network intelligence" title="Network performance" copy="Assess topology coverage, connection quality, VLAN visibility, and evidence that needs attention." action={<button className="secondary-action" onClick={() => void load()} disabled={loading}>{loading ? "Refreshing…" : "Refresh data"}</button>} />
    {error ? <Feedback error={error} onRetry={() => void load()} /> : loading && !topology ? <Feedback loading loadingTitle="Loading network performance" loadingMessage="Retrieving current topology and segmentation evidence." /> : topology && segmentation ? <main className="network-performance-page">
      <section className="performance-health" aria-labelledby="network-health-title">
        <div className={`performance-health-score ${health.tone}`}>
          <div className="performance-score-ring" style={{ "--score": `${score}%` } as CSSProperties}><strong>{score}</strong><span>/100</span></div>
          <div><span className="eyebrow">Current assessment</span><h2 id="network-health-title">{health.label} network evidence</h2><p>This explainable score reflects verified, stale, unresolved, and unknown relationships—not device availability.</p></div>
        </div>
        <div className="performance-health-context"><StatusBadge status={health.badge} /><p><Icon name="clock" size={16} /> Updated {updatedAt?.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) ?? "just now"}</p><small>Data freshness: {formatMinutes(topology.data_freshness_minutes)}</small></div>
      </section>

      <section className="performance-overview" aria-label="Network performance summary">
        <SummaryCard icon="devices" label="Devices represented" value={topology.devices_represented} detail={`${topology.network_devices ?? 0} network · ${topology.end_devices ?? 0} endpoints`} />
        <SummaryCard icon="network" label="Verified connections" value={topology.relationships_verified} detail={`${topology.topology_relationships} total relationships`} />
        <SummaryCard icon="chart" label="VLAN coverage" value={`${segmentation.vlan_coverage_percentage ?? 0}%`} detail={`${segmentation.devices_with_vlan_information} devices mapped`} />
        <SummaryCard icon="warning" label="Requires attention" value={issues} detail="Stale, unresolved, unknown, or failed" tone={issues ? "warning" : "success"} />
      </section>

      <div className="performance-workspace">
        <PerformanceSection title="Topology evidence" copy="Confidence and quality of known network connections." action="Open topology" to="/topology">
          <MetricRows rows={[["Total relationships", topology.topology_relationships, "All observed links"], ["Verified", topology.relationships_verified, "Supported by current evidence", "success"], ["Average confidence", `${topology.average_confidence ?? 0}%`, "Across known relationships"], ["Stale", topology.stale_relationships, "Evidence requires refreshing", topology.stale_relationships ? "warning" : "neutral"], ["Unresolved", topology.unresolved_relationships, "Insufficient evidence", topology.unresolved_relationships ? "warning" : "neutral"], ["Duplicate", topology.duplicate_relationships, "Requires reconciliation", topology.duplicate_relationships ? "warning" : "neutral"]]} />
        </PerformanceSection>
        <PerformanceSection title="Polling health" copy="Current SNMP collection activity and responsiveness." action="Open SNMP" to="/snmp">
          <MetricRows rows={[["Active polls", topology.active_snmp_polls ?? 0, "Targets currently collected"], ["Failed polls", topology.failed_snmp_polls ?? 0, "Targets not responding", topology.failed_snmp_polls ? "danger" : "success"], ["Average response", `${topology.average_response_time_ms ?? 0} ms`, "Observed poll response time"], ["Evidence freshness", formatMinutes(topology.data_freshness_minutes), "Age of latest topology data"]]} />
        </PerformanceSection>
        <PerformanceSection title="Segmentation visibility" copy="VLAN, subnet, and port context available to technicians." action="Open segmentation" to="/segmentation" wide>
          <MetricRows rows={[["VLANs discovered", segmentation.vlans_discovered, `${segmentation.critical_vlans ?? 0} marked critical`], ["Subnets identified", segmentation.subnets_identified, "Known networks"], ["Ports mapped", segmentation.ports_with_vlan_information, `${segmentation.trunk_ports} trunk ports`], ["Devices mapped", segmentation.devices_with_vlan_information, `${segmentation.average_devices_per_vlan ?? 0} average per VLAN`], ["Unknown endpoints", segmentation.unknown_vlan_relationships, "No confirmed VLAN", segmentation.unknown_vlan_relationships ? "warning" : "success"], ["Stale mappings", segmentation.stale_vlan_relationships, "Evidence requires refresh", segmentation.stale_vlan_relationships ? "warning" : "neutral"]]} />
        </PerformanceSection>
      </div>
      <AttentionPanel topology={topology} segmentation={segmentation} />
    </main> : null}
  </DashboardLayout>;
}

type Tone = "neutral" | "success" | "warning" | "danger";
type MetricRow = [string, string | number, string, Tone?];
function SummaryCard({ icon, label, value, detail, tone = "neutral" }: { icon: IconName; label: string; value: string | number; detail: string; tone?: Tone }) { return <article className={`performance-summary-card ${tone}`}><Icon name={icon} size={20} /><div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div></article>; }
function PerformanceSection({ title, copy, action, to, wide, children }: { title: string; copy: string; action: string; to: string; wide?: boolean; children: ReactNode }) { return <section className={`performance-section ${wide ? "wide" : ""}`}><header><div><h2>{title}</h2><p>{copy}</p></div><Link to={to}>{action}<Icon name="arrow" size={15} /></Link></header>{children}</section>; }
function MetricRows({ rows }: { rows: MetricRow[] }) { return <dl className="performance-metric-rows">{rows.map(([label, value, detail, tone = "neutral"]) => <div key={label} className={tone}><dt><span>{label}</span><small>{detail}</small></dt><dd>{value}</dd></div>)}</dl>; }
function AttentionPanel({ topology, segmentation }: { topology: V3ATopologyStats; segmentation: V3CStats }) {
  const items = [topology.failed_snmp_polls ? ["Failed SNMP polls", `${topology.failed_snmp_polls} targets are not responding.`, "/snmp", "Review targets", "danger"] : null, topology.stale_relationships ? ["Stale topology evidence", `${topology.stale_relationships} relationships require verification.`, "/topology", "Review topology", "warning"] : null, topology.unresolved_relationships ? ["Unresolved connections", `${topology.unresolved_relationships} relationships lack sufficient evidence.`, "/topology", "Investigate", "warning"] : null, segmentation.unknown_vlan_relationships ? ["Unknown VLAN assignments", `${segmentation.unknown_vlan_relationships} endpoints have no confirmed VLAN.`, "/segmentation", "Review segmentation", "warning"] : null].filter(Boolean) as string[][];
  return <section className="performance-attention"><header><div><span className="eyebrow">Operational follow-up</span><h2>{items.length ? "Items requiring attention" : "No immediate evidence issues"}</h2></div><StatusBadge status={items.length ? "Attention" : "Healthy"} /></header>{items.length ? <div className="performance-attention-list">{items.map(([title, detail, to, action, tone]) => <article key={title} className={tone}><Icon name={tone === "danger" ? "alerts" : "warning"} /><div><strong>{title}</strong><span>{detail}</span></div><Link to={to}>{action}</Link></article>)}</div> : <p className="performance-clear"><Icon name="check" /> Current topology, polling, and segmentation evidence is within configured expectations.</p>}</section>;
}
function healthScore(topology?: V3ATopologyStats, segmentation?: V3CStats) { if (!topology || !segmentation) return 0; const relationships = Math.max(topology.topology_relationships, 1); const vlans = Math.max(segmentation.vlans_discovered, 1); const score = 100 - topology.stale_relationships / relationships * 20 - topology.unresolved_relationships / relationships * 15 - segmentation.unknown_vlan_relationships / vlans * 15 - segmentation.stale_vlan_relationships / vlans * 10 + topology.relationships_verified / relationships * 10; return Math.max(0, Math.min(100, Math.round(score))); }
function healthState(score: number) { if (score >= 80) return { label: "Strong", badge: "Healthy", tone: "success" }; if (score >= 60) return { label: "Stable", badge: "Operational", tone: "info" }; if (score >= 40) return { label: "Limited", badge: "Attention", tone: "warning" }; return { label: "Weak", badge: "Critical", tone: "danger" }; }
function formatMinutes(value?: number) { if (value === undefined || value === null) return "Not available"; if (value < 60) return `${value} min`; return `${Math.floor(value / 60)}h ${value % 60}m`; }
