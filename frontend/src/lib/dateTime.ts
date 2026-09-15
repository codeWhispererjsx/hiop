let zone = "Africa/Lagos";
export function configureTimeZone(value: string) {
  try { new Intl.DateTimeFormat("en", {timeZone:value}).format(); } catch { return; }
  if (zone === value) return;
  zone=value;
  window.dispatchEvent(new Event("hiop:timezone-updated"));
}
export function formatDateTime(value: string | number | Date, options?: Intl.DateTimeFormatOptions) {
  const date=new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown";
  return date.toLocaleString(undefined,{timeZone:zone,...options});
}
