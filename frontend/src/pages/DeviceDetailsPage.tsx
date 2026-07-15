import { useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { Feedback } from "../components/Feedback";
import Modal from "../components/Modal";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import type { LiveEvent } from "../lib/types";
import { PageTitle } from "./DashboardPage";

export default function DeviceDetailsPage() {
  const { id = "" } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const successNotice = (location.state as { notice?: string } | null)?.notice;
  const { data: device, loading, error, reload } = useRequest(() => endpoints.device(id));
  const [confirmingRetirement, setConfirmingRetirement] = useState(false);
  const [retiring, setRetiring] = useState(false);
  const [retireError, setRetireError] = useState("");

  const handleLiveEvent = (event: LiveEvent) => {
    if (event.event === "device_status_changed" && event.device_id === id) void reload();
  };

  const retire = async () => {
    if (!device || retiring) return;
    setRetiring(true);
    setRetireError("");
    try {
      await endpoints.retireDevice(device.id);
      navigate("/devices", { replace: true, state: { notice: `${device.hostname} was retired successfully.`, toast: true } });
    } catch (error) {
      setRetireError(error instanceof Error ? error.message : "Unable to retire this device.");
      setRetiring(false);
    }
  };

  return (
    <DashboardLayout onLiveEvent={handleLiveEvent}>
      <PageTitle
        eyebrow="Asset inventory"
        title={device?.hostname ?? "Device details"}
        copy="Complete device information from the HIOP inventory."
        action={<div className="page-actions"><Link className="secondary-action" to="/devices">Back to devices</Link>{device && device.status !== "Retired" && <><Link className="primary-action" to={`/devices/${id}/edit`}>Edit device</Link><button className="danger-action" onClick={() => { setRetireError(""); setConfirmingRetirement(true); }}>Retire device</button></>}</div>}
      />

      {successNotice && <div className="inline-notice" role="status">{successNotice}</div>}

      {loading || error ? (
        <Feedback loading={loading} error={error} onRetry={reload} />
      ) : !device ? (
        <Feedback emptyTitle="Device not found" empty="No device information is available." />
      ) : (
        <section className="device-details" aria-label={`Details for ${device.hostname}`}>
          <header>
            <div>
              <span>Current status</span>
              <b className={`status-badge ${device.status.toLowerCase().replaceAll(" ", "-")}`}>{device.status}</b>
            </div>
          </header>
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
            <Detail label="IP Address" value={device.ip_address} />
            <Detail label="MAC Address" value={device.mac_address} />
            <Detail label="Status" value={device.status} />
          </dl>
        </section>
      )}

      {confirmingRetirement && device && <Modal title="Retire device" onClose={() => !retiring && setConfirmingRetirement(false)}>
        <div className="retire-confirmation">
          <p>Retire <strong>{device.hostname}</strong>? The device will remain in inventory history but will no longer be considered active.</p>
          <p className="retire-warning">This action should only be used when the asset has been permanently removed from service.</p>
          {retireError && <div className="form-error" role="alert">{retireError}</div>}
          <footer>
            <button className="secondary-action" disabled={retiring} onClick={() => setConfirmingRetirement(false)}>Cancel</button>
            <button className="danger-action" disabled={retiring} onClick={() => void retire()}>{retiring ? "Retiring..." : "Confirm retirement"}</button>
          </footer>
        </div>
      </Modal>}
    </DashboardLayout>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value || "—"}</dd></div>;
}
