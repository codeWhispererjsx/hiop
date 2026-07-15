import { Link, useNavigate, useParams } from "react-router-dom";
import { DeviceForm } from "../components/DeviceForm";
import { Feedback } from "../components/Feedback";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import type { DeviceInput } from "../lib/types";
import { PageTitle } from "./DashboardPage";

export default function EditDevicePage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { data: device, loading, error, reload } = useRequest(() => endpoints.device(id));
  const detailsPath = `/devices/${id}`;

  const saveDevice = async (values: DeviceInput) => {
    const updated = await endpoints.updateDevice(id, values);
    navigate(detailsPath, { replace: true, state: { notice: `${updated.hostname} was updated successfully.` } });
  };

  return <DashboardLayout>
    <PageTitle eyebrow="Asset inventory" title={device ? `Edit ${device.hostname}` : "Edit device"} copy="Update this asset's inventory and network information." action={<Link className="secondary-action" to={detailsPath}>Cancel</Link>} />
    {loading || error ? (
      <Feedback loading={loading} error={error} onRetry={reload} />
    ) : !device ? (
      <Feedback emptyTitle="Device not found" empty="No device information is available to edit." />
    ) : (
      <DeviceForm initialValues={device} cancelTo={detailsPath} submitLabel="Save changes" submittingLabel="Saving changes..." onSubmit={saveDevice} />
    )}
  </DashboardLayout>;
}
