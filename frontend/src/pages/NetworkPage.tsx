import { formatDateTime } from "../lib/dateTime";
import { useCallback, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { PageTitle } from "./DashboardPage";
import { Icon } from "../components/Icon";
import { Feedback } from "../components/Feedback";
import { StatCard } from "../components/StatCard";
import { StatusBadge } from "../components/StatusBadge";
import { endpoints, getPaginatedItems } from "../lib/api";
import { useRequest } from "../hooks/useRequest";
import type { Alert, Device, LiveEvent, MonitoringSummary, Scan } from "../lib/types";

type ScanState = "idle" | "running" | "completed" | "failed";

const formatDate = (value?: string | null) => value ? formatDateTime(value) : "Never";
const latency = (value?: number | null) => value == null ? "No response" : `${Math.round(value * 100) / 100} ms`;

export default function NetworkPage() {
  const navigate = useNavigate();
  const devices = useRequest(endpoints.devices, []);
  const scans = useRequest(() => endpoints.scanHistory(100), []);
  const alerts = useRequest(endpoints.alerts, []);
  const [window, setWindow] = useState("24h");
  const health = useRequest(() => endpoints.monitoringSummary(window), [window]);
  
  const reloadDevices = devices.reload;
  const reloadScans = scans.reload;
  const reloadAlerts = alerts.reload;
  const reloadHealth = health.reload;
  
  const [scanState, setScanState] = useState<ScanState>("idle");
  const [scanningDevice, setScanningDevice] = useState("");
  const [message, setMessage] = useState("");
  const [socketConnected, setSocketConnected] = useState<boolean | null>(null);

  const refresh = useCallback(async () => {
    await Promise.all([reloadDevices(), reloadScans(), reloadAlerts(), reloadHealth()]);
  }, [reloadDevices, reloadScans, reloadAlerts, reloadHealth]);

  const live = useCallback((event: LiveEvent) => {
    if (event.event === "device_status_changed") {
      setMessage(`${event.hostname ?? "A device"} changed to ${event.current_status ?? "an unknown state"}.`);
      void refresh();
    }
  }, [refresh]);

  const runScan = async (device?: Device) => {
    setMessage("");
    setScanState("running");
    setScanningDevice(device?.id ?? "all");
    try {
      if (device) {
        const result = await endpoints.scanDevice(device.id);
        if ("queued" in result && result.queued) {
          setMessage(`${device.hostname} monitoring check was sent to the local agent. Refresh the view in a few seconds for the result.`);
        } else {
          setMessage(`${device.hostname} scan completed: ${result.status}, ${latency(result.response_time)}.`);
        }
      } else {
        const result = await endpoints.scanAll();
        if (result.queued) {
          setMessage(`Monitoring checks sent to the local agent for ${result.queued} of ${result.total_devices} devices. Results will appear as the agent reports back.`);
        } else {
          setMessage(`Scan completed for ${result.total_devices} devices: ${result.online} online, ${result.offline} offline.`);
        }
      }
      setScanState("completed");
      await refresh();
    } catch (error) {
      setScanState("failed");
      setMessage(error instanceof Error ? error.message : "The scan request failed.");
    } finally {
      setScanningDevice("");
    }
  };

  const latestByDevice = useMemo(() => {
    const latest = new Map<string, Scan>();
    for (const scan of getPaginatedItems(scans.data)) if (!latest.has(scan.device_id)) latest.set(scan.device_id, scan);
    return latest;
  }, [scans.data]);
  
  const devicesList = useMemo(() => getPaginatedItems(devices.data), [devices.data]);
  
  const activeDevices = devicesList.filter((device) => device.inventory_status !== "Retired");
  
  const averageResponse = useMemo(() => {
    const values = activeDevices
      .map((device) => latestByDevice.get(device.id)?.response_time)
      .filter((value): value is number => value != null);
    return values.length ? values.reduce((total, value) => total + value, 0) / values.length : null;
  }, [activeDevices, latestByDevice]);
  
  const lastScan = scans.data?.[0]?.scanned_at ?? null;
  const activeAlerts = getPaginatedItems(alerts.data).filter((alert) => !alert.acknowledged);
  const running = scanState === "running";
  const initialLoading = devices.loading || scans.loading || alerts.loading || health.loading;
  const initialError = devices.error || scans.error || alerts.error || health.error;

  return (
    <DashboardLayout onLiveEvent={live} onLiveStateChange={setSocketConnected}>
      <nav className="page-actions" aria-label="Monitoring workspaces">
        <Link className="secondary-action" to="/alerts">Alerts</Link>
        <Link className="secondary-action" to="/topology">Topology</Link>
        <Link className="secondary-action" to="/segmentation">Segments</Link>
      </nav>
      
      <PageTitle
        eyebrow="Advanced monitoring"
        title="Device health intelligence"
        copy="Historical, explainable health from the local agent and supported SNMP evidence."
        action={
          <div className="noc-actions">
            <select
              aria-label="Monitoring time window"
              value={window}
              onChange={(event) => setWindow(event.target.value)}
            >
              <option value="1h">Last hour</option>
              <option value="24h">Last 24 hours</option>
              <option value="7d">Last 7 days</option>
              <option value="30d">Last 30 days</option>
            </select>
            <button
              className="secondary-action"
              disabled={running}
              onClick={() => void refresh()}
              aria-label="Refresh monitoring view"
            >
              <Icon name="network" aria-hidden="true" />
              Refresh view
            </button>
            <button
              className="primary-action"
              disabled={running || !activeDevices.length}
              onClick={() => void runScan()}
              aria-label={running && scanningDevice === "all" ? "Monitoring all devices" : "Refresh monitoring"}
              aria-busy={running && scanningDevice === "all"}
            >
              <Icon name="wifi" aria-hidden="true" />
              {running && scanningDevice === "all" ? "Monitoring…" : "Refresh monitoring"}
            </button>
          </div>
        }
      />
      
      {socketConnected === false && (
        <div className="noc-connection-error" role="alert" aria-live="polite">
          <Icon name="warning" aria-hidden="true" />
          <div>
            <strong>Live connection interrupted</strong>
            <span>Status changes may be delayed. HIOP is reconnecting automatically.</span>
          </div>
        </div>
      )}
      
      {message && (
        <div
          className={`inline-notice ${scanState === "failed" ? "notice-error" : ""}`}
          role={scanState === "failed" ? "alert" : "status"}
          aria-live="polite"
        >
          {message}
        </div>
      )}
      
      {scanState !== "idle" && <ScanProgress state={scanState} />}

      {initialLoading || initialError ? (
        <Feedback loading={initialLoading} error={initialError} onRetry={refresh} />
      ) : (
        <>
          <section className="noc-summary" aria-label="Network monitoring statistics">
            <StatCard
              label="Monitored devices"
              value={health.data?.monitored ?? 0}
              detail="Devices with observations in this window"
              icon="devices"
              trend={window}
            />
            <StatCard
              label="Online"
              value={health.data?.online ?? 0}
              detail="Last local check got a response"
              icon="check"
              tone="success"
              trend="Current"
            />
            <StatCard
              label="Offline"
              value={health.data?.offline ?? 0}
              detail="Last local check got no response"
              icon="warning"
              tone="danger"
              trend="Current"
            />
            <StatCard
              label="Degraded"
              value={health.data?.degraded ?? 0}
              detail="Latency or missed-check evidence"
              icon="network"
              tone="warning"
              trend="Health"
            />
            <StatCard
              label="Unknown"
              value={health.data?.unknown ?? 0}
              detail="Insufficient monitoring evidence"
              icon="wifi"
              tone="warning"
              trend="Evidence"
            />
            <StatCard
              label="Last scan time"
              value={lastScan ? new Date(lastScan).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "Never"}
              detail={formatDate(lastScan)}
              icon="clock"
              trend="Latest"
            />
            <StatCard
              label="Average response"
              value={averageResponse == null ? "—" : latency(averageResponse)}
              detail="Latest responsive device checks"
              icon="network"
              trend="Latency"
            />
            <StatCard
              label="Active alerts"
              value={activeAlerts.length}
              detail="Unacknowledged network events"
              icon="alerts"
              tone={activeAlerts.length ? "danger" : "success"}
              trend="Attention"
            />
          </section>

          <HealthEvidence
            summary={health.data}
            devices={devicesList}
            onOpen={(id) => navigate(`/devices/${id}`)}
          />

          <section className="panel noc-device-panel">
            <header className="section-head">
              <div>
                <h2>Network devices</h2>
                <p>Current inventory state joined with each device's latest local check.</p>
              </div>
              <span className={`live-pill ${socketConnected ? "connected" : ""}`}>
                {socketConnected ? "Live updates" : "Reconnecting"}
              </span>
            </header>
            {!devicesList.length ? (
              <Feedback
                emptyTitle="No network devices"
                empty="Add a device with an IP address before running network checks."
              />
            ) : (
              <NetworkDeviceTable
                devices={devicesList}
                latest={latestByDevice}
                busy={running}
                scanningDevice={scanningDevice}
                onOpen={(id) => navigate(`/devices/${id}`)}
                onScan={runScan}
              />
            )}
          </section>

          <section className="noc-lower-grid">
            <section className="panel">
              <header className="section-head">
                <div>
                  <h2>Recent scan history</h2>
                  <p>Latest results reported by local monitoring.</p>
                </div>
              </header>
              {scans.error || !scans.data?.length ? (
                <Feedback
                  error={scans.error}
                  empty="No scan history has been recorded."
                  onRetry={reloadScans}
                />
              ) : (
                <div className="noc-history-list">
                  {scans.data.slice(0, 12).map((scan) => {
                    const device = devicesList.find((item) => item.id === scan.device_id);
                    return (
                      <button
                        key={scan.id}
                        onClick={() => navigate(`/devices/${scan.device_id}`)}
                        aria-label={`View device ${device?.hostname ?? scan.ip_address}`}
                      >
                        <span className={`pulse ${scan.status.toLowerCase()}`} aria-hidden="true" />
                        <span>
                          <strong>{device?.hostname ?? scan.ip_address}</strong>
                          <small>{formatDate(scan.scanned_at)}</small>
                        </span>
                        <StatusBadge status={scan.status} />
                        <span>{latency(scan.response_time)}</span>
                      </button>
                    );
                  })}
                </div>
              )}
            </section>
            
            <section className="panel">
              <header className="section-head">
                <div>
                  <h2>Recent network alerts</h2>
                  <p>Status changes requiring operational awareness.</p>
                </div>
              </header>
              {alerts.error || !alerts.data?.length ? (
                <Feedback
                  error={alerts.error}
                  empty="No network alerts have been recorded."
                  onRetry={reloadAlerts}
                />
              ) : (
                <div className="noc-alert-list">
                  {alerts.data.slice(0, 8).map((alert) => (
                    <AlertRow
                      key={alert.id}
                      alert={alert}
                      device={devicesList.find((item) => item.id === alert.device_id)}
                      onOpen={() => navigate(`/devices/${alert.device_id}`)}
                    />
                  ))}
                </div>
              )}
            </section>
          </section>
        </>
      )}
    </DashboardLayout>
  );
}

function HealthEvidence({
  summary,
  devices,
  onOpen,
}: {
  summary: MonitoringSummary | null;
  devices: Device[];
  onOpen: (id: string) => void;
}) {
  const names = new Map(devices.map((device) => [device.id, device.hostname]));
  
  return (
    <section className="panel">
      <header className="section-head">
        <div>
          <h2>Explainable device health</h2>
          <p>Availability, latency and missed-check rate are calculated from saved local checks.</p>
        </div>
      </header>
      {!summary?.devices.length ? (
        <Feedback empty="No monitoring evidence exists for this time window." />
      ) : (
        <div className="noc-history-list">
          {summary.devices.map((item) => (
            <button
              key={item.device_id}
              onClick={() => onOpen(item.device_id)}
              aria-label={`View device ${names.get(item.device_id) ?? "Known device"}`}
            >
              <span className={`pulse ${item.status.toLowerCase()}`} aria-hidden="true" />
              <span>
                <strong>{names.get(item.device_id) ?? "Known device"}</strong>
                <small>{item.reasons.join(" · ")}</small>
              </span>
              <StatusBadge status={item.health} />
              <span>
                {item.availability_percent == null
                  ? "Availability unknown"
                  : `${item.availability_percent}% available`}
              </span>
              <span>
                {item.packet_loss_percent == null
                  ? "More check history needed"
                  : `${item.packet_loss_percent}% missed checks`}
              </span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function ScanProgress({ state }: { state: ScanState }) {
  const content =
    state === "running"
      ? ["Scan running", "HIOP is sending checks to the local agent. Results appear as the agent reports back."]
      : state === "completed"
      ? ["Scan completed", "Latest device states and history have been refreshed."]
      : ["Scan failed", "The request did not complete. Review the error and try again."];
      
  return (
    <section className={`scan-progress ${state}`} aria-live="polite">
      <span className={state === "running" ? "spinner" : "scan-progress-icon"}>
        <Icon name={state === "completed" ? "check" : "warning"} aria-hidden="true" />
      </span>
      <div>
        <strong>{content[0]}</strong>
        <p>{content[1]}</p>
      </div>
      {state === "running" && <div className="scan-progress-track"><i aria-hidden="true" /></div>}
    </section>
  );
}

function NetworkDeviceTable({
  devices,
  latest,
  busy,
  scanningDevice,
  onOpen,
  onScan,
}: {
  devices: Device[];
  latest: Map<string, Scan>;
  busy: boolean;
  scanningDevice: string;
  onOpen: (id: string) => void;
  onScan: (device: Device) => Promise<void>;
}) {
  return (
    <div className="noc-table-wrap">
      <table className="noc-table">
        <thead>
          <tr>
            <th scope="col">Device</th>
            <th scope="col">Asset tag</th>
            <th scope="col">IP address</th>
            <th scope="col">Department</th>
            <th scope="col">Type</th>
            <th scope="col">Status</th>
            <th scope="col">Response</th>
            <th scope="col">Last scan</th>
            <th scope="col">Actions</th>
          </tr>
        </thead>
        <tbody>
          {devices.map((device) => {
            const scan = latest.get(device.id);
            const status =
              device.inventory_status === "Retired"
                ? "Retired"
                : device.network_status || scan?.status || "Unknown";
            return (
              <tr key={device.id}>
                <td>
                  <button
                    className="noc-device-link"
                    onClick={() => onOpen(device.id)}
                    aria-label={`View details for ${device.hostname}`}
                  >
                    {device.hostname}
                  </button>
                </td>
                <td>{device.asset_tag}</td>
                <td>{device.ip_address}</td>
                <td>{device.department || "Unassigned"}</td>
                <td>{device.device_type}</td>
                <td>
                  <StatusBadge status={status} />
                </td>
                <td>{latency(scan?.response_time)}</td>
                <td>{formatDate(scan?.scanned_at)}</td>
                <td>
                  <div className="row-actions">
                    <button
                      disabled={busy || device.inventory_status === "Retired"}
                      onClick={() => void onScan(device)}
                      aria-label={`Scan ${device.hostname}`}
                      aria-busy={scanningDevice === device.id}
                    >
                      {scanningDevice === device.id ? "Scanning…" : "Scan"}
                    </button>
                    <button
                      onClick={() => onOpen(device.id)}
                      aria-label={`View ${device.hostname}`}
                    >
                      View
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function AlertRow({ alert, device, onOpen }: { alert: Alert; device?: Device; onOpen: () => void }) {
  return (
    <button
      className={alert.acknowledged ? "acknowledged" : ""}
      onClick={onOpen}
      aria-label={`View alert for ${device?.hostname ?? "Related device"}`}
    >
      <span className={`pulse ${alert.current_status.toLowerCase()}`} aria-hidden="true" />
      <span>
        <strong>{alert.message}</strong>
        <small>
          {device?.hostname ?? "Related device"} · {formatDate(alert.created_at)}
        </small>
      </span>
      <StatusBadge status={alert.current_status} />
    </button>
  );
}

