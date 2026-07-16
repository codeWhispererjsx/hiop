import { type FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { endpoints } from "../lib/api";
import type { DeviceInput, HierarchyCatalog } from "../lib/types";

type Errors = Partial<Record<keyof DeviceInput, string>>;

const fields: Array<{ key: keyof DeviceInput; label: string; placeholder: string }> = [
  { key: "asset_tag", label: "Asset Tag", placeholder: "HIOP-001" },
  { key: "hostname", label: "Hostname", placeholder: "frontdesk-pc-01" },
  { key: "device_type", label: "Device Type", placeholder: "Desktop" },
  { key: "brand", label: "Brand", placeholder: "Dell" },
  { key: "model", label: "Model", placeholder: "OptiPlex 7010" },
  { key: "serial_number", label: "Serial Number", placeholder: "Enter serial number" },
  { key: "ip_address", label: "IP Address", placeholder: "192.168.1.10" },
  { key: "mac_address", label: "MAC Address", placeholder: "00:1A:2B:3C:4D:5E" },
];

export function DeviceForm({ initialValues, cancelTo, submitLabel, submittingLabel, onSubmit }: {
  initialValues: DeviceInput;
  cancelTo: string;
  submitLabel: string;
  submittingLabel: string;
  onSubmit: (device: DeviceInput) => Promise<void>;
}) {
  const [form, setForm] = useState<DeviceInput>(initialValues);
  const [errors, setErrors] = useState<Errors>({});
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [catalog, setCatalog] = useState<HierarchyCatalog | null>(null);
  const [catalogError, setCatalogError] = useState("");

  useEffect(() => {
    endpoints.hierarchy().then(setCatalog).catch((error) => setCatalogError(error instanceof Error ? error.message : "Unable to load locations and departments."));
  }, []);

  const update = (key: keyof DeviceInput, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
    if (errors[key]) setErrors((current) => ({ ...current, [key]: undefined }));
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const validationErrors = validate(form);
    setErrors(validationErrors);
    setSubmitError("");
    if (Object.keys(validationErrors).length) return;

    setSubmitting(true);
    try {
      await onSubmit(trimDevice(form));
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Unable to save the device.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="device-form-card">
      <form className="device-form" onSubmit={submit} noValidate>
        <div className="form-grid">
          {fields.map(({ key, label, placeholder }) => (
            <label key={key}>
              {label}
              <input
                className={errors[key] ? "field-invalid" : ""}
                value={String(form[key] ?? "")}
                onChange={(event) => update(key, event.target.value)}
                placeholder={placeholder}
                aria-invalid={Boolean(errors[key])}
                aria-describedby={errors[key] ? `${key}-error` : undefined}
                disabled={submitting}
              />
              {errors[key] && <span className="field-error" id={`${key}-error`}>{errors[key]}</span>}
            </label>
          ))}
          <HierarchySelect label="Department" value={form.department_id} fallback={form.department} options={catalog?.departments ?? []} unavailable={catalogError} error={errors.department} onChange={(id, name) => { setForm((current) => ({ ...current, department_id: id, department: name })); setErrors((current)=>({...current,department:undefined})); }} disabled={submitting} />
          <HierarchySelect label="Room / Location" value={form.room_id} fallback={form.location} options={catalog?.rooms ?? []} unavailable={catalogError} error={errors.location} onChange={(id, name) => { setForm((current) => ({ ...current, room_id: id, location: name })); setErrors((current)=>({...current,location:undefined})); }} disabled={submitting} />
          <HierarchySelect label="Network Zone" value={form.network_zone_id} fallback="" options={catalog?.network_zones ?? []} unavailable={catalogError} optional onChange={(id) => setForm((current) => ({ ...current, network_zone_id: id }))} disabled={submitting} />
          <label>
            Inventory Status
            <select value={form.inventory_status} onChange={(event) => update("inventory_status", event.target.value)} disabled={submitting}>
              <option value="Active">Active</option>
              <option value="Inactive">Inactive</option>
            </select>
            <span className="field-help">Online and Offline are updated by network monitoring. Retirement uses the Retire action.</span>
          </label>
        </div>

        {submitError && <div className="form-error" role="alert">{submitError}</div>}

        <footer>
          <Link className="secondary-action" to={cancelTo}>Cancel</Link>
          <button className="primary-action" type="submit" disabled={submitting}>
            {submitting ? submittingLabel : submitLabel}
          </button>
        </footer>
      </form>
    </section>
  );
}

function validate(device: DeviceInput): Errors {
  const errors: Errors = {};
  const required: Array<keyof DeviceInput> = ["asset_tag", "hostname", "device_type", "brand", "model", "serial_number", "department", "location", "ip_address", "mac_address", "inventory_status"];
  for (const key of required) {
    if (!String(device[key] ?? "").trim()) errors[key] = "This field is required.";
  }
  if (device.hostname && !/^[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?$/.test(device.hostname.trim())) {
    errors.hostname = "Use letters, numbers, dots, or hyphens only.";
  }
  if (device.ip_address && !isValidIpv4(device.ip_address.trim())) {
    errors.ip_address = "Enter a valid IPv4 address.";
  }
  if (device.mac_address && !/^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$/.test(device.mac_address.trim())) {
    errors.mac_address = "Enter a valid MAC address.";
  }
  return errors;
}

function isValidIpv4(value: string) {
  const parts = value.split(".");
  return parts.length === 4 && parts.every((part) => /^\d{1,3}$/.test(part) && Number(part) <= 255);
}

function trimDevice(device: DeviceInput): DeviceInput {
  return Object.fromEntries(
    Object.entries(device).map(([key, value]) => [key, typeof value === "string" ? value.trim() : value]),
  ) as DeviceInput;
}

function HierarchySelect({ label, value, fallback, options, unavailable, error, optional = false, disabled, onChange }: { label: string; value?: string | null; fallback: string; options: Array<{id:string;name:string;is_active:boolean}>; unavailable: string; error?: string; optional?: boolean; disabled: boolean; onChange: (id: string | null, name: string) => void }) {
  const active = options.filter((option) => option.is_active || option.id === value);
  return <label>{label}<select value={value ?? ""} disabled={disabled || Boolean(unavailable)} onChange={(event) => { const item = options.find((option) => option.id === event.target.value); onChange(item?.id ?? null, item?.name ?? ""); }}>
    <option value="">{optional ? `No ${label.toLowerCase()}` : `Select ${label.toLowerCase()}`}</option>
    {active.map((option) => <option key={option.id} value={option.id}>{option.name}{option.is_active ? "" : " (Inactive)"}</option>)}
  </select>{!value && fallback && <span className="field-help">Current legacy value: {fallback}</span>}{(unavailable||error) && <span className="field-error">{unavailable||error}</span>}</label>;
}
