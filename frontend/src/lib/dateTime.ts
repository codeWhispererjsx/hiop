let zone = "Africa/Lagos";
export function configureTimeZone(value: string) {
  try { new Intl.DateTimeFormat("en", {timeZone:value}).format(); } catch { return; }
  if (zone === value) return;
  zone=value;
  window.dispatchEvent(new Event("hiop:timezone-updated"));
}
export function configuredTimeZone() {
  return zone;
}
export function formatDateTime(value: string | number | Date, options?: Intl.DateTimeFormatOptions) {
  const date=new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown";
  return date.toLocaleString(undefined,{timeZone:zone,timeZoneName:"short",...options});
}
export function formatDateOnly(value: string | null | undefined) {
  if (!value) return "Not available";
  const datePart = value.slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(datePart)) return "Not available";
  const date = new Date(`${datePart}T00:00:00Z`);
  if (Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== datePart) return "Not available";
  return date.toLocaleDateString(undefined, { timeZone: "UTC" });
}
