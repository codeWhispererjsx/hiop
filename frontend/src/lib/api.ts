const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000/api/v1";

export class ApiError extends Error { status: number; constructor(message: string, status: number) { super(message); this.status = status; } }

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem("hiop_token");
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try { response = await fetch(`${API_URL}${path}`, { ...init, headers }); }
  catch { throw new ApiError("Cannot reach the HIOP backend. Confirm FastAPI is running.", 0); }
  if (response.status === 401) { localStorage.removeItem("hiop_token"); window.dispatchEvent(new Event("hiop:unauthorized")); }
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((item: { msg?: string }) => item.msg ?? "Invalid value").join(" ");
    } catch { /* non-JSON response */ }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function queryString(values: Record<string, string | number | undefined>) {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => { if (value !== undefined && value !== "") params.set(key, String(value)); });
  const query = params.toString();
  return query ? `?${query}` : "";
}

async function download(path: string) {
  const token = localStorage.getItem("hiop_token");
  let response: Response;
  try { response = await fetch(`${API_URL}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} }); }
  catch { throw new ApiError("Cannot reach the HIOP backend. Confirm FastAPI is running.", 0); }
  if (response.status === 401) { localStorage.removeItem("hiop_token"); window.dispatchEvent(new Event("hiop:unauthorized")); }
  if (!response.ok) throw new ApiError(`Export failed (${response.status})`, response.status);
  const disposition = response.headers.get("Content-Disposition") ?? "";
  return { blob: await response.blob(), filename: disposition.match(/filename="?([^";]+)"?/)?.[1] ?? "hiop-audit.csv" };
}

export const endpoints = {
  login: (email: string, password: string) => api<{access_token:string}>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  register: (body: {username:string;email:string;password:string}) => api<import("./types").User>("/auth/register", { method: "POST", body: JSON.stringify(body) }),
  me: () => api<import("./types").User>("/auth/me"),
  dashboard: () => api<import("./types").DashboardData>("/dashboard/"),
  devices: () => api<import("./types").Device[]>("/devices/"),
  device: (id: string) => api<import("./types").Device>(`/devices/${id}`),
  createDevice: (body: import("./types").DeviceInput) => api<import("./types").Device>("/devices/", { method: "POST", body: JSON.stringify(body) }),
  updateDevice: (id: string, body: Partial<import("./types").DeviceInput>) => api<import("./types").Device>(`/devices/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  retireDevice: (id: string) => api<{message:string}>(`/devices/${id}`, { method: "DELETE" }),
  scanDevice: (device_id: string) => api<import("./types").Scan>("/network/scan", { method: "POST", body: JSON.stringify({ device_id }) }),
  scanAll: () => api<{total_devices:number;online:number;offline:number;results:import("./types").Scan[]}>("/network/scan-all", { method: "POST" }),
  scanRange: (network: string) => api<Array<{ip_address:string;status:string;response_time:number|null}>>("/network/scan-range", { method: "POST", body: JSON.stringify({ network }) }),
  scanHistory: (limit = 100) => api<import("./types").Scan[]>(`/network/history?limit=${limit}`),
  tickets: () => api<import("./types").Ticket[]>("/tickets/"),
  ticket: (id: string) => api<import("./types").Ticket>(`/tickets/${id}`),
  createTicket: (body: import("./types").TicketInput) => api<import("./types").Ticket>("/tickets/", { method: "POST", body: JSON.stringify(body) }),
  updateTicket: (id: string, body: Partial<import("./types").Ticket>) => api<import("./types").Ticket>(`/tickets/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  assignTicket: (id: string, assignedTo: string) => api<import("./types").Ticket>(`/tickets/${id}/assign?assigned_to=${encodeURIComponent(assignedTo)}`, { method: "PATCH" }),
  closeTicket: (id: string) => api<import("./types").Ticket>(`/tickets/${id}/close`, { method: "PATCH" }),
  deleteTicket: (id: string) => api<{message:string}>(`/tickets/${id}`, { method: "DELETE" }),
  alerts: () => api<import("./types").Alert[]>("/alerts"),
  acknowledgeAlert: (id: string) => api<{id:string;acknowledged:boolean}>(`/alerts/${id}/acknowledge`, { method: "PATCH" }),
  auditLogs: (filters: import("./types").AuditFilters = {}, signal?: AbortSignal) => api<import("./types").AuditLogPage>(`/audit-logs${queryString(filters)}`, { signal }),
  auditLog: (id: string) => api<import("./types").AuditLog>(`/audit-logs/${id}`),
  exportAuditLogs: (filters: import("./types").AuditFilters = {}) => download(`/audit-logs/export${queryString(filters)}`),
  users: () => api<import("./types").User[]>("/users"),
  user: (id: string) => api<import("./types").User>(`/users/${id}`),
  userAudit: (id: string) => api<import("./types").AuditLog[]>(`/users/${id}/audit`),
  userRoles: () => api<string[]>("/users/roles"),
  eligibleAssignees: () => api<import("./types").User[]>("/users/eligible-assignees"),
  createUser: (body: import("./types").UserInput) => api<import("./types").User>("/users", { method: "POST", body: JSON.stringify(body) }),
  updateUser: (id: string, body: Pick<import("./types").UserInput, "username" | "email">) => api<import("./types").User>(`/users/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  changeUserRole: (id: string, role: string) => api<import("./types").User>(`/users/${id}/role`, { method: "PATCH", body: JSON.stringify({ role }) }),
  changeUserStatus: (id: string, is_active: boolean) => api<import("./types").User>(`/users/${id}/status`, { method: "PATCH", body: JSON.stringify({ is_active }) }),
  resetUserPassword: (id: string, password: string) => api<{message:string}>(`/users/${id}/reset-password`, { method: "POST", body: JSON.stringify({ password }) }),
  deactivateUser: (id: string) => api<void>(`/users/${id}`, { method: "DELETE" }),
  settings: () => api<import("./types").MonitoringSettings>("/settings"),
  updateSettings: (body: import("./types").MonitoringSettings) => api<import("./types").MonitoringSettings>("/settings", { method: "PUT", body: JSON.stringify(body) }),
};
