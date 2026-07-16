import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import type { Device, TicketInput } from "../lib/types";

type Errors = Partial<Record<keyof TicketInput, string>>;

export function TicketForm({initialValues, devices, cancelTo, submitLabel, submittingLabel, onSubmit}: {initialValues: TicketInput; devices: Device[]; cancelTo: string; submitLabel: string; submittingLabel: string; onSubmit: (values: TicketInput) => Promise<void>}) {
  const [form, setForm] = useState(initialValues);
  const [errors, setErrors] = useState<Errors>({});
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const update = <K extends keyof TicketInput>(key: K, value: TicketInput[K]) => { setForm(current => ({...current, [key]: value})); setErrors(current => ({...current, [key]: undefined})); };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const nextErrors: Errors = {};
    if (!form.title.trim()) nextErrors.title = "Title is required."; else if (form.title.trim().length < 4) nextErrors.title = "Use at least four characters.";
    if (!form.description.trim()) nextErrors.description = "Description is required."; else if (form.description.trim().length < 10) nextErrors.description = "Provide at least ten characters of operational context.";
    if (!["Low", "Medium", "High"].includes(form.priority)) nextErrors.priority = "Select a supported priority.";
    setErrors(nextErrors); setSubmitError("");
    if (Object.keys(nextErrors).length || submitting) return;
    setSubmitting(true);
    try { await onSubmit({...form, title: form.title.trim(), description: form.description.trim(), device_id: form.device_id || null}); }
    catch (error) { setSubmitError(error instanceof Error ? error.message : "Unable to save the ticket."); }
    finally { setSubmitting(false); }
  };
  return <section className="ticket-form-card"><form className="ticket-form" onSubmit={submit} noValidate>
    <div className="ticket-form-grid">
      <label>Title<input className={errors.title ? "field-invalid" : ""} value={form.title} disabled={submitting} onChange={event => update("title", event.target.value)} aria-invalid={Boolean(errors.title)}/>{errors.title && <span className="field-error">{errors.title}</span>}</label>
      <label>Priority<select value={form.priority} disabled={submitting} onChange={event => update("priority", event.target.value as TicketInput["priority"])}><option>Low</option><option>Medium</option><option>High</option></select>{errors.priority && <span className="field-error">{errors.priority}</span>}</label>
      <label className="ticket-description-field">Description<textarea rows={8} className={errors.description ? "field-invalid" : ""} value={form.description} disabled={submitting} onChange={event => update("description", event.target.value)} aria-invalid={Boolean(errors.description)}/>{errors.description && <span className="field-error">{errors.description}</span>}</label>
      <label className="ticket-device-field">Related device <span className="optional-label">Optional</span><select value={form.device_id ?? ""} disabled={submitting} onChange={event => update("device_id", event.target.value || null)}><option value="">No related device</option>{devices.map(device => <option key={device.id} value={device.id}>{device.hostname} · {device.asset_tag}</option>)}</select><span className="field-help">Only a real registered HIOP device can be linked.</span></label>
    </div>
    {submitError && <div className="form-error" role="alert">{submitError}</div>}
    <footer><Link className="secondary-action" to={cancelTo}>Cancel</Link><button className="primary-action" disabled={submitting}>{submitting ? submittingLabel : submitLabel}</button></footer>
  </form></section>;
}
