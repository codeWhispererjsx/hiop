import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { Feedback } from "../components/Feedback";
import { endpoints } from "../lib/api";
import type { V3ATopologyStats, V3CStats } from "../lib/types";
import { PageTitle } from "./DashboardPage";
import "../styles/network-performance.css";

export default function NetworkPerformancePage() {
  const [topologyStats, setTopologyStats] = useState<V3ATopologyStats>();
  const [segmentationStats, setSegmentationStats] = useState<V3CStats>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [topoStats, segStats] = await Promise.all([
        endpoints.v3aTopologyStats(),
        endpoints.v3cStats()
      ]);
      setTopologyStats(topoStats);
      setSegmentationStats(segStats);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Performance data could not be loaded.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, []);

  const calculateHealthScore = () => {
    if (!topologyStats || !segmentationStats) return 0;
    
    let score = 100;
    
    // Deduct for stale relationships
    const staleRatio = (topologyStats.stale_relationships || 0) / (topologyStats.topology_relationships || 1);
    score -= staleRatio * 20;
    
    // Deduct for unresolved evidence
    const unresolvedRatio = (topologyStats.unresolved_relationships || 0) / (topologyStats.topology_relationships || 1);
    score -= unresolvedRatio * 15;
    
    // Deduct for unknown VLAN relationships
    const unknownRatio = (segmentationStats.unknown_vlan_relationships || 0) / (segmentationStats.vlans_discovered || 1);
    score -= unknownRatio * 15;
    
    // Deduct for stale VLAN relationships
    const staleVlanRatio = (segmentationStats.stale_vlan_relationships || 0) / (segmentationStats.vlans_discovered || 1);
    score -= staleVlanRatio * 10;
    
    // Bonus for high verification
    const verificationRatio = (topologyStats.relationships_verified || 0) / (topologyStats.topology_relationships || 1);
    score += verificationRatio * 10;
    
    return Math.max(0, Math.min(100, Math.round(score)));
  };

  const getHealthStatus = (score: number) => {
    if (score >= 80) return { status: "Excellent", color: "var(--color-success)" };
    if (score >= 60) return { status: "Good", color: "var(--color-primary)" };
    if (score >= 40) return { status: "Fair", color: "var(--color-warning)" };
    return { status: "Poor", color: "var(--color-danger)" };
  };

  return (
    <DashboardLayout>
      <PageTitle
        eyebrow="Network Intelligence"
        title="Network Performance Dashboard"
        copy="Combined view of topology and segmentation performance metrics"
        action={
          <button
            className="secondary-action"
            onClick={() => void load()}
            disabled={loading}
          >
            Refresh Data
          </button>
        }
      />
      {error && <Feedback error={error} />}
      {loading ? (
        <Feedback loading />
      ) : (
        <div className="network-performance-page">
          {/* Overall Health Score */}
          <section className="health-score-section">
            <div className="health-score-card">
              <h3>Overall Network Health</h3>
              <div className="health-score">
                <span className="score-value">{calculateHealthScore()}</span>
                <span className="score-max">/100</span>
              </div>
              <div className="health-status" style={{ color: getHealthStatus(calculateHealthScore()).color }}>
                {getHealthStatus(calculateHealthScore()).status}
              </div>
            </div>
            <div className="health-indicators">
              <div className="indicator">
                <span className="indicator-label">Coverage</span>
                <span className="indicator-value">
                  {topologyStats?.devices_represented || 0} devices
                </span>
              </div>
              <div className="indicator">
                <span className="indicator-label">Accuracy</span>
                <span className="indicator-value">
                  {topologyStats?.relationships_verified || 0} verified
                </span>
              </div>
              <div className="indicator">
                <span className="indicator-label">Freshness</span>
                <span className="indicator-value">
                  {topologyStats?.data_freshness_minutes || 0}m old
                </span>
              </div>
            </div>
          </section>

          {/* Topology Performance */}
          <section className="performance-section">
            <div className="section-header">
              <h2>Topology Performance</h2>
              <Link className="secondary-action" to="/topology">View Topology</Link>
            </div>
            <div className="metrics-grid">
              <MetricCard
                label="Total Relationships"
                value={topologyStats?.topology_relationships || 0}
                icon="🔗"
                trend="stable"
              />
              <MetricCard
                label="Devices Represented"
                value={topologyStats?.devices_represented || 0}
                icon="🖥️"
                trend="up"
              />
              <MetricCard
                label="Verified Connections"
                value={topologyStats?.relationships_verified || 0}
                icon="✅"
                trend="up"
                highlight
              />
              <MetricCard
                label="Stale Connections"
                value={topologyStats?.stale_relationships || 0}
                icon="⚠️"
                trend="down"
                warning
              />
              <MetricCard
                label="Unresolved Evidence"
                value={topologyStats?.unresolved_relationships || 0}
                icon="❓"
                trend="down"
                warning
              />
              <MetricCard
                label="Network Devices"
                value={topologyStats?.network_devices || 0}
                icon="🔀"
                trend="stable"
              />
              <MetricCard
                label="End Devices"
                value={topologyStats?.end_devices || 0}
                icon="💻"
                trend="up"
              />
              <MetricCard
                label="Avg Confidence"
                value={`${topologyStats?.average_confidence || 0}%`}
                icon="📊"
                trend="up"
              />
              <MetricCard
                label="Active SNMP Polls"
                value={topologyStats?.active_snmp_polls || 0}
                icon="🔄"
                trend="stable"
              />
              <MetricCard
                label="Failed Polls"
                value={topologyStats?.failed_snmp_polls || 0}
                icon="❌"
                trend="down"
                warning
              />
              <MetricCard
                label="Avg Response Time"
                value={`${topologyStats?.average_response_time_ms || 0}ms`}
                icon="⚡"
                trend="stable"
              />
              <MetricCard
                label="Data Freshness"
                value={`${topologyStats?.data_freshness_minutes || 0}m`}
                icon="🕐"
                trend="stable"
              />
            </div>
          </section>

          {/* Segmentation Performance */}
          <section className="performance-section">
            <div className="section-header">
              <h2>Segmentation Performance</h2>
              <Link className="secondary-action" to="/segmentation">View Segmentation</Link>
            </div>
            <div className="metrics-grid">
              <MetricCard
                label="VLANs Discovered"
                value={segmentationStats?.vlans_discovered || 0}
                icon="🏷️"
                trend="up"
              />
              <MetricCard
                label="Subnets Identified"
                value={segmentationStats?.subnets_identified || 0}
                icon="🌐"
                trend="up"
              />
              <MetricCard
                label="Devices with VLAN Info"
                value={segmentationStats?.devices_with_vlan_information || 0}
                icon="🖥️"
                trend="up"
              />
              <MetricCard
                label="Ports with VLAN Info"
                value={segmentationStats?.ports_with_vlan_information || 0}
                icon="🔌"
                trend="up"
              />
              <MetricCard
                label="Trunk Ports"
                value={segmentationStats?.trunk_ports || 0}
                icon="🔀"
                trend="stable"
              />
              <MetricCard
                label="Unknown Endpoints"
                value={segmentationStats?.unknown_vlan_relationships || 0}
                icon="❓"
                trend="down"
                warning
              />
              <MetricCard
                label="Security Zones"
                value={segmentationStats?.security_zones || 0}
                icon="🔒"
                trend="stable"
              />
              <MetricCard
                label="Critical VLANs"
                value={segmentationStats?.critical_vlans || 0}
                icon="🚨"
                trend="stable"
                highlight
              />
              <MetricCard
                label="High Traffic VLANs"
                value={segmentationStats?.high_traffic_vlans || 0}
                icon="📈"
                trend="up"
              />
              <MetricCard
                label="Avg Devices per VLAN"
                value={segmentationStats?.average_devices_per_vlan || 0}
                icon="📊"
                trend="stable"
              />
              <MetricCard
                label="VLAN Coverage"
                value={`${segmentationStats?.vlan_coverage_percentage || 0}%`}
                icon="📏"
                trend="up"
              />
              <MetricCard
                label="Last Scan"
                value={`${segmentationStats?.last_scan_minutes_ago || 0}m ago`}
                icon="🕐"
                trend="stable"
              />
            </div>
          </section>

          {/* Performance Recommendations */}
          <section className="recommendations-section">
            <h2>Performance Recommendations</h2>
            <div className="recommendations">
              {(topologyStats?.stale_relationships ?? 0) > 0 && (
                <div className="recommendation warning">
                  <strong>⚠️ Refresh Stale Connections</strong>
                  <span>{topologyStats?.stale_relationships} topology connections need verification</span>
                </div>
              )}
              {(topologyStats?.unresolved_relationships ?? 0) > 0 && (
                <div className="recommendation warning">
                  <strong>⚠️ Investigate Unresolved Evidence</strong>
                  <span>{topologyStats?.unresolved_relationships} connections lack sufficient evidence</span>
                </div>
              )}
              {(segmentationStats?.unknown_vlan_relationships ?? 0) > 0 && (
                <div className="recommendation warning">
                  <strong>⚠️ Identify Unknown Endpoints</strong>
                  <span>{segmentationStats?.unknown_vlan_relationships} devices lack VLAN assignments</span>
                </div>
              )}
              {(topologyStats?.failed_snmp_polls ?? 0) > 0 && (
                <div className="recommendation error">
                  <strong>❌ Fix Failed SNMP Polls</strong>
                  <span>{topologyStats?.failed_snmp_polls} SNMP targets are not responding</span>
                </div>
              )}
              {(!topologyStats?.stale_relationships && !topologyStats?.unresolved_relationships && 
                !segmentationStats?.unknown_vlan_relationships && !topologyStats?.failed_snmp_polls) && (
                <div className="recommendation success">
                  <strong>✅ Network Performance Optimal</strong>
                  <span>All metrics are within acceptable ranges</span>
                </div>
              )}
            </div>
          </section>
        </div>
      )}
    </DashboardLayout>
  );
}

function MetricCard({ 
  label, 
  value, 
  icon, 
  trend, 
  highlight = false, 
  warning = false 
}: { 
  label: string; 
  value: string | number; 
  icon: string; 
  trend: string; 
  highlight?: boolean; 
  warning?: boolean; 
}) {
  return (
    <div className={`metric-card ${highlight ? 'highlight' : ''} ${warning ? 'warning' : ''}`}>
      <div className="metric-icon">{icon}</div>
      <div className="metric-content">
        <span className="metric-label">{label}</span>
        <span className="metric-value">{value}</span>
        <span className={`metric-trend ${trend}`}>
          {trend === 'up' ? '↑' : trend === 'down' ? '↓' : '→'}
        </span>
      </div>
    </div>
  );
}
