import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { Feedback } from "../components/Feedback";
import Modal from "../components/Modal";
import { StatusBadge } from "../components/StatusBadge";
import { endpoints } from "../lib/api";
import type {
  ConsolidatedDiscoveryDevice,
  DiscoveryJob,
  IdentityRule,
  OrganizationDepartment,
} from "../lib/types";
import "../styles/discovery-intelligence.css";
import "../styles/discovery-evidence.css";
import { useRequest } from "../hooks/useRequest";

const tabs = [
  ["Quick Scan", "/discovery-intelligence"],
  ["Devices", "/discovery-intelligence/devices"],
  ["Needs Review", "/discovery-intelligence/review"],
  ["Naming Rules", "/discovery-intelligence/identity-rules"],
] as const;

export default function DiscoveryIntelligencePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const mode = location.pathname.endsWith("/identity-rules")
    ? "rules"
    : location.pathname.endsWith("/devices")
      ? "devices"
      : location.pathname.endsWith("/review")
        ? "review"
        : "scan";
  const [devices, setDevices] = useState<ConsolidatedDiscoveryDevice[]>([]);
  const [range, setRange] = useState("");
  const [scanning, setScanning] = useState(false);
  const [activeScans, setActiveScans] = useState<DiscoveryJob[]>([]);
  const [lastScan, setLastScan] = useState<DiscoveryJob>();
  const [clock, setClock] = useState(0);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [detail, setDetail] = useState<Record<string, unknown>>();
  const [approving, setApproving] = useState("");
  const [enriching, setEnriching] = useState(false);
  const [adEnriching, setAdEnriching] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [query, setQuery] = useState("");
  const [departmentFilter, setDepartmentFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [vendorFilter, setVendorFilter] = useState("");
  const [identityFilter, setIdentityFilter] = useState("all");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkApproving, setBulkApproving] = useState(false);
  const [confirmBulkApproval, setConfirmBulkApproval] = useState(false);
  const [cancellingScan, setCancellingScan] = useState("");
  const [confirmClear, setConfirmClear] = useState(false);
  const [clearedScanId, setClearedScanId] = useState(() =>
    window.localStorage.getItem(discoveryClearKey()),
  );
  const currentUser = useRequest(endpoints.me, []);
  const canDiscover = currentUser.data?.role !== "viewer";
  const canApprove =
    currentUser.data?.role === "admin" ||
    currentUser.data?.role === "platformadmin";

  useEffect(() => {
    let active = true;
    const request = mode === "scan"
      ? endpoints.discoveryJobs(false, "quick_scan").then(async (history) => {
          const latest = history.items.find((job) => job.trigger_type === "quick_scan");
          if (!latest) return [];
          if (latest.id === clearedScanId) return [];
          if (active) setLastScan(latest);
          return (await endpoints.discoveryJobResults(latest.id)).items;
        })
      : endpoints.consolidatedDiscoveryDevices().then((response) => response.items);
    request
      .then((items) => {
        if (active) setDevices(items);
      })
      .catch((caught: unknown) => {
        if (active)
          setError(
            caught instanceof Error
              ? caught.message
              : "Devices could not be loaded.",
          );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [mode, clearedScanId]);
  useEffect(() => {
    let active = true;
    let hadActiveScan = false;
    const refresh = async () => {
      try {
        const response = await endpoints.discoveryJobs(true);
        if (!active) return;
        const quickScans = response.items;
        setActiveScans(quickScans);
        setClock(Date.now());
        if (!quickScans.length && !lastScan) {
          const history = await endpoints.discoveryJobs(false, "quick_scan");
          const latest = history.items.find((job) => job.trigger_type === "quick_scan");
          if (active && latest && latest.id !== clearedScanId) setLastScan(latest);
        }
        if (mode === "scan" && quickScans.length) {
          const latest = await endpoints.discoveryJobResults(quickScans[0].id);
          if (active) setDevices(latest.items);
        }
        if (!quickScans.length && hadActiveScan) {
          const history = await endpoints.discoveryJobs(false, "quick_scan");
          const completed = history.items.find(
            (job) => job.trigger_type === "quick_scan",
          );
          if (active && completed && completed.id !== clearedScanId) {
            setLastScan(completed);
            if (mode === "scan") {
              const latest = await endpoints.discoveryJobResults(completed.id);
              if (active) setDevices(latest.items);
            }
            setMessage(
              completed.status === "completed" || completed.status === "completed_with_warnings"
                ? `Discovery finished: ${completed.devices_discovered ?? 0} device${completed.devices_discovered === 1 ? "" : "s"} found.`
                : `Discovery ended with status: ${completed.status.replaceAll("_", " ")}.`,
            );
          }
        }
        hadActiveScan = quickScans.length > 0;
      } catch {
        // The main page error state remains reserved for actionable failures.
      }
    };
    void refresh();
    const poll = window.setInterval(() => void refresh(), 2500);
    return () => {
      active = false;
      window.clearInterval(poll);
    };
  }, [lastScan, mode, clearedScanId]);
  const visible = useMemo(() => {
    const term = query.trim().toLowerCase();
    return devices.filter((device) => {
      if (
        mode === "review" &&
        device.conflict_status !== "open" &&
        device.confidence_score >= 60
      )
        return false;
      if (departmentFilter && device.department !== departmentFilter)
        return false;
      if (
        typeFilter &&
        (device.device_type || device.classification) !== typeFilter
      )
        return false;
      if (vendorFilter && device.vendor !== vendorFilter) return false;
      if (identityFilter !== "all" && identityBucket(device) !== identityFilter)
        return false;
      return (
        !term ||
        [
          device.friendly_name,
          device.primary_hostname,
          device.ip_address,
          device.mac_address,
          device.department,
          device.classification,
          device.device_type,
          device.vendor,
        ].some((value) => value?.toLowerCase().includes(term))
      );
    });
  }, [
    devices,
    mode,
    query,
    departmentFilter,
    typeFilter,
    vendorFilter,
    identityFilter,
  ]);
  const options = (
    field: (device: ConsolidatedDiscoveryDevice) => string | null | undefined,
  ) =>
    [
      ...new Set(
        devices.map(field).filter((value): value is string => Boolean(value)),
      ),
    ].sort();
  const scan = async (event: FormEvent) => {
    event.preventDefault();
    const requestedNetwork = normalizeNetworkPreview(range);
    const existing = activeScans.find(
      (job) => job.network_range === requestedNetwork,
    );
    if (existing) {
      setError(
        `A scan of ${existing.network_range} is already ${existing.status}. Wait for it to finish before starting another.`,
      );
      return;
    }
    setScanning(true);
    setError("");
    setMessage("Starting discovery. Devices will appear as they are found.");
    try {
      const response = await endpoints.quickDiscoveryScan(range);
      setRange(response.normalized_network);
      setActiveScans((current) => [
        response.job,
        ...current.filter((job) => job.id !== response.job.id),
      ]);
      setLastScan(undefined);
      window.localStorage.removeItem(discoveryClearKey());
      setClearedScanId(null);
      setDevices([]);
      setSelected(new Set());
      setMessage(
        `Scanning ${response.normalized_network}. Results will update automatically.`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The scan could not be completed.",
      );
      setMessage("");
    } finally {
      setScanning(false);
      endpoints
        .discoveryJobs(true, "quick_scan")
        .then((response) => setActiveScans(response.items))
        .catch(() => undefined);
    }
  };
  const cancelScan = async (job: DiscoveryJob) => {
    setCancellingScan(job.id);
    setError("");
    try {
      const response = await endpoints.cancelDiscoveryJob(job.id);
      setActiveScans((current) => response.status==="cancelled"?current.filter((item)=>item.id!==job.id):current.map(item=>item.id===job.id?{...item,status:"cancelling",current_stage:"cancelling"}:item));
      setMessage(
        `Stop requested (${response.status}). ${response.partial_results} discovered device${response.partial_results === 1 ? " remains" : "s remain"} available for review.`,
      );
      const latest = await endpoints.discoveryJobResults(job.id);
      setDevices(latest.items);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The scan could not be cancelled.");
    } finally {
      setCancellingScan("");
    }
  };
  const inspect = async (device: ConsolidatedDiscoveryDevice) => {
    try {
      setDetail(await endpoints.discoveryResult(device.result_id));
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Device evidence could not be loaded.",
      );
    }
  };
  const approve = async (device: ConsolidatedDiscoveryDevice) => {
    setApproving(device.result_id);
    setError("");
    try {
      const managed = await endpoints.approveDiscoveryResult(device.result_id);
      setDevices((current) =>
        current.map((item) =>
          item.result_id === device.result_id
            ? { ...item, inventory_device_id: managed.id }
            : item,
        ),
      );
      setDetail((current) =>
        current ? { ...current, inventory_device_id: managed.id } : current,
      );
      setMessage(
        `${device.primary_hostname || device.ip_address} was approved into managed inventory.`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Device approval failed.",
      );
    } finally {
      setApproving("");
    }
  };
  const bulkApprove = async () => {
    const ids = [...selected].filter(
      (id) =>
        !devices.find((item) => item.result_id === id)?.inventory_device_id,
    );
    if (!ids.length) return;
    setBulkApproving(true);
    setConfirmBulkApproval(false);
    setError("");
    try {
      const response = await endpoints.bulkApproveDiscoveryResults(ids);
      const approved = new Map(
        response.approved.map((item) => [item.result_id, item.device_id]),
      );
      setDevices((current) =>
        current.map((item) =>
          approved.has(item.result_id)
            ? { ...item, inventory_device_id: approved.get(item.result_id)! }
            : item,
        ),
      );
      setSelected(new Set());
      setMessage(
        `${response.approved_count} devices approved. ${response.approved_count} devices added to managed inventory.${response.failed.length ? ` ${response.failed.length} could not be approved.` : ""}`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Selected devices could not be approved.",
      );
    } finally {
      setBulkApproving(false);
    }
  };
  const clearResults = () => {
    if (lastScan) {
      window.localStorage.setItem(discoveryClearKey(), lastScan.id);
      setClearedScanId(lastScan.id);
    }
    setDevices([]);
    setLastScan(undefined);
    setSelected(new Set());
    setDetail(undefined);
    setConfirmClear(false);
    setMessage(
      "Discovery results cleared from this view. Historical evidence and managed devices were preserved.",
    );
  };
  const approveDetail = async () => {
    const result = (detail?.result || {}) as Record<string, unknown>;
    if (!result.id) return;
    await approve(
      devices.find((item) => item.result_id === String(result.id)) ||
        ({
          ...result,
          result_id: String(result.id),
          inventory_device_id: null,
        } as ConsolidatedDiscoveryDevice),
    );
  };
  const enrich = async () => {
    const result = (detail?.result || {}) as Record<string, unknown>;
    if (!result.id) return;
    setEnriching(true);
    setError("");
    try {
      const response = await endpoints.enrichDiscoveryResult(String(result.id));
      setDetail(await endpoints.discoveryResult(String(result.id)));
      setMessage(
        response.status === "unavailable"
          ? `SNMP unavailable: ${response.warnings[0] || "No response."}`
          : `Enrichment ${response.status.replaceAll("_", " ")}. ${response.found.length} attributes found.`,
      );
      setDevices((current) =>
        current.map((item) =>
          item.result_id === String(result.id)
            ? { ...item, ...response.device }
            : item,
        ),
      );
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Device enrichment failed.",
      );
    } finally {
      setEnriching(false);
    }
  };
  const enrichFromAD = async () => {
    const result = (detail?.result || {}) as Record<string, unknown>;
    if (!result.id) return;
    setAdEnriching(true);
    setError("");
    try {
      const response = await endpoints.enrichDiscoveryResultFromAD(
        String(result.id),
      );
      setDetail(await endpoints.discoveryResult(String(result.id)));
      setMessage(
        response.status === "unavailable"
          ? `AD enrichment unavailable: ${response.warnings[0] || "No matching computer object."}`
          : `AD enrichment ${response.status.replaceAll("_", " ")}. ${response.found.length} attributes found.`,
      );
      setDevices((current) =>
        current.map((item) =>
          item.result_id === String(result.id)
            ? { ...item, ...response.device }
            : item,
        ),
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Active Directory enrichment failed.",
      );
    } finally {
      setAdEnriching(false);
    }
  };
  const confirmIdentity = async (values: {
    friendly_name?: string;
    department?: string;
    device_type?: string;
    location?: string;
  }) => {
    const result = (detail?.result || {}) as Record<string, unknown>;
    if (!result.id) return;
    setConfirming(true);
    setError("");
    try {
      const confirmed = await endpoints.confirmDiscoveryIdentity(
        String(result.id),
        values,
      );
      setDetail(await endpoints.discoveryResult(String(confirmed.id)));
      setDevices((current) =>
        current.map((item) =>
          item.result_id === String(confirmed.id)
            ? { ...item, ...confirmed }
            : item,
        ),
      );
      setMessage(
        `${confirmed.friendly_name || confirmed.primary_hostname || confirmed.ip_address} was manually confirmed.`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Identity confirmation failed.",
      );
    } finally {
      setConfirming(false);
    }
  };
  const decideIdentity = async (action: "accept" | "reject") => {
    const result = (detail?.result || {}) as Record<string, unknown>;
    if (!result.id) return;
    setConfirming(true);
    setError("");
    try {
      const updated =
        action === "accept"
          ? await endpoints.acceptDiscoveryIdentity(String(result.id))
          : await endpoints.rejectDiscoveryIdentity(String(result.id));
      setDetail(await endpoints.discoveryResult(String(updated.id)));
      setDevices((current) =>
        current.map((item) =>
          item.result_id === String(updated.id)
            ? { ...item, ...updated }
            : item,
        ),
      );
      setMessage(
        action === "accept"
          ? "Identity suggestion accepted."
          : "Identity suggestion rejected; technical identity was preserved.",
      );
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Identity review failed.",
      );
    } finally {
      setConfirming(false);
    }
  };

  return (
    <DashboardLayout>
      <header className="page-title discovery-title">
        <div>
          <span className="eyebrow">Discover</span>
          <h1>Network discovery</h1>
          <p>
            Scan a private network and build a clean inventory of real devices.
          </p>
        </div>
      </header>
      <nav className="discovery-tabs" aria-label="Discovery sections">
        {tabs.map(([label, path]) => (
          <button
            key={path}
            className={location.pathname === path ? "active" : ""}
            onClick={() => navigate(path)}
          >
            {label}
          </button>
        ))}
      </nav>
      {error && <Feedback error={error} />}
      {mode === "rules" && <IdentityRulesPanel canManage={canApprove} />}
      {mode === "scan" && (
        <>
          <section className="quick-scan-hero">
            <div>
              <span className="eyebrow">Simple network scan</span>
              <h2>Find devices on your network</h2>
              <p>
                Enter one private IP address or subnet. No credentials are
                required.
              </p>
            </div>
            {canDiscover ? (
              <form onSubmit={scan}>
                <label>
                  Network address or range
                  <input
                    value={range}
                    onChange={(event) => setRange(event.target.value)}
                    placeholder="192.168.1.0/24"
                    required
                  />
                </label>
                <button
                  className="primary-action"
                  disabled={
                    scanning ||
                    activeScans.some(
                      (job) => job.network_range === normalizeNetworkPreview(range),
                    )
                  }
                >
                  {scanning
                    ? "Scanning and identifying…"
                    : activeScans.some(
                          (job) => job.network_range === normalizeNetworkPreview(range),
                        )
                      ? "Scan already in progress"
                      : "Discover Devices"}
                </button>
              </form>
            ) : (
              <p>
                Viewer access is read-only. Discovery actions are unavailable.
              </p>
            )}
            {message && (
              <p role="status" className="quick-scan-status">
                {message}
              </p>
            )}
          </section>
          {activeScans.length > 0 && (
            <section className="active-scan-panel" aria-live="polite">
              <header>
                <div>
                  <span className="eyebrow">Discovery activity</span>
                  <h2>Scan in progress</h2>
                </div>
                <StatusBadge status="Running" />
              </header>
              {activeScans.map((job) => (
                <article key={job.id}>
                  <div>
                    <strong>{job.network_range}</strong>
                    <span>
                      {job.status === "pending"
                        ? "Waiting to start"
                        : job.current_stage === "enriching"
                          ? "Enriching discovered identities"
                          : "Discovering hosts"}
                    </span>
                  </div>
                  <progress
                    value={job.hosts_completed}
                    max={Math.max(1, job.hosts_total)}
                    aria-label={`${job.hosts_completed} of ${job.hosts_total} addresses checked`}
                  />
                  <dl>
                    <div>
                      <dt>Started</dt>
                      <dd>
                        {new Date(
                          job.started_at || job.created_at,
                        ).toLocaleString()}
                      </dd>
                    </div>
                    <div>
                      <dt>Elapsed</dt>
                      <dd>
                        {elapsed(job.started_at || job.created_at, clock)}
                      </dd>
                    </div>
                    <div>
                      <dt>Addresses checked</dt>
                      <dd>
                        {job.hosts_completed} / {job.hosts_total}
                      </dd>
                    </div>
                    <div>
                      <dt>Devices found</dt>
                      <dd>{job.devices_discovered ?? 0}</dd>
                    </div>
                    <div>
                      <dt>Current phase</dt>
                      <dd>{phaseLabel(job.current_stage)}</dd>
                    </div>
                  </dl>
                  {canDiscover && (
                    <button
                      type="button"
                      disabled={cancellingScan === job.id || job.status === "cancelling"}
                      onClick={() => void cancelScan(job)}
                    >
                      {cancellingScan === job.id || job.status === "cancelling" ? "Stopping…" : "Terminate scan"}
                    </button>
                  )}
                </article>
              ))}
            </section>
          )}
          {lastScan &&
            ["completed", "completed_with_warnings"].includes(lastScan.status) &&
            (lastScan.devices_discovered ?? 0) === 0 && (
              <section className="discovery-zero-state" role="status">
                <span className="eyebrow">Scan completed</span>
                <h2>No responding hosts were detected</h2>
                <dl>
                  <div><dt>Network</dt><dd>{lastScan.network_range}</dd></div>
                  <div><dt>Addresses checked</dt><dd>{lastScan.hosts_completed}</dd></div>
                  <div><dt>Status</dt><dd>{lastScan.status.replaceAll("_", " ")}</dd></div>
                </dl>
                <p>The network may be unreachable from this computer, devices may block ICMP, the subnet may be incorrect, or local firewall/ARP evidence may be unavailable.</p>
                <div className="row-actions">
                  <button type="button" onClick={() => setRange(lastScan.network_range)}>Retry Scan</button>
                  <button type="button" onClick={() => navigate("/settings")}>Check Network Settings</button>
                </div>
              </section>
            )}
          <section className="discovery-metrics">
            <Metric
              label="Latest scan"
              value={lastScan?.devices_discovered ?? devices.length}
              detail={lastScan ? `${lastScan.network_range} · ${lastScan.status.replaceAll("_", " ")}` : "Real devices in this property"}
            />
            <Metric
              label="Identified"
              value={
                devices.filter(
                  (device) => identityBucket(device) === "identified",
                ).length
              }
              detail="High-confidence identity"
            />
            <Metric
              label="Needs review"
              value={
                devices.filter((device) => identityBucket(device) === "review")
                  .length
              }
              detail="Check before approval"
            />
            <Metric
              label="Unknown"
              value={
                devices.filter((device) => identityBucket(device) === "unknown")
                  .length
              }
              detail="Technical identity preserved"
            />
          </section>
          {canDiscover && devices.length > 0 && (
            <div className="discovery-clear-bar">
              <span>
                Clear the table without deleting managed devices or historical
                evidence.
              </span>
              <button type="button" onClick={() => setConfirmClear(true)}>
                Clear results
              </button>
            </div>
          )}
          {confirmClear && (
            <Modal
              title="Clear discovery results?"
              onClose={() => setConfirmClear(false)}
            >
              <section className="discovery-confirm-modal">
                <p>
                  This removes the currently displayed scan results from the
                  table.
                </p>
                <div className="confirmation-safety">
                  <strong>Your operational data remains safe</strong>
                  <span>
                    Managed devices, monitoring observations, technical
                    evidence, and audit history will not be deleted.
                  </span>
                </div>
                <div className="row-actions">
                  <button type="button" onClick={() => setConfirmClear(false)}>
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="primary-action"
                    onClick={clearResults}
                  >
                    Clear results
                  </button>
                </div>
              </section>
            </Modal>
          )}
          {confirmBulkApproval && (
            <Modal
              title={`Approve ${selected.size} selected device${selected.size === 1 ? "" : "s"}?`}
              onClose={() => setConfirmBulkApproval(false)}
            >
              <section className="discovery-confirm-modal">
                <p>
                  These devices will be added to this property's managed inventory.
                </p>
                <div className="confirmation-safety">
                  <strong>Technical identity will be preserved</strong>
                  <span>
                    Hostnames, IP addresses, MAC addresses, discovery evidence,
                    and scan history remain linked to each approved device.
                  </span>
                </div>
                <div className="row-actions">
                  <button type="button" onClick={() => setConfirmBulkApproval(false)}>
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="primary-action"
                    disabled={bulkApproving}
                    onClick={() => void bulkApprove()}
                  >
                    {bulkApproving ? "Approving…" : "Approve devices"}
                  </button>
                </div>
              </section>
            </Modal>
          )}
        </>
      )}
      {mode !== "rules" && (mode !== "scan" || devices.length > 0) && (
        <section className="discovery-panel">
          <header>
            <div>
              <h2>{mode === "review" ? "Identity review" : "Devices"}</h2>
              <p>
                {mode === "review"
                  ? "Accept, edit, or reject medium- and low-confidence identity suggestions."
                  : "Discovered devices from your network."}
              </p>
            </div>
          </header>
          <div className="discovery-bulk-bar">
            <div>
              <b>{selected.size} selected</b>
              <span>
                Select devices with discovered hostnames, then approve them together.
              </span>
            </div>
            {canApprove && (
              <div className="row-actions">
                <button
                  onClick={() =>
                    setSelected(
                      new Set(
                        visible
                          .filter(
                            (item) =>
                              hasDiscoveredHostname(item) &&
                              !item.inventory_device_id,
                          )
                          .map((item) => item.result_id),
                      ),
                    )
                  }
                >
                  Select with hostname
                </button>
                <button
                  onClick={() =>
                    setSelected(
                      new Set(
                        visible
                          .filter(
                            (item) =>
                              identityBucket(item) === "identified" &&
                              !item.inventory_device_id,
                          )
                          .map((item) => item.result_id),
                      ),
                    )
                  }
                >
                  Select Identified
                </button>
                <button
                  onClick={() =>
                    setSelected(
                      new Set(
                        visible
                          .filter((item) => !item.inventory_device_id)
                          .map((item) => item.result_id),
                      ),
                    )
                  }
                >
                  Select All
                </button>
                <button
                  className="primary-action"
                  disabled={!selected.size || bulkApproving}
                  onClick={() => setConfirmBulkApproval(true)}
                >
                  {bulkApproving
                    ? "Approving…"
                    : `Approve Selected (${selected.size})`}
                </button>
              </div>
            )}
          </div>
          <div className="discovery-filters">
            <label>
              Search
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Name, hostname, IP, MAC, department, type, or vendor"
              />
            </label>
            <label>
              Identity
              <select
                value={identityFilter}
                onChange={(event) => setIdentityFilter(event.target.value)}
              >
                <option value="all">All</option>
                <option value="identified">Identified</option>
                <option value="review">Needs Review</option>
                <option value="unknown">Unknown</option>
              </select>
            </label>
            <label>
              Department
              <select
                value={departmentFilter}
                onChange={(event) => setDepartmentFilter(event.target.value)}
              >
                <option value="">All departments</option>
                {options((device) => device.department).map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </select>
            </label>
            <label>
              Device type
              <select
                value={typeFilter}
                onChange={(event) => setTypeFilter(event.target.value)}
              >
                <option value="">All device types</option>
                {options(
                  (device) => device.device_type || device.classification,
                ).map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </select>
            </label>
            <label>
              Vendor
              <select
                value={vendorFilter}
                onChange={(event) => setVendorFilter(event.target.value)}
              >
                <option value="">All vendors</option>
                {options((device) => device.vendor).map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </select>
            </label>
          </div>
          {loading ? (
            <Feedback loading />
          ) : (
            <DeviceTable
              rows={visible}
              filtered={Boolean(
                query ||
                identityFilter !== "all" ||
                departmentFilter ||
                typeFilter ||
                vendorFilter,
              )}
              inspect={inspect}
              approve={approve}
              approving={approving}
              canApprove={canApprove}
              selected={selected}
              setSelected={setSelected}
            />
          )}
        </section>
      )}
      {mode !== "rules" && detail && (
        <Modal title="Device details" onClose={() => setDetail(undefined)}>
          <Evidence
            data={detail}
            close={() => setDetail(undefined)}
            enrich={enrich}
            enriching={enriching}
            enrichFromAD={enrichFromAD}
            adEnriching={adEnriching}
            confirmIdentity={confirmIdentity}
            decideIdentity={decideIdentity}
            confirming={confirming}
            approve={approveDetail}
            approving={Boolean(approving)}
            canDiscover={canDiscover}
            canApprove={canApprove}
          />
        </Modal>
      )}
    </DashboardLayout>
  );
}

function elapsed(start: string, now: number) {
  const seconds = Math.max(
    0,
    Math.floor((now - new Date(start).getTime()) / 1000),
  );
  const minutes = Math.floor(seconds / 60);
  return minutes ? `${minutes}m ${seconds % 60}s` : `${seconds}s`;
}

function normalizeNetworkPreview(value: string): string {
  const trimmed = value.trim();
  if (/^(?:\d{1,3}\.){2}\d{1,3}$/.test(trimmed)) return `${trimmed}.0/24`;
  const completeRange = trimmed.match(/^((?:\d{1,3}\.){3})1-254$/);
  if (completeRange) return `${completeRange[1]}0/24`;
  return trimmed;
}

function phaseLabel(value: string | null): string {
  if (value === "host_discovery") return "Host discovery";
  if (value === "enriching") return "Identity enrichment";
  if (value === "cancelling") return "Stopping the scan worker";
  if (value === "waiting_for_agent") return "Waiting for the property’s local agent";
  if (value === "agent_discovery") return "Scanning from the local agent";
  return value ? value.replaceAll("_", " ") : "Starting";
}

const EMPTY_RULE = {
  name: "",
  scope: "property",
  match_field: "hostname",
  match_operator: "contains",
  pattern: "",
  output_device_type: "Printer",
  output_department_id: "",
  output_location: "",
  friendly_name_template: "{department} {device_type} {sequence}",
  priority: 100,
  confidence: 70,
};

function IdentityRulesPanel({ canManage }: { canManage: boolean }) {
  const [rules, setRules] = useState<IdentityRule[]>([]);
  const [departments, setDepartments] = useState<OrganizationDepartment[]>([]);
  const [form, setForm] = useState({ ...EMPTY_RULE });
  const [previewInput, setPreviewInput] = useState("");
  const [preview, setPreview] = useState<Record<string, unknown>>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const load = () =>
    Promise.all([
      endpoints.identityRules(true),
      endpoints.organizationDepartments(),
    ])
      .then(([ruleData, departmentData]) => {
        setRules(ruleData.items);
        setDepartments(departmentData);
      })
      .catch((caught) =>
        setError(
          caught instanceof Error
            ? caught.message
            : "Naming rules could not be loaded.",
        ),
      );
  useEffect(() => {
    void load();
  }, []);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await endpoints.createIdentityRule({
        ...form,
        property_id:
          form.scope === "property"
            ? window.localStorage.getItem("hiop.active_property_id")
            : null,
        output_department_id: form.output_department_id || null,
        output_location: form.output_location || null,
      });
      setForm({ ...EMPTY_RULE });
      setMessage(
        "Naming rule created. It will apply during the next enrichment.",
      );
      await load();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Rule could not be created.",
      );
    } finally {
      setBusy(false);
    }
  };
  const test = async () => {
    setBusy(true);
    setError("");
    try {
      setPreview(
        await endpoints.previewIdentityRule({
          property_id: window.localStorage.getItem("hiop.active_property_id"),
          hostname: previewInput,
        }),
      );
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Rule preview failed.",
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="identity-rules-workspace">
      <header className="discovery-panel">
        <span className="eyebrow">Administration · Discovery intelligence</span>
        <h2>Naming & classification rules</h2>
        <p>
          Turn your organisation’s technical identifiers into an explainable Friendly
          Name, Device Type, Suggested Department, and Location. Rules are
          scoped, deterministic, and never replace a manually confirmed
          identity.
        </p>
        <details className="feature-guide"><summary>How naming rules work</summary><ol><li>Choose an identifier your devices already use, such as a hostname.</li><li>Add a rule matching your own convention. For example, a hostname beginning with FO- might mean Front Office, if that is how your organisation names devices.</li><li>Set the friendly name, device type, department, or location you want suggested.</li><li>Test the rule against a known device, then run enrichment and review the suggestions.</li></ol><p>Saving a rule does not rename a computer on the network. It helps HIOP interpret its identity. Manually confirmed identities stay in place.</p></details><div className="precedence-note">
          <b>Precedence:</b> Manual confirmation → strong discovery/SNMP →
          Active Directory → configured rule → weak inference.
        </div>
      </header>
      {error && <Feedback error={error} />}{" "}
      {message && (
        <p className="quick-scan-status" role="status">
          {message}
        </p>
      )}
      <div className="identity-rule-layout">
        <section className="discovery-panel">
          <h3>Configured rules</h3>
          {!rules.length ? (
            <Feedback
              emptyTitle="No naming rules yet."
              empty="Add a confirmed organization or property naming convention. HIOP will not guess one."
            />
          ) : (
            <div className="rule-list">
              {rules.map((rule) => (
                <article key={rule.id}>
                  <div>
                    <strong>{rule.name}</strong>
                    <small>
                      {rule.scope} · Priority {rule.priority} ·{" "}
                      {rule.confidence}% confidence
                    </small>
                  </div>
                  <p>
                    <code>
                      {rule.match_field} {rule.match_operator} “{rule.pattern}”
                    </code>
                  </p>
                  <p>
                    {rule.department_name || "No department"} ·{" "}
                    {rule.output_device_type || "No device type"} ·{" "}
                    {rule.output_location || "No location"}
                  </p>
                  <StatusBadge status={rule.enabled ? "Active" : "Inactive"} />
                  {canManage && rule.enabled && (
                    <button
                      onClick={() =>
                        void endpoints.disableIdentityRule(rule.id).then(load)
                      }
                    >
                      Disable
                    </button>
                  )}
                </article>
              ))}
            </div>
          )}
        </section>
        <section className="discovery-panel">
          {canManage ? (
            <form className="identity-rule-form" onSubmit={submit}>
              <h3>Add rule</h3>
              <label>
                Rule name
                <input
                  required
                  value={form.name}
                  onChange={(event) =>
                    setForm({ ...form, name: event.target.value })
                  }
                  placeholder="Front Office printer hostname"
                />
              </label>
              <div className="form-grid">
                <label>
                  Scope
                  <select
                    value={form.scope}
                    onChange={(event) =>
                      setForm({ ...form, scope: event.target.value })
                    }
                  >
                    <option value="property">Current property</option>
                    <option value="organization">Organization-wide</option>
                  </select>
                </label>
                <label>
                  Evidence field
                  <select
                    value={form.match_field}
                    onChange={(event) =>
                      setForm({ ...form, match_field: event.target.value })
                    }
                  >
                    <option value="hostname">Hostname</option>
                    <option value="fqdn">FQDN</option>
                    <option value="vendor">Vendor</option>
                    <option value="snmp">SNMP description</option>
                    <option value="ad_ou">Active Directory OU</option>
                    <option value="device_type">Existing device type</option>
                  </select>
                </label>
                <label>
                  Match
                  <select
                    value={form.match_operator}
                    onChange={(event) =>
                      setForm({ ...form, match_operator: event.target.value })
                    }
                  >
                    <option value="contains">Contains</option>
                    <option value="starts_with">Starts with</option>
                    <option value="ends_with">Ends with</option>
                    <option value="equals">Equals</option>
                  </select>
                </label>
                <label>
                  Pattern
                  <input
                    required
                    value={form.pattern}
                    onChange={(event) =>
                      setForm({ ...form, pattern: event.target.value })
                    }
                    placeholder="Confirmed token"
                  />
                </label>
                <label>
                  Device type
                  <select
                    value={form.output_device_type}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        output_device_type: event.target.value,
                      })
                    }
                  >
                    {[
                      "Printer",
                      "POS Terminal",
                      "Desktop",
                      "Laptop",
                      "Server",
                      "Switch",
                      "Router",
                      "Firewall",
                      "Access Point",
                      "UPS",
                      "Phone",
                      "Other",
                    ].map((value) => (
                      <option key={value}>{value}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Department
                  <select
                    value={form.output_department_id}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        output_department_id: event.target.value,
                      })
                    }
                  >
                    <option value="">No department</option>
                    {departments
                      .filter((item) => item.is_active)
                      .map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.name}
                        </option>
                      ))}
                  </select>
                </label>
                <label>
                  Location (optional)
                  <input
                    value={form.output_location}
                    onChange={(event) =>
                      setForm({ ...form, output_location: event.target.value })
                    }
                    placeholder="Only with reliable evidence"
                  />
                </label>
                <label>
                  Confidence
                  <input
                    type="number"
                    min="1"
                    max="100"
                    value={form.confidence}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        confidence: Number(event.target.value),
                      })
                    }
                  />
                </label>
              </div>
              <label>
                Friendly name template
                <input
                  value={form.friendly_name_template}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      friendly_name_template: event.target.value,
                    })
                  }
                />
                <small>
                  Available: department, device_type, location, sequence,
                  hostname.
                </small>
              </label>
              <button className="primary-action" disabled={busy}>
                {busy ? "Saving…" : "Add rule"}
              </button>
            </form>
          ) : (
            <p>
              You can inspect rules. Organization administrators manage them.
            </p>
          )}
          <div className="rule-preview">
            <h3>Preview safely</h3>
            <p>Preview does not change a device.</p>
            <label>
              Technical hostname
              <input
                value={previewInput}
                onChange={(event) => setPreviewInput(event.target.value)}
                placeholder="heloshadtsc1821"
              />
            </label>
            <button
              disabled={busy || !previewInput}
              onClick={() => void test()}
            >
              Test rules
            </button>
            {preview && <pre>{JSON.stringify(preview, null, 2)}</pre>}
          </div>
        </section>
      </div>
    </section>
  );
}

function Metric({
  label,
  value,
  detail,
}: {
  label: string;
  value: number;
  detail: string;
}) {
  return (
    <article className="discovery-metric">
      <small>{label}</small>
      <strong>{value}</strong>
      <span>{detail}</span>
    </article>
  );
}

function identityBucket(
  device: ConsolidatedDiscoveryDevice,
): "identified" | "review" | "unknown" {
  if (
    device.conflict_status === "open" ||
    (device.confidence_score >= 40 && device.confidence_score < 80)
  )
    return "review";
  if (
    device.confidence_score < 40 ||
    (!device.friendly_name &&
      (device.device_type || device.classification || "")
        .toLowerCase()
        .includes("unknown"))
  )
    return "unknown";
  return "identified";
}

function hasDiscoveredHostname(device: ConsolidatedDiscoveryDevice): boolean {
  const hostname = (device.primary_hostname || device.fqdn || "")
    .trim()
    .toLowerCase();
  return Boolean(
    hostname &&
    hostname !== "not yet discovered" &&
    hostname !== "unknown" &&
    hostname !== "unknown device",
  );
}

function discoveryClearKey(): string {
  const propertyId = window.localStorage.getItem("hiop.active_property_id") || "organization";
  return `hiop.discovery.cleared_scan.${propertyId}`;
}

function DeviceTable({
  rows,
  filtered,
  inspect,
  approve,
  approving,
  canApprove,
  selected,
  setSelected,
}: {
  rows: ConsolidatedDiscoveryDevice[];
  filtered: boolean;
  inspect: (device: ConsolidatedDiscoveryDevice) => void;
  approve: (device: ConsolidatedDiscoveryDevice) => void;
  approving: string;
  canApprove: boolean;
  selected: Set<string>;
  setSelected: (value: Set<string>) => void;
}) {
  if (!rows.length)
    return (
      <Feedback
        emptyTitle={
          filtered ? "No matching devices" : "No devices discovered yet."
        }
        empty={
          filtered
            ? "Try a friendly name, hostname, IP address, MAC address, or filter."
            : "Choose Discover Devices to scan the approved private network."
        }
      />
    );
  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };
  return (
    <div className="table-wrap quick-device-table">
      <table>
        <thead>
          <tr>
            <th>
              <span className="sr-only">Select</span>
            </th>
            <th>Device</th>
            <th>Hostname</th>
            <th>IP</th>
            <th>Type</th>
            <th>Department</th>
            <th>Location</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((device) => {
            const bucket = identityBucket(device);
            const approved = Boolean(device.inventory_device_id);
            const hostname =
              device.primary_hostname || device.fqdn || "Hostname unavailable";
            return (
              <tr key={device.result_id}>
                <td data-label="Select">
                  <input
                    type="checkbox"
                    aria-label={`Select ${device.friendly_name || hostname || device.ip_address}`}
                    checked={selected.has(device.result_id)}
                    disabled={approved || !canApprove}
                    onChange={() => toggle(device.result_id)}
                  />
                </td>
                <td data-label="Device">
                  <strong>{device.friendly_name || "Unknown Device"}</strong>
                  <small>
                    {device.mac_address || "MAC not available"} ·{" "}
                    {device.confidence_level?.replaceAll("_", " ") || "low"}{" "}
                    confidence
                  </small>
                </td>
                <td data-label="Hostname">
                  <code>{hostname}</code>
                </td>
                <td data-label="IP">
                  <code>{device.ip_address}</code>
                </td>
                <td data-label="Type">
                  {device.device_type || device.classification || "Unknown"}
                </td>
                <td data-label="Department">
                  {device.department || "Unknown"}
                </td>
                <td data-label="Location">{device.location || "Unknown"}</td>
                <td data-label="Status">
                  <StatusBadge
                    status={
                      approved
                        ? "Approved"
                        : bucket === "identified"
                          ? "Identified"
                          : bucket === "review"
                            ? "Needs Review"
                            : "Unknown"
                    }
                  />
                </td>
                <td data-label="Actions">
                  <div className="row-actions">
                    <button onClick={() => inspect(device)}>
                      {bucket === "review" && canApprove
                        ? "Review"
                        : "View details"}
                    </button>
                    {canApprove && !approved && bucket === "identified" && (
                      <button
                        disabled={approving === device.result_id}
                        onClick={() => void approve(device)}
                      >
                        {approving === device.result_id
                          ? "Approving…"
                          : "Approve"}
                      </button>
                    )}
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

function Evidence({
  data,
  close,
  enrich,
  enriching,
  enrichFromAD,
  adEnriching,
  confirmIdentity,
  decideIdentity,
  confirming,
  approve,
  approving,
  canDiscover,
  canApprove,
}: {
  data: Record<string, unknown>;
  close: () => void;
  enrich: () => void;
  enriching: boolean;
  enrichFromAD: () => void;
  adEnriching: boolean;
  confirmIdentity: (values: {
    friendly_name?: string;
    department?: string;
    device_type?: string;
    location?: string;
  }) => void;
  decideIdentity: (action: "accept" | "reject") => void;
  confirming: boolean;
  approve: () => Promise<void>;
  approving: boolean;
  canDiscover: boolean;
  canApprove: boolean;
}) {
  const result = (data.result || {}) as Record<string, unknown>;
  const profile = (data.identity_profile || {}) as Record<string, unknown>;
  const evidence = (data.evidence || []) as Array<Record<string, unknown>>;
  const conflicts = (data.conflicts || []) as Array<Record<string, unknown>>;
  const history = (data.identity_history || []) as Array<
    Record<string, unknown>
  >;
  const [friendlyName, setFriendlyName] = useState(
    String(result.friendly_name || ""),
  );
  const [department, setDepartment] = useState(String(result.department || ""));
  const [deviceType, setDeviceType] = useState(
    String(result.device_type || result.classification || ""),
  );
  const [location, setLocation] = useState(String(result.location || ""));
  const interfaces = (() => {
    try {
      return JSON.parse(String(result.interface_information || "[]")) as Array<
        Record<string, unknown>
      >;
    } catch {
      return [];
    }
  })();
  const uptime = result.uptime_seconds
    ? `${Math.floor(Number(result.uptime_seconds) / 86400)}d ${Math.floor((Number(result.uptime_seconds) % 86400) / 3600)}h`
    : "Not available";
  const openConflicts = conflicts.filter((item) => item.status === "open");
  const approved = Boolean(data.inventory_device_id);
  const strong =
    Number(result.confidence_score || 0) >= 60 && !openConflicts.length;
  const explanations = [
    ...new Set(
      evidence.map((item) =>
        explainEvidence(
          String(item.source || ""),
          String(item.evidence_type || ""),
        ),
      ),
    ),
  ].filter(Boolean);
  return (
    <section className="discovery-detail">
      <header>
        <div>
          <small>Why HIOP identified this device</small>
          <h3>
            {String(
              result.friendly_name ||
                result.primary_hostname ||
                result.ip_address ||
                "Unable to identify this device",
            )}
          </h3>
        </div>
        <div className="row-actions">
          {canDiscover && (
            <>
              <button
                className="primary-action"
                disabled={enriching}
                onClick={() => void enrich()}
              >
                {enriching ? "Enriching…" : "Enrich Device"}
              </button>
              <button
                disabled={adEnriching}
                onClick={() => void enrichFromAD()}
              >
                {adEnriching ? "Checking AD…" : "Enrich from Active Directory"}
              </button>
            </>
          )}
          <button onClick={close}>Close</button>
        </div>
      </header>
      <div className="enrichment-statuses">
        <p className="enrichment-status">
          <b>DNS:</b>{" "}
          {dnsMessage(
            String(result.dns_status || ""),
            String(result.fqdn || ""),
            evidence,
          )}
        </p>
        <p className="enrichment-status">
          <b>SNMP:</b>{" "}
          {enrichmentMessage(
            "SNMP",
            String(result.snmp_enrichment_status || "not_attempted"),
          )}
        </p>
        <p className="enrichment-status">
          <b>Active Directory:</b>{" "}
          {enrichmentMessage(
            "Active Directory",
            String(result.ad_enrichment_status || "not_attempted"),
          )}
        </p>
      </div>
      <div className="detail-grid">
        <article>
          <h4>Identity</h4>
          <p>
            <b>Friendly Name:</b>{" "}
            {String(result.friendly_name || "Unknown Device")}
          </p>
          <p>
            <b>Name source:</b>{" "}
            {String(
              profile.friendly_name_source ||
                (result.identity_confirmed ? "MANUAL" : "Not yet classified"),
            )}
          </p>
          <p>
            <b>Original Hostname:</b>{" "}
            {String(result.primary_hostname || "Not available")}
          </p>
          <p>
            <b>FQDN:</b> {String(result.fqdn || "Not available")}
          </p>
          <p>
            <b>IP:</b> {String(result.ip_address)}
          </p>
          <p>
            <b>MAC:</b> {String(result.mac_address || "Not available")}
          </p>
        </article>
        <article>
          <h4>Classification</h4>
          <p>
            <b>Device Type:</b>{" "}
            {String(result.device_type || result.classification || "Unknown")}
          </p>
          <p>
            <b>Type source:</b>{" "}
            {String(
              profile.classification_source ||
                (result.identity_confirmed ? "MANUAL" : "Discovery"),
            )}
          </p>
          {Boolean(result.classification) &&
            result.classification !== result.device_type && (
              <p>
                <b>Technical Classification:</b> {String(result.classification)}
              </p>
            )}
          <p>
            <b>Department:</b> {String(result.department || "Unknown")}
          </p>
          <p>
            <b>Department source:</b>{" "}
            {String(
              profile.department_source ||
                (result.identity_confirmed ? "MANUAL" : "Not yet classified"),
            )}
          </p>
          <p>
            <b>Location:</b> {String(result.location || "Unknown")}
          </p>
          <p>
            <b>Location source:</b>{" "}
            {String(
              profile.location_source ||
                (result.identity_confirmed ? "MANUAL" : "Not yet discovered"),
            )}
          </p>
        </article>
        <article>
          <h4>Technical</h4>
          <p>
            <b>Vendor:</b> {String(result.vendor || "Unknown")}
          </p>
          <p>
            <b>Model:</b> {String(result.model || "Not available")}
          </p>
          <p>
            <b>Serial Number:</b>{" "}
            {String(result.serial_number || "Not available")}
          </p>
          <p>
            <b>Operating System:</b>{" "}
            {String(
              result.operating_system ||
                result.ad_operating_system ||
                "Not available",
            )}
          </p>
          <p>
            <b>Firmware:</b> {String(result.firmware || "Not available")}
          </p>
          <p>
            <b>Uptime:</b> {uptime}
          </p>
          <p>
            <b>Interfaces:</b>{" "}
            {String(result.interface_count ?? "Not available")}
          </p>
          {interfaces.slice(0, 8).map((item, index) => (
            <small key={index}>
              {String(
                item.name || item.description || `Interface ${item.index}`,
              )}{" "}
              — {String(item.oper_status || "Unknown")}
            </small>
          ))}
        </article>
        <article>
          <h4>Windows / Active Directory</h4>
          <p>
            <b>Domain:</b> {String(result.ad_domain || "Not available")}
          </p>
          <p>
            <b>Computer:</b>{" "}
            {String(result.ad_computer_name || "Not available")}
          </p>
          <p>
            <b>OS Version:</b>{" "}
            {String(result.ad_operating_system_version || "Not available")}
          </p>
          <p>
            <b>OU:</b>{" "}
            {String(result.ad_organizational_unit || "Not available")}
          </p>
          <p>
            <b>AD Status:</b>{" "}
            {result.ad_enabled === true
              ? "Enabled"
              : result.ad_enabled === false
                ? "Disabled"
                : "Not available"}
          </p>
          <p>
            <b>Last Logon:</b>{" "}
            {result.ad_last_logon_at
              ? new Date(String(result.ad_last_logon_at)).toLocaleString()
              : "Not available"}
          </p>
          <p>
            <b>Description:</b>{" "}
            {String(
              result.ad_description || result.description || "Not available",
            )}
          </p>
          <p>
            <b>Distinguished Name:</b>{" "}
            {String(result.ad_distinguished_name || "Not available")}
          </p>
        </article>
      </div>
      <article className="identity-confidence">
        <h4>Identification confidence</h4>
        <strong>
          {String(result.confidence_score || 0)}% ·{" "}
          {String(result.confidence_level || "low").replaceAll("_", " ")}
        </strong>
        <p>{String(result.confidence_reason || "Insufficient evidence.")}</p>
        {explanations.length ? (
          <ul>
            {explanations.map((item) => (
              <li key={item}>✓ {item}</li>
            ))}
          </ul>
        ) : (
          <p>
            Unable to identify this device: no corroborating identity evidence
            is available.
          </p>
        )}
        <small>
          {result.identity_confirmed
            ? "Manually confirmed"
            : "Automatic assessment"}{" "}
          · {String(data.correlated_observations || 1)} correlated
          observation(s)
        </small>
      </article>
      {openConflicts.length > 0 && (
        <section className="identity-conflicts">
          <h4>Conflict detected</h4>
          {openConflicts.map((item, index) => (
            <article key={String(item.id || index)}>
              <StatusBadge status="Review" />
              <strong>{String(item.attribute)}</strong>
              <p>
                ⚠ {String(item.left_source)}: {String(item.left_value)} ↔{" "}
                {String(item.right_source)}: {String(item.right_value)}
              </p>
            </article>
          ))}
        </section>
      )}
      {canDiscover &&
        !result.identity_confirmed &&
        typeof result.friendly_name === "string" &&
        result.friendly_name.length > 0 && (
          <div className="identity-review-actions">
            <button
              className="primary-action"
              disabled={confirming}
              onClick={() => decideIdentity("accept")}
            >
              Accept suggestion
            </button>
            <button
              disabled={confirming}
              onClick={() => decideIdentity("reject")}
            >
              Reject suggestion
            </button>
          </div>
        )}
      {canDiscover && (
        <form
          className="identity-confirmation"
          onSubmit={(event) => {
            event.preventDefault();
            confirmIdentity({
              friendly_name: friendlyName,
              department,
              device_type: deviceType,
              location,
            });
          }}
        >
          <h4>Manual correction</h4>
          <p>
            Confirm or correct the suggested identity. Manually confirmed values
            are preserved during future discovery.
          </p>
          <label>
            Friendly Name
            <input
              value={friendlyName}
              onChange={(event) => setFriendlyName(event.target.value)}
            />
          </label>
          <label>
            Department
            <input
              value={department}
              onChange={(event) => setDepartment(event.target.value)}
            />
          </label>
          <label>
            Device Type
            <input
              value={deviceType}
              onChange={(event) => setDeviceType(event.target.value)}
            />
          </label>
          <label>
            Location
            <input
              value={location}
              onChange={(event) => setLocation(event.target.value)}
            />
          </label>
          <button className="primary-action" disabled={confirming}>
            {confirming ? "Confirming…" : "Confirm Identification"}
          </button>
        </form>
      )}
      <section className="identity-evidence">
        <h4>Evidence</h4>
        <div className="evidence-cards">
          {evidence.length ? (
            evidence.map((item, index) => (
              <article key={String(item.id || index)}>
                <strong>
                  {String(item.evidence_type || "evidence").replaceAll(
                    "_",
                    " ",
                  )}
                </strong>
                <p>{String(item.value || "Observed")}</p>
                <small>
                  {sourceLabel(String(item.source || "network"))} ·{" "}
                  {item.verified ? "confirmed" : "observed"}
                </small>
              </article>
            ))
          ) : (
            <p>Not available</p>
          )}
        </div>
      </section>
      <section className="identity-history">
        <h4>Identity history</h4>
        {history.length ? (
          history.map((item, index) => (
            <p key={String(item.id || index)}>
              <b>{String(item.attribute)}</b>:{" "}
              {String(item.previous_value || "Unknown")} →{" "}
              {String(item.current_value)}{" "}
              <small>{sourceLabel(String(item.source))}</small>
            </p>
          ))
        ) : (
          <p>No identity changes have been recorded.</p>
        )}
      </section>
      <footer className="identity-review-actions">
        {approved ? (
          <>
            <StatusBadge status="Approved" />
            <span>This device exists once in managed inventory.</span>
          </>
        ) : strong && canApprove ? (
          <button
            className="primary-action"
            disabled={approving}
            onClick={() => void approve()}
          >
            {approving ? "Approving…" : "Approve Device"}
          </button>
        ) : (
          <>
            <StatusBadge status="Review" />
            <span>
              {canApprove
                ? "Review conflicts or confirm the identity before approval."
                : "Read-only evidence view."}
            </span>
          </>
        )}
      </footer>
    </section>
  );
}

function sourceLabel(source: string) {
  const value = source.toLowerCase();
  if (value.includes("active_directory") || value === "ad")
    return "Active Directory";
  if (value.includes("hostname_rule")) return "Hostname Rules";
  if (value.includes("dns")) return "DNS";
  if (value.includes("dhcp")) return "DHCP";
  if (value.includes("snmp")) return "SNMP";
  if (value.includes("arp")) return "ARP";
  if (value.includes("icmp") || value.includes("ping"))
    return "Network Discovery";
  if (value.includes("manual") || value.includes("administrator"))
    return "Manual Confirmation";
  return source.replaceAll("_", " ");
}
function explainEvidence(source: string, type: string) {
  const label = sourceLabel(source);
  const attribute = type.replaceAll("_", " ");
  return label && attribute ? `${label} supplied ${attribute} evidence` : "";
}
function enrichmentMessage(provider: string, status: string) {
  if (status === "not_attempted") return "Enrichment has not been performed.";
  if (status === "unavailable")
    return provider === "Active Directory"
      ? "Active Directory unavailable."
      : "SNMP unavailable.";
  return status.replaceAll("_", " ");
}
function dnsMessage(
  status: string,
  fqdn: string,
  evidence: Array<Record<string, unknown>>,
) {
  const confirmed = evidence.some(
    (item) =>
      String(item.source || "")
        .toLowerCase()
        .includes("dns") && item.verified !== false,
  );
  return [
    "ptr_found",
    "forward_confirmed",
    "resolved",
    "verified",
    "success",
  ].includes(status) ||
    Boolean(fqdn) ||
    confirmed
    ? "DNS information available."
    : "DNS information unavailable.";
}
