import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { Feedback } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { StatusBadge } from "../components/StatusBadge";
import { endpoints, getPaginatedItems } from "../lib/api";
import type { MonitoringSummary } from "../lib/types";
import { PageTitle } from "./DashboardPage";
import "../styles/network-performance.css";

export default function NetworkPerformancePage() {
  const [summary, setSummary] = useState<MonitoringSummary>();
  const [deviceNames, setDeviceNames] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [monitoring, devices] = await Promise.all([
        endpoints.monitoringSummary("24h"),
        endpoints.devices(),
      ]);
      setSummary(monitoring);
      setDeviceNames(
        Object.fromEntries(
          getPaginatedItems(devices).map((device) => [device.id, device.hostname]),
        ),
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Monitoring data could not be loaded.",
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <DashboardLayout>
      <PageTitle
        eyebrow="Monitor · device health"
        title="Network performance"
        copy="Review device availability, latency, and monitoring evidence from the last 24 hours."
        action={
          <button
            className="secondary-action"
            onClick={() => void load()}
            disabled={loading}
          >
            {loading ? "Refreshing…" : "Refresh data"}
          </button>
        }
      />
      {error ? (
        <Feedback error={error} onRetry={() => void load()} />
      ) : loading && !summary ? (
        <Feedback
          loading
          loadingTitle="Loading network performance"
          loadingMessage="Retrieving current device health and availability."
        />
      ) : summary ? (
        <main className="network-performance-page">
          <section className="performance-overview" aria-label="Device health summary">
            <SummaryCard label="Monitored devices" value={summary.monitored} />
            <SummaryCard label="Online" value={summary.online} tone="success" />
            <SummaryCard
              label="Offline"
              value={summary.offline}
              tone={summary.offline ? "danger" : "success"}
            />
            <SummaryCard
              label="Degraded or unhealthy"
              value={summary.degraded + summary.unhealthy}
              tone={summary.degraded + summary.unhealthy ? "warning" : "success"}
            />
          </section>
          <section className="performance-section wide">
            <header>
              <div>
                <h2>Device health</h2>
                <p>Availability and latency observations for the last 24 hours.</p>
              </div>
              <Link to="/devices">
                View inventory <Icon name="arrow" size={15} />
              </Link>
            </header>
            {summary.devices.length === 0 ? (
              <p>No monitored devices are available yet.</p>
            ) : (
              <div className="port-table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Device</th>
                      <th>Health</th>
                      <th>Availability</th>
                      <th>Latency</th>
                      <th>Packet loss</th>
                      <th>Last check</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.devices.map((device) => (
                      <tr key={device.device_id}>
                        <td>
                          <Link to={`/devices/${device.device_id}`}>
                            {deviceNames[device.device_id] || device.device_id}
                          </Link>
                        </td>
                        <td>
                          <StatusBadge status={device.health} />
                        </td>
                        <td>
                          {device.availability_percent == null
                            ? "Not enough data"
                            : `${device.availability_percent}%`}
                        </td>
                        <td>
                          {device.latency?.current == null
                            ? "Unavailable"
                            : `${device.latency.current} ms`}
                        </td>
                        <td>
                          {device.packet_loss_percent == null
                            ? "Not enough data"
                            : `${device.packet_loss_percent}%`}
                        </td>
                        <td>
                          {device.last_check
                            ? new Date(device.last_check).toLocaleString()
                            : "Never"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </main>
      ) : null}
    </DashboardLayout>
  );
}

function SummaryCard({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: number;
  tone?: "neutral" | "success" | "warning" | "danger";
}) {
  return (
    <article className={`performance-summary-card ${tone}`}>
      <Icon name={tone === "danger" ? "warning" : "devices"} size={20} />
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
    </article>
  );
}
