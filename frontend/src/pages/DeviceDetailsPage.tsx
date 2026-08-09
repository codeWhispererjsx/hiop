import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { ConfirmationModal } from "../components/ConfirmationModal";
import { DeviceHistory, type HistorySection } from "../components/DeviceHistory";
import { Feedback } from "../components/Feedback";
import { StatusBadge } from "../components/StatusBadge";
import { Toast } from "../components/Toast";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import type { Device, LiveEvent } from "../lib/types";
import { PageTitle } from "./DashboardPage";

type DetailsTab = "overview" | HistorySection;
const tabs: Array<{ id: DetailsTab; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "scans", label: "Scan History" },
  { id: "alerts", label: "Alerts" },
  { id: "tickets", label: "Tickets" },
  { id: "audit", label: "Audit Trail" },
];

export default function DeviceDetailsPage() {
  const { id = "" } = useParams();
  const location = useLocation();
  const successNotice = (location.state as { notice?: string } | null)?.notice;
  const { data: device, loading, error, reload } = useRequest(() => endpoints.device(id));
  const [discoveryIdentity, setDiscoveryIdentity] = useState<Record<string, unknown>>();
  useEffect(() => {
    let active = true;
    endpoints.inventoryDiscoveryIdentity(id).then((value) => { if (active) setDiscoveryIdentity(value); }).catch(() => { if (active) setDiscoveryIdentity(undefined); });
    return () => { active = false; };
  }, [id]);
  const hierarchy = useRequest(endpoints.hierarchy, []);
  const currentUser = useRequest(endpoints.me, []);
  const [activeTab, setActiveTab] = useState<DetailsTab>("overview");
  const [confirmingRetirement, setConfirmingRetirement] = useState(false);
  const [retiring, setRetiring] = useState(false);
  const [retireError, setRetireError] = useState("");
  const [retireNotice, setRetireNotice] = useState("");

  const handleLiveEvent = (event: LiveEvent) => {
    if (event.event === "device_status_changed" && event.device_id === id) void reload();
  };

  const retire = async () => {
    if (!device || retiring) return;
    setRetiring(true);
    setRetireError("");
    try {
      await endpoints.retireDevice(device.id);
      await reload();
      setConfirmingRetirement(false);
      setRetireNotice(`${device.hostname} was retired successfully.`);
    } catch (requestError) {
      setRetireError(requestError instanceof Error ? requestError.message : "Unable to retire this device.");
    } finally {
      setRetiring(false);
    }
  };

  const isRetired = device?.inventory_status.toLowerCase() === "retired";

  return (
    <DashboardLayout onLiveEvent={handleLiveEvent}>
      <PageTitle
        eyebrow="Asset inventory"
        title={device?.hostname ?? "Device details"}
        copy="Complete device information and operational history from HIOP."
        action={<div className="page-actions">
          <Link className="secondary-action" to="/devices">Back to devices</Link>
          {device && !isRetired && ["admin", "technician"].includes(currentUser.data?.role ?? "") && <>
            <Link className="primary-action" to={`/devices/${id}/edit`}>Edit device</Link>
            {currentUser.data?.role === "admin" && <button className="danger-action" onClick={() => { setRetireError(""); setConfirmingRetirement(true); }}>Retire device</button>}
          </>}
        </div>}
      />

      {(retireNotice || successNotice) && <Toast message={retireNotice || successNotice || "Device updated successfully."} />}

      {loading || error ? (
        <Feedback loading={loading} error={error} onRetry={reload} />
      ) : !device ? (
        <Feedback emptyTitle="Device not found" empty="No device information is available." />
      ) : (
        <>
          {isRetired && <div className="retired-banner"><StatusBadge status="Retired" /><span>This asset is retired. Its details and operational history remain available.</span></div>}
          <nav className="detail-tabs" aria-label="Device detail sections">
            {tabs.map((tab) => <button key={tab.id} className={activeTab === tab.id ? "active" : ""} aria-current={activeTab === tab.id ? "page" : undefined} onClick={() => setActiveTab(tab.id)}>{tab.label}</button>)}
          </nav>

          {activeTab === "overview" ? <DeviceOverview device={device} discoveryIdentity={discoveryIdentity} networkZone={hierarchy.data?.network_zones.find((zone) => zone.id === device.network_zone_id)?.name ?? ""} /> : <DeviceHistory device={device} section={activeTab} />}
        </>
      )}

      {confirmingRetirement && device && <ConfirmationModal
        title="Retire device"
        confirmLabel="Confirm retirement"
        busyLabel="Retiring..."
        busy={retiring}
        error={retireError}
        onCancel={() => setConfirmingRetirement(false)}
        onConfirm={() => void retire()}
      >
        <p>Retire <strong>{device.hostname}</strong>? The device record and all historical scans, alerts, tickets, and audit activity will remain available.</p>
        <p className="confirmation-warning">This action should only be used when the asset has been permanently removed from service.</p>
      </ConfirmationModal>}
    </DashboardLayout>
  );
}

function DeviceOverview({ device, networkZone, discoveryIdentity }: { device: Device; networkZone: string; discoveryIdentity?: Record<string, unknown> }) {
  const identity=(discoveryIdentity?.result||{}) as Record<string,unknown>;
  const evidence=(discoveryIdentity?.evidence||[]) as Array<Record<string,unknown>>;
  const conflicts=(discoveryIdentity?.conflicts||[]) as Array<Record<string,unknown>>;
  const history=(discoveryIdentity?.identity_history||[]) as Array<Record<string,unknown>>;
  return <section className="device-details" aria-label={`Details for ${device.hostname}`}>
    <header><div className="overview-statuses"><span>Inventory</span><StatusBadge status={device.inventory_status} /><span>Network</span><StatusBadge status={device.network_status} /></div></header>
    <dl>
      <Detail label="Device ID" value={device.id} />
      <Detail label="Asset Tag" value={device.asset_tag} />
      <Detail label="Hostname" value={device.hostname} />
      <Detail label="Device Type" value={device.device_type} />
      <Detail label="Brand" value={device.brand} />
      <Detail label="Model" value={device.model} />
      <Detail label="Serial Number" value={device.serial_number} />
      <Detail label="Department" value={device.department} />
      <Detail label="Location" value={device.location} />
      <Detail label="Network Zone" value={networkZone} />
      <Detail label="IP Address" value={device.ip_address} />
      <Detail label="MAC Address" value={device.mac_address || "Unknown"} />
      <Detail label="Inventory Status" value={device.inventory_status} />
      <Detail label="Network Status" value={device.network_status} />
    </dl>
    {discoveryIdentity && <>
      <h2>Discovery identity</h2>
      <dl>
        <Detail label="Friendly Name" value={String(identity.friendly_name||"Unknown")} />
        <Detail label="Original Hostname" value={String(identity.primary_hostname||"Not available")} />
        <Detail label="FQDN" value={String(identity.fqdn||"Not available")} />
        <Detail label="Device Role" value={String(identity.device_type||identity.classification||"Unknown")} />
        <Detail label="Technical Classification" value={String(identity.classification||"Not available")} />
        <Detail label="Department" value={String(identity.department||"Not available")} />
        <Detail label="Vendor / Model" value={`${String(identity.vendor||"Unknown")} / ${String(identity.model||"Not available")}`} />
        <Detail label="Confidence" value={`${String(identity.confidence_score||0)}% · ${String(identity.confidence_level||"low").replaceAll("_"," ")}`} />
        <Detail label="Confidence reason" value={String(identity.confidence_reason||"Insufficient identifying evidence.")} />
        <Detail label="Evidence sources" value={[...new Set(evidence.map(item=>String(item.source||"Discovery")))].join(", ")||"Not available"} />
        <Detail label="Conflicts" value={conflicts.filter(item=>item.status==="open").length?`${conflicts.filter(item=>item.status==="open").length} conflict(s) require review`:"None detected"} />
        <Detail label="Identity history" value={history.length?`${history.length} recorded change(s)`:"No identity changes recorded"} />
      </dl>
    </>}
    <h2>Windows / Active Directory</h2>
    <dl>
      <Detail label="Domain" value={device.ad_domain || "Not available"} />
      <Detail label="Computer" value={device.ad_computer_name || "Not available"} />
      <Detail label="Operating System" value={device.ad_operating_system || "Not available"} />
      <Detail label="OS Version" value={device.ad_operating_system_version || "Not available"} />
      <Detail label="Organizational Unit" value={device.ad_organizational_unit || "Not available"} />
      <Detail label="AD Description" value={device.ad_description || "Not available"} />
      <Detail label="AD Status" value={device.ad_enabled === true ? "Enabled" : device.ad_enabled === false ? "Disabled" : "Not available"} />
      <Detail label="Last Logon" value={device.ad_last_logon_at ? new Date(device.ad_last_logon_at).toLocaleString() : "Not available"} />
      <Detail label="Distinguished Name" value={device.ad_distinguished_name || "Not available"} />
    </dl>
  </section>;
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value || "Not recorded"}</dd></div>;
}
