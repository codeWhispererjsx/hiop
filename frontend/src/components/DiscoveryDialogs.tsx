import { useMemo, useState, type FormEvent } from "react";
import type { BulkApprovalItem, DiscoveredDevice, InventoryApproval } from "../lib/types";
import Modal from "./Modal";


function initialApproval(device: DiscoveredDevice): InventoryApproval {
  return {
    asset_tag: "",
    hostname: device.hostname ?? "",
    device_type: device.device_type_guess === "unknown" ? "" : device.device_type_guess ?? "",
    ip_address: device.ip_address,
    mac_address: device.mac_address ?? "",
    brand: device.vendor ?? "",
    model: "",
    serial_number: "",
    department: "",
    location: "",
    inventory_status: "Active",
    network_zone_id: device.network_zone_id ?? undefined,
  };
}

export function ApprovalDialog({ devices, busy, error, onClose, onSubmit }: {
  devices: DiscoveredDevice[];
  busy: boolean;
  error: string;
  onClose: () => void;
  onSubmit: (items: BulkApprovalItem[]) => Promise<void>;
}) {
  const defaults = useMemo(() => Object.fromEntries(devices.map((device) => [device.id, initialApproval(device)])), [devices]);
  const [forms, setForms] = useState<Record<string, InventoryApproval>>(defaults);
  const update = (id: string, field: keyof InventoryApproval, value: string) => setForms((current) => ({
    ...current,
    [id]: { ...current[id], [field]: value },
  }));
  const submit = (event: FormEvent) => {
    event.preventDefault();
    void onSubmit(devices.map((device) => ({ discovery_id: device.id, inventory: forms[device.id] })));
  };
  return <Modal title={devices.length === 1 ? "Approve discovered device" : `Approve ${devices.length} discovered devices`} onClose={() => !busy && onClose()}>
    <form className="modal-form discovery-approval-form" onSubmit={submit}>
      <p className="muted">Approval creates official inventory records. Verify every identifier before saving; HIOP prevents duplicate asset tags, serial numbers, and MAC addresses.</p>
      {devices.map((device, index) => {
        const form = forms[device.id];
        return <fieldset className="approval-device-card" key={device.id}>
          <legend><span>{index + 1}</span>{device.hostname || device.ip_address}</legend>
          <div className="approval-source"><strong>{device.ip_address}</strong><span>{device.mac_address || "MAC unavailable"}</span><span>{device.vendor || "Vendor unknown"}</span></div>
          <div className="form-grid">
            <Field label="Asset tag" value={form.asset_tag} onChange={(value) => update(device.id, "asset_tag", value)} required />
            <Field label="Serial number" value={form.serial_number} onChange={(value) => update(device.id, "serial_number", value)} required />
            <Field label="Hostname" value={form.hostname ?? ""} onChange={(value) => update(device.id, "hostname", value)} required />
            <Field label="Device type" value={form.device_type ?? ""} onChange={(value) => update(device.id, "device_type", value)} required />
            <Field label="IP address" value={form.ip_address ?? ""} onChange={(value) => update(device.id, "ip_address", value)} required />
            <Field label="MAC address" value={form.mac_address ?? ""} onChange={(value) => update(device.id, "mac_address", value)} required />
            <Field label="Brand" value={form.brand} onChange={(value) => update(device.id, "brand", value)} required />
            <Field label="Model" value={form.model} onChange={(value) => update(device.id, "model", value)} required />
            <Field label="Department" value={form.department} onChange={(value) => update(device.id, "department", value)} required />
            <Field label="Location" value={form.location} onChange={(value) => update(device.id, "location", value)} required />
          </div>
        </fieldset>;
      })}
      {error && <p className="form-error" role="alert">{error}</p>}
      <footer><button type="button" className="secondary-action" disabled={busy} onClick={onClose}>Cancel</button><button className="primary-action" disabled={busy}>{busy ? "Creating inventory…" : devices.length === 1 ? "Approve and create device" : `Approve ${devices.length} devices`}</button></footer>
    </form>
  </Modal>;
}

function Field({ label, value, required, onChange }: { label: string; value: string; required?: boolean; onChange: (value: string) => void }) {
  return <label>{label}<input value={value} required={required} onChange={(event) => onChange(event.target.value)} /></label>;
}

export function RunDiscoveryDialog({ busy, error, onClose, onSubmit }: { busy:boolean; error:string; onClose:()=>void; onSubmit:(range:string)=>Promise<void> }) {
  const [range, setRange] = useState("");
  return <Modal title="Run Discovery" onClose={() => !busy && onClose()}><form className="modal-form" onSubmit={(event) => { event.preventDefault(); void onSubmit(range); }}>
    <p className="muted">Enter a private CIDR contained within the authorized ranges configured by an administrator. Public ranges are always rejected.</p>
    <label>Private CIDR range<input value={range} required placeholder="Authorized CIDR" onChange={(event) => setRange(event.target.value)} /></label>
    {error && <p className="form-error" role="alert">{error}</p>}
    <footer><button type="button" className="secondary-action" disabled={busy} onClick={onClose}>Cancel</button><button className="primary-action" disabled={busy}>{busy ? "Discovering…" : "Run Discovery"}</button></footer>
  </form></Modal>;
}

export function RejectDialog({ count, busy, error, onClose, onSubmit }: { count:number; busy:boolean; error:string; onClose:()=>void; onSubmit:(reason?:string)=>Promise<void> }) {
  const [reason, setReason] = useState("");
  return <Modal title={count === 1 ? "Reject discovery" : `Reject ${count} discoveries`} onClose={() => !busy && onClose()}><form className="modal-form" onSubmit={(event) => { event.preventDefault(); void onSubmit(reason || undefined); }}>
    <p className="muted">Rejected records remain in Discovery history. A reason is optional and will be retained with the record.</p>
    <label>Reason (optional)<textarea rows={4} maxLength={500} value={reason} onChange={(event) => setReason(event.target.value)} /></label>
    {error && <p className="form-error" role="alert">{error}</p>}
    <footer><button type="button" className="secondary-action" disabled={busy} onClick={onClose}>Cancel</button><button className="danger-action" disabled={busy}>{busy ? "Rejecting…" : "Reject"}</button></footer>
  </form></Modal>;
}
