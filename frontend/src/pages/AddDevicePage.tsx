import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import type { DeviceInput } from "../lib/types";
import { PageTitle } from "./DashboardPage";

const initialDevice: DeviceInput = {
  asset_tag: "",
  hostname: "",
  device_type: "",
  brand: "",
  model: "",
  serial_number: "",
  department: "",
  location: "",
  ip_address: "",
  mac_address: "",
  status: "Active",
};

type Errors = Partial<Record<keyof DeviceInput, string>>;

const fields: Array<{ key: keyof DeviceInput; label: string; placeholder: string }> = [
  { key: "asset_tag", label: "Asset Tag", placeholder: "HIOP-001" },
  { key: "hostname", label: "Hostname", placeholder: "frontdesk-pc-01" },
  { key: "device_type", label: "Device Type", placeholder: "Desktop" },
  { key: "brand", label: "Brand", placeholder: "Dell" },
  { key: "model", label: "Model", placeholder: "OptiPlex 7010" },
  { key: "serial_number", label: "Serial Number", placeholder: "Enter serial number" },
  { key: "department", label: "Department", placeholder: "Front Office" },
  { key: "location", label: "Location", placeholder: "Reception" },
  { key: "ip_address", label: "IP Address", placeholder: "192.168.1.10" },
  { key: "mac_address", label: "MAC Address", placeholder: "00:1A:2B:3C:4D:5E" },
];

export default function AddDevicePage() {
  const navigate = useNavigate();
  const [form, setForm] = useState<DeviceInput>(initialDevice);
  const [errors, setErrors] = useState<Errors>({});
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);

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
      const device = await endpoints.createDevice(trimDevice(form));
      navigate("/devices", {
        replace: true,
        state: { notice: `${device.hostname} was added successfully.` },
      });
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Unable to add the device.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <DashboardLayout>
      <PageTitle
        eyebrow="Asset inventory"
        title="Add device"
        copy="Register a new hotel IT asset in the HIOP inventory."
        action={<Link className="secondary-action" to="/devices">Cancel</Link>}
      />

      <section className="device-form-card">
        <form className="device-form" onSubmit={submit} noValidate>
          <div className="form-grid">
            {fields.map(({ key, label, placeholder }) => (
              <label key={key}>
                {label}
                <input
                  className={errors[key] ? "field-invalid" : ""}
                  value={form[key]}
                  onChange={(event) => update(key, event.target.value)}
                  placeholder={placeholder}
                  aria-invalid={Boolean(errors[key])}
                  aria-describedby={errors[key] ? `${key}-error` : undefined}
                  disabled={submitting}
                />
                {errors[key] && <span className="field-error" id={`${key}-error`}>{errors[key]}</span>}
              </label>
            ))}
            <label>
              Status
              <select value={form.status} onChange={(event) => update("status", event.target.value)} disabled={submitting}>
                <option value="Active">Active</option>
                <option value="Online">Online</option>
                <option value="Offline">Offline</option>
                <option value="Inactive">Inactive</option>
              </select>
            </label>
          </div>

          {submitError && <div className="form-error" role="alert">{submitError}</div>}

          <footer>
            <Link className="secondary-action" to="/devices">Cancel</Link>
            <button className="primary-action" type="submit" disabled={submitting}>
              {submitting ? "Adding device…" : "Add device"}
            </button>
          </footer>
        </form>
      </section>
    </DashboardLayout>
  );
}

function validate(device: DeviceInput): Errors {
  const errors: Errors = {};
  for (const key of Object.keys(device) as Array<keyof DeviceInput>) {
    if (!device[key].trim()) errors[key] = "This field is required.";
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
    Object.entries(device).map(([key, value]) => [key, value.trim()]),
  ) as DeviceInput;
}
