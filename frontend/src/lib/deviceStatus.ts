export function statusContext(status: string) {
  const normalized = status.toLowerCase();
  if (normalized === "online" || normalized === "offline") return "Last network state";
  return "Inventory state";
}
