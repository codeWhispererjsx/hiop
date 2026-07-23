import { clearAuthToken, getAuthToken } from "./auth";

const API_URL = import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? "http://127.0.0.1:8001/api/v1" : "/api/v1");

export class ApiError extends Error { status: number; constructor(message: string, status: number) { super(message); this.status = status; } }

const inFlightGets = new Map<string, Promise<unknown>>();

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const token = getAuthToken();
  const requestKey = method === "GET" && !init.signal ? `${token ?? "anonymous"}:${path}` : "";
  const existing = requestKey ? inFlightGets.get(requestKey) : undefined;
  if (existing) return existing as Promise<T>;

  const request = performRequest<T>(path, init, token);
  if (!requestKey) return request;
  inFlightGets.set(requestKey, request);
  try { return await request; }
  finally { inFlightGets.delete(requestKey); }
}

async function performRequest<T>(path: string, init: RequestInit, token: string | null): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try { response = await fetch(`${API_URL}${path}`, { ...init, headers }); }
  catch { throw new ApiError("Cannot reach the HIOP backend. Confirm FastAPI is running.", 0); }
  if (response.status === 401) { clearAuthToken(); window.dispatchEvent(new Event("hiop:unauthorized")); }
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
  const token = getAuthToken();
  let response: Response;
  try { response = await fetch(`${API_URL}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} }); }
  catch { throw new ApiError("Cannot reach the HIOP backend. Confirm FastAPI is running.", 0); }
  if (response.status === 401) { clearAuthToken(); window.dispatchEvent(new Event("hiop:unauthorized")); }
  if (!response.ok) throw new ApiError(`Export failed (${response.status})`, response.status);
  const disposition = response.headers.get("Content-Disposition") ?? "";
  return { blob: await response.blob(), filename: disposition.match(/filename="?([^";]+)"?/)?.[1] ?? "hiop-audit.csv" };
}

export const endpoints = {
  login: (email: string, password: string) => api<{access_token:string}>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  me: () => api<import("./types").User>("/auth/me"),
  dashboard: () => api<import("./types").DashboardData>("/dashboard/"),
  devices: () => api<import("./types").Device[]>("/devices/"),
  device: (id: string) => api<import("./types").Device>(`/devices/${id}`),
  createDevice: (body: import("./types").DeviceInput) => api<import("./types").Device>("/devices/", { method: "POST", body: JSON.stringify(body) }),
  updateDevice: (id: string, body: Partial<import("./types").DeviceInput>) => api<import("./types").Device>(`/devices/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  retireDevice: (id: string) => api<{message:string}>(`/devices/${id}`, { method: "DELETE" }),
  deviceScans: (id: string) => api<import("./types").Scan[]>(`/devices/${id}/scans`),
  deviceAlerts: (id: string) => api<import("./types").Alert[]>(`/devices/${id}/alerts`),
  deviceTickets: (id: string) => api<import("./types").Ticket[]>(`/devices/${id}/tickets`),
  deviceAuditLogs: (id: string) => api<import("./types").AuditLog[]>(`/devices/${id}/audit-logs`),
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
  reportsSummary: (filters: Pick<import("./types").ReportFilters, "start_date" | "end_date"> = {}) => api<import("./types").ReportsSummary>(`/reports/summary${queryString(filters)}`),
  report: (name: import("./types").ReportKey, filters: import("./types").ReportFilters = {}) => api<import("./types").ReportPage>(`/reports/${name}${queryString(filters)}`),
  exportReport: (name: import("./types").ReportKey, filters: import("./types").ReportFilters = {}) => download(`/reports/${name}/export${queryString(filters)}`),
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
  settings: () => api<import("./types").SettingsBundle>("/settings"),
  publicSettings: () => api<import("./types").PublicSettings>("/settings/public"),
  updateGeneralSettings: (body: import("./types").GeneralSettings) => api<import("./types").SettingsBundle>("/settings/general", { method: "PUT", body: JSON.stringify(body) }),
  updateOrganizationSettings: (body: import("./types").OrganizationSettings) => api<import("./types").SettingsBundle>("/settings/organization", { method: "PUT", body: JSON.stringify(body) }),
  updateNetworkSettings: (body: import("./types").NetworkSettings) => api<import("./types").SettingsBundle>("/settings/network", { method: "PUT", body: JSON.stringify(body) }),
  updateNotificationSettings: (body: import("./types").NotificationSettings) => api<import("./types").SettingsBundle>("/settings/notifications", { method: "PUT", body: JSON.stringify(body) }),
  updateDiscoverySettings: (body: import("./types").DiscoverySettings) => api<import("./types").SettingsBundle>("/settings/discovery", { method: "PUT", body: JSON.stringify(body) }),
  systemHealth: () => api<import("./types").SystemHealth>("/settings/system-health"),
  hierarchy: () => api<import("./types").HierarchyCatalog>("/hierarchy"),
  createHierarchy: (kind: import("./types").HierarchyKind, body: Partial<import("./types").HierarchyItem>) => api<import("./types").HierarchyItem>(`/hierarchy/${kind}`, { method: "POST", body: JSON.stringify(body) }),
  updateHierarchy: (kind: import("./types").HierarchyKind, id: string, body: Partial<import("./types").HierarchyItem>) => api<import("./types").HierarchyItem>(`/hierarchy/${kind}/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deactivateHierarchy: (kind: import("./types").HierarchyKind, id: string) => api<void>(`/hierarchy/${kind}/${id}`, { method: "DELETE" }),
  discovery: (filters: import("./types").DiscoveryFilters = {}) => api<import("./types").DiscoveryPage>(`/discovery${queryString(filters)}`),
  discoveryDetail: (id: string) => api<import("./types").DiscoveredDevice>(`/discovery/${id}`),
  discoveryStats: () => api<import("./types").DiscoveryStats>("/discovery/stats"),
  runDiscovery: (range_scanned: string) => api<import("./types").DiscoveryRun>("/discovery/run", { method: "POST", body: JSON.stringify({ range_scanned }) }),
  approveDiscovery: (id: string, inventory: import("./types").InventoryApproval) => api<import("./types").ApprovalResponse>(`/discovery/${id}/approve`, { method: "POST", body: JSON.stringify(inventory) }),
  ignoreDiscovery: (id: string) => api<import("./types").DiscoveredDevice>(`/discovery/${id}/ignore`, { method: "POST" }),
  rejectDiscovery: (id: string, reason?: string) => api<import("./types").DiscoveredDevice>(`/discovery/${id}/reject`, { method: "POST", body: JSON.stringify({ reason: reason || null }) }),
  bulkApproveDiscovery: (items: import("./types").BulkApprovalItem[]) => api<import("./types").BulkActionResponse>("/discovery/bulk-approve", { method: "POST", body: JSON.stringify({ items }) }),
  bulkIgnoreDiscovery: (discovery_ids: string[]) => api<import("./types").BulkActionResponse>("/discovery/bulk-ignore", { method: "POST", body: JSON.stringify({ discovery_ids }) }),
  bulkRejectDiscovery: (discovery_ids: string[], reason?: string) => api<import("./types").BulkActionResponse>("/discovery/bulk-reject", { method: "POST", body: JSON.stringify({ discovery_ids, reason: reason || null }) }),
  exportDiscovery: () => download("/discovery/export"),
  importSessions: (filters: import("./types").ImportSessionFilters = {}) => api<import("./types").ImportSessionPage>(`/imports${queryString(filters)}`),
  importSession: (id: string) => api<import("./types").ImportSession>(`/imports/${id}`),
  uploadImport: (file: File, signal?: AbortSignal) => { const body = new FormData(); body.append("file", file); return api<import("./types").ImportUploadResponse>("/imports/device-inventory/upload", { method: "POST", body, signal }); },
  importColumns: (id: string, worksheet?: string) => api<import("./types").ImportColumnDetection>(`/imports/${id}/columns${queryString({ worksheet })}`),
  saveImportMapping: (id: string, mapping: Record<string, string | null>, worksheet?: string | null) => api<import("./types").ImportColumnDetection>(`/imports/${id}/mapping`, { method: "POST", body: JSON.stringify({ mapping, worksheet: worksheet || null }) }),
  validateImport: (id: string) => api<import("./types").ImportSession>(`/imports/${id}/validate`, { method: "POST" }),
  importRows: (id: string, filters: import("./types").ImportRowFilters = {}) => api<import("./types").ImportedDevicePage>(`/imports/${id}/rows${queryString(filters)}`),
  importRow: (sessionId: string, rowId: string) => api<import("./types").ImportedDevice>(`/imports/${sessionId}/rows/${rowId}`),
  importErrors: (id: string) => api<import("./types").ImportErrorReport>(`/imports/${id}/errors`),
  exportImportErrors: (id: string) => download(`/imports/${id}/errors/export`),
  cancelImport: (id: string) => api<import("./types").ImportSession>(`/imports/${id}/cancel`, { method: "POST" }),
  runImportMatching: (id: string) => api<import("./types").ImportSummary>(`/imports/${id}/match`, { method: "POST" }),
  recomputeImportMatches: (id: string) => api<import("./types").ImportSummary>(`/imports/${id}/matches/recompute`, { method: "POST" }),
  importMatches: (id: string, filters: import("./types").ImportMatchFilters = {}) => api<import("./types").ImportMatchPage>(`/imports/${id}/matches${queryString(filters)}`),
  importRowMatches: (sessionId: string, rowId: string) => api<import("./types").ImportMatchCandidate[]>(`/imports/${sessionId}/rows/${rowId}/matches`),
  importMergePlan: (sessionId: string, rowId: string, candidateId?: string) => api<import("./types").MergePlan>(`/imports/${sessionId}/rows/${rowId}/merge-plan${queryString({ candidate_id: candidateId })}`),
  acceptImportMatch: (sessionId: string, rowId: string, candidateId: string) => api<import("./types").ImportMatchCandidate>(`/imports/${sessionId}/rows/${rowId}/accept-match`, { method: "POST", body: JSON.stringify({ candidate_id: candidateId }) }),
  rejectImportMatch: (sessionId: string, rowId: string, candidateId: string) => api<import("./types").ImportMatchCandidate>(`/imports/${sessionId}/rows/${rowId}/reject-match`, { method: "POST", body: JSON.stringify({ candidate_id: candidateId }) }),
  markImportCreateNew: (sessionId: string, rowId: string) => api<import("./types").ImportedDevice>(`/imports/${sessionId}/rows/${rowId}/mark-create-new`, { method: "POST" }),
  markImportSkip: (sessionId: string, rowId: string) => api<import("./types").ImportedDevice>(`/imports/${sessionId}/rows/${rowId}/mark-skip`, { method: "POST" }),
  importLocationSuggestion: (sessionId: string, rowId: string) => api<import("./types").ImportLocationSuggestion>(`/imports/${sessionId}/rows/${rowId}/location-suggestion`),
  importLocationSuggestions: (sessionId: string) => api<import("./types").ImportLocationSuggestion[]>(`/imports/${sessionId}/locations`),
  reviewImportLocation: (sessionId: string, rowId: string, body: import("./types").LocationReviewInput) => api<import("./types").ImportLocationSuggestion>(`/imports/${sessionId}/rows/${rowId}/location-suggestion`, { method: "POST", body: JSON.stringify(body) }),
};
