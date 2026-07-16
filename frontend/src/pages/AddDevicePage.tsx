import { Link, useNavigate } from "react-router-dom";
import { DeviceForm } from "../components/DeviceForm";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import type { DeviceInput } from "../lib/types";
import { PageTitle } from "./DashboardPage";

const initialDevice: DeviceInput = {
  asset_tag: "", hostname: "", device_type: "", brand: "", model: "",
  serial_number: "", department: "", location: "", ip_address: "",
  mac_address: "", inventory_status: "Active",
};

export default function AddDevicePage() {
  const navigate = useNavigate();
  const createDevice = async (values: DeviceInput) => {
    const device = await endpoints.createDevice(values);
    navigate("/devices", { replace: true, state: { notice: `${device.hostname} was added successfully.` } });
  };

  return <DashboardLayout>
    <PageTitle eyebrow="Asset inventory" title="Add device" copy="Register a new hotel IT asset in the HIOP inventory." action={<Link className="secondary-action" to="/devices">Cancel</Link>} />
    <DeviceForm initialValues={initialDevice} cancelTo="/devices" submitLabel="Add device" submittingLabel="Adding device..." onSubmit={createDevice} />
  </DashboardLayout>;
}
