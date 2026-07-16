import { useNavigate, useParams } from "react-router-dom";
import { TicketForm } from "../components/TicketForm";
import { Feedback } from "../components/Feedback";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints } from "../lib/api";
import type { TicketInput } from "../lib/types";
import { PageTitle } from "./DashboardPage";

const emptyTicket: TicketInput = {title:"", description:"", priority:"Medium", device_id:null};

export default function TicketFormPage({mode}: {mode: "create" | "edit"}) {
  const {id = ""} = useParams();
  const navigate = useNavigate();
  const ticket = useRequest(() => mode === "edit" ? endpoints.ticket(id) : Promise.resolve(null), [id, mode]);
  const devices = useRequest(endpoints.devices, []);
  const editing = mode === "edit";
  const loading = devices.loading || (editing && ticket.loading);
  const error = devices.error || (editing ? ticket.error : "");
  const current = ticket.data;
  const initial: TicketInput = current ? {title:current.title, description:current.description, priority:current.priority as TicketInput["priority"], device_id:current.device_id} : emptyTicket;
  const save = async (values: TicketInput) => {
    const saved = editing ? await endpoints.updateTicket(id, values) : await endpoints.createTicket(values);
    navigate(`/tickets/${saved.id}`, {replace:true, state:{notice: editing ? "Ticket updated successfully." : "Ticket created successfully."}});
  };
  return <DashboardLayout><PageTitle eyebrow="IT service desk" title={editing ? "Edit ticket" : "Create ticket"} copy={editing ? "Update the supported service-ticket fields while preserving operational history." : "Record a new operational issue using the current FastAPI ticket schema."}/>{loading || error ? <Feedback loading={loading} error={error} onRetry={() => void Promise.all([devices.reload(), ...(editing ? [ticket.reload()] : [])])}/> : editing && !current ? <Feedback emptyTitle="Ticket not found" empty="The requested ticket is unavailable."/> : <TicketForm key={current?.id ?? "new"} initialValues={initial} devices={devices.data ?? []} cancelTo={editing ? `/tickets/${id}` : "/tickets"} submitLabel={editing ? "Save changes" : "Create ticket"} submittingLabel={editing ? "Saving changes…" : "Creating ticket…"} onSubmit={save}/>}</DashboardLayout>;
}
