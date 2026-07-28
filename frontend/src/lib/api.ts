import { clearAuthToken, getAuthToken } from "./auth";

// Same-origin by default; Vite and nginx proxy this path to FastAPI.
const API_URL = import.meta.env.VITE_API_URL ?? "/api/v1";

export class ApiError extends Error { status: number; constructor(message: string, status: number) { super(message); this.status = status; } }

const inFlightGets = new Map<string, Promise<unknown>>();

function errorDetailMessage(detail: unknown): string | undefined {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => typeof item === "object" && item !== null && "msg" in item && typeof item.msg === "string" ? item.msg : "Invalid value")
      .join(" ");
  }
  if (typeof detail === "object" && detail !== null && "message" in detail && typeof detail.message === "string") {
    return detail.message;
  }
  return undefined;
}

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
      const body: unknown = await response.json();
      if (typeof body === "object" && body !== null && "detail" in body) {
        message = errorDetailMessage(body.detail) ?? message;
      }
    } catch { /* non-JSON response */ }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function queryString(values: Record<string, string | number | boolean | undefined>) {
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
  setImportDisposition: (sessionId: string, rowId: string, body: {disposition:import("./types").FinalDisposition;approved_fields?:string[];approved_overwrites?:string[]}) => api<import("./types").ImportedDevice>(`/imports/${sessionId}/rows/${rowId}/disposition`, { method: "POST", body: JSON.stringify(body) }),
  importReadiness: (id: string) => api<import("./types").ImportReadiness>(`/imports/${id}/readiness`),
  importExecutionPlan: (id: string, persist = false) => api<import("./types").ImportReadiness>(`/imports/${id}/execution-plan${queryString({persist:persist ? "true" : undefined})}`),
  finalizeImport: (id: string, planVersion: number, idempotencyKey: string) => api<import("./types").ImportResults>(`/imports/${id}/finalize`, { method: "POST", body: JSON.stringify({plan_version:planVersion,idempotency_key:idempotencyKey,confirm_inventory_mutation:true,confirm_rollback_limits:true}) }),
  importResults: (id: string, page = 1) => api<import("./types").ImportResults>(`/imports/${id}/results${queryString({page,page_size:50})}`),
  importRollbackPreview: (id: string) => api<import("./types").RollbackPreview>(`/imports/${id}/rollback-preview`),
  rollbackImport: (id: string) => api<import("./types").ImportResults>(`/imports/${id}/rollback`, { method: "POST", body: JSON.stringify({confirmation:"ROLLBACK"}) }),
  retryFailedImport: (id: string) => api<import("./types").ImportResults>(`/imports/${id}/retry-failed`, { method: "POST" }),
  adOverview: () => api<import("./types").ADOverview>("/active-directory/overview"),
  adSettings: () => api<Record<string,unknown>>("/active-directory/settings"),
  adConnections: (filters: Record<string,string|number|undefined> = {}) => api<import("./types").ADPage<import("./types").ADConnection>>(`/active-directory/connections${queryString(filters)}`),
  adConnection: (id:string) => api<import("./types").ADConnection>(`/active-directory/connections/${id}`),
  createADConnection: (body:import("./types").ADConnectionInput) => api<import("./types").ADConnection>("/active-directory/connections", {method:"POST",body:JSON.stringify(body)}),
  updateADConnection: (id:string, body:Partial<import("./types").ADConnectionInput>) => api<import("./types").ADConnection>(`/active-directory/connections/${id}`, {method:"PATCH",body:JSON.stringify(body)}),
  disableADConnection: (id:string) => api<import("./types").ADConnection>(`/active-directory/connections/${id}/disable`, {method:"POST"}),
  updateADSecret: (id:string, secret:string) => api<import("./types").ADConnection>(`/active-directory/connections/${id}/secret`, {method:"POST",body:JSON.stringify({bind_secret:secret})}),
  testADConnection: (id:string) => api<import("./types").ADTestResult>(`/active-directory/connections/${id}/test`, {method:"POST"}),
  adRootDse: (id:string) => api<import("./types").ADRootDse>(`/active-directory/connections/${id}/root-dse`),
  adSyncConfig: (id:string) => api<import("./types").ADSyncConfig>(`/active-directory/connections/${id}/sync-config`),
  updateADSyncConfig: (id:string, body:Partial<import("./types").ADSyncConfig>) => api<import("./types").ADSyncConfig>(`/active-directory/connections/${id}/sync-config`, {method:"PUT",body:JSON.stringify(body)}),
  startADSync: (id:string, body:{sync_mode:"full"|"incremental";dry_run:boolean;object_types:string[]}) => api<{sync_run_id:string;status:string;warnings:string[]}>(`/active-directory/connections/${id}/sync`, {method:"POST",body:JSON.stringify(body)}),
  adSyncRuns: (filters:Record<string,string|number|undefined>={}) => api<import("./types").ADPage<import("./types").ADSyncRun>>(`/active-directory/sync-runs${queryString(filters)}`),
  adSyncRun: (id:string) => api<import("./types").ADSyncRun>(`/active-directory/sync-runs/${id}`),
  cancelADSync: (id:string) => api<import("./types").ADSyncRun>(`/active-directory/sync-runs/${id}/cancel`, {method:"POST"}),
  adSyncSummary: (id:string) => api<Record<string,unknown>>(`/active-directory/sync-runs/${id}/summary`),
  adObjects: (filters:Record<string,string|number|undefined>={}) => api<import("./types").ADPage<import("./types").ADObject>>(`/active-directory/objects${queryString(filters)}`),
  adObject: (id:string) => api<import("./types").ADObject>(`/active-directory/objects/${id}`),
  adObjectChanges: (id:string, page=1) => api<import("./types").ADPage<import("./types").ADChange>>(`/active-directory/objects/${id}/changes${queryString({page,page_size:50})}`),
  adMatches: (filters:Record<string,string|number|undefined>={}) => api<import("./types").ADPage<import("./types").ADMatch>>(`/active-directory/matches${queryString(filters)}`),
  runADMatching: (id:string, body={object_types:["user","computer"],recompute:false,dry_run:false}) => api<Record<string,unknown>>(`/active-directory/connections/${id}/match`, {method:"POST",body:JSON.stringify(body)}),
  adReconciliationPlan: (id:string) => api<Record<string,unknown>>(`/active-directory/objects/${id}/reconciliation-plan`),
  resolveADObject: (id:string, body:Record<string,unknown>) => api<Record<string,unknown>>(`/active-directory/objects/${id}/resolve`, {method:"POST",body:JSON.stringify(body)}),
  ignoreADObject: (id:string) => api<Record<string,unknown>>(`/active-directory/objects/${id}/ignore`, {method:"POST"}),
  adMappings: (connectionId:string, kind:string) => api<import("./types").ADMapping[]>(`/active-directory/connections/${connectionId}/mappings/${kind}`),
  createADMapping: (connectionId:string, kind:"departments"|"ous"|"roles", body:Record<string,unknown>) => api<import("./types").ADMapping>(`/active-directory/connections/${connectionId}/mappings/${kind}`, {method:"POST",body:JSON.stringify(body)}),
  deleteADMapping: (connectionId:string, kind:string, id:string) => api<void>(`/active-directory/connections/${connectionId}/mappings/${kind}/${id}`, {method:"DELETE"}),
  previewADMapping: (connectionId:string, kind:string, id:string) => api<{items:Array<Record<string,unknown>>;total:number;truncated:boolean}>(`/active-directory/connections/${connectionId}/mappings/${kind}/${id}/preview`),
  adReviewQueue: (filters:Record<string,string|number|undefined>={}) => api<import("./types").ADPage<Record<string,unknown>>>(`/active-directory/review-queue${queryString(filters)}`),
  snmpCredentials: (filters:Record<string,string|number|undefined>={}) => api<import("./types").SNMPPage<import("./types").SNMPCredential>>(`/snmp/credentials${queryString(filters)}`),
  snmpCredential: (id:string) => api<import("./types").SNMPCredential>(`/snmp/credentials/${id}`),
  createSNMPCredential: (body:import("./types").SNMPCredentialInput) => api<import("./types").SNMPCredential>("/snmp/credentials",{method:"POST",body:JSON.stringify(body)}),
  updateSNMPCredential: (id:string,body:Partial<import("./types").SNMPCredentialInput>) => api<import("./types").SNMPCredential>(`/snmp/credentials/${id}`,{method:"PATCH",body:JSON.stringify(body)}),
  rotateSNMPSecret: (id:string,body:{community?:string;authentication_secret?:string;privacy_secret?:string}) => api<import("./types").SNMPCredential>(`/snmp/credentials/${id}/secret`,{method:"POST",body:JSON.stringify(body)}),
  disableSNMPCredential: (id:string) => api<import("./types").SNMPCredential>(`/snmp/credentials/${id}/disable`,{method:"POST"}),
  snmpTargets: (filters:Record<string,string|number|undefined>={}) => api<import("./types").SNMPPage<import("./types").SNMPTarget>>(`/snmp/targets${queryString(filters)}`),
  snmpTarget: (id:string) => api<import("./types").SNMPTarget>(`/snmp/targets/${id}`),
  createSNMPTarget: (body:import("./types").SNMPTargetInput) => api<import("./types").SNMPTarget>("/snmp/targets",{method:"POST",body:JSON.stringify(body)}),
  updateSNMPTarget: (id:string,body:Partial<import("./types").SNMPTargetInput>) => api<import("./types").SNMPTarget>(`/snmp/targets/${id}`,{method:"PATCH",body:JSON.stringify(body)}),
  disableSNMPTarget: (id:string) => api<import("./types").SNMPTarget>(`/snmp/targets/${id}/disable`,{method:"POST"}),
  testSNMPTarget: (id:string) => api<import("./types").SNMPTargetTestResult>(`/snmp/targets/${id}/test`,{method:"POST",body:JSON.stringify({include_optional_identity:true})}),
  collectSNMPTarget: (id:string,groups:string[]) => api<{poll_run_id:string;accepted_groups:string[];status:string;warnings:string[]}>(`/snmp/targets/${id}/collect`,{method:"POST",body:JSON.stringify({groups})}),
  snmpPollingConfig: (id:string) => api<import("./types").SNMPPollingConfiguration>(`/snmp/targets/${id}/polling-config`),
  updateSNMPPollingConfig: (id:string,body:Partial<import("./types").SNMPPollingConfiguration>) => api<import("./types").SNMPPollingConfiguration>(`/snmp/targets/${id}/polling-config`,{method:"PUT",body:JSON.stringify(body)}),
  snmpPollRuns: (filters:Record<string,string|number|undefined>={}) => api<import("./types").SNMPPage<import("./types").SNMPPollRun>>(`/snmp/poll-runs${queryString(filters)}`),
  snmpPollRun: (id:string) => api<import("./types").SNMPPollRun>(`/snmp/poll-runs/${id}`),
  snmpPollResults: (id:string,page=1) => api<import("./types").SNMPPage<import("./types").SNMPMetric>>(`/snmp/poll-runs/${id}/results${queryString({page,page_size:100})}`),
  cancelSNMPPoll: (id:string) => api<import("./types").SNMPPollRun>(`/snmp/poll-runs/${id}/cancel`,{method:"POST"}),
  snmpProfiles: (filters:Record<string,string|number|undefined>={}) => api<import("./types").SNMPPage<import("./types").SNMPDeviceProfile>>(`/snmp/profiles${queryString(filters)}`),
  createSNMPProfile: (body:Record<string,unknown>) => api<import("./types").SNMPDeviceProfile>("/snmp/profiles",{method:"POST",body:JSON.stringify(body)}),
  updateSNMPProfile: (id:string,body:Record<string,unknown>) => api<import("./types").SNMPDeviceProfile>(`/snmp/profiles/${id}`,{method:"PATCH",body:JSON.stringify(body)}),
  snmpOids: (filters:Record<string,string|number|undefined>={}) => api<import("./types").SNMPPage<import("./types").SNMPOIDDefinition>>(`/snmp/oids${queryString(filters)}`),
  createSNMPOid: (body:Record<string,unknown>) => api<import("./types").SNMPOIDDefinition>("/snmp/oids",{method:"POST",body:JSON.stringify(body)}),
  updateSNMPOid: (id:string,body:Record<string,unknown>) => api<import("./types").SNMPOIDDefinition>(`/snmp/oids/${id}`,{method:"PATCH",body:JSON.stringify(body)}),
  snmpCandidates: (filters:Record<string,string|number|undefined>={}) => api<import("./types").SNMPPage<import("./types").SNMPDiscoveryCandidate>>(`/snmp/candidates${queryString(filters)}`),
  snmpCandidate: (id:string) => api<import("./types").SNMPDiscoveryCandidate>(`/snmp/candidates/${id}`),
  matchSNMPCandidate: (id:string) => api<import("./types").SNMPPage<import("./types").SNMPMatchCandidate>>(`/snmp/candidates/${id}/match`,{method:"POST"}),
  snmpCandidateMatches: (id:string) => api<import("./types").SNMPPage<import("./types").SNMPMatchCandidate>>(`/snmp/candidates/${id}/matches`),
  snmpOnboardingPlan: (id:string) => api<import("./types").SNMPOnboardingPlan>(`/snmp/candidates/${id}/onboarding-plan`),
  approveSNMPCandidate: (id:string,device:Record<string,unknown>,expected_updated_at?:string) => api<Record<string,unknown>>(`/snmp/candidates/${id}/approve`,{method:"POST",body:JSON.stringify({device,expected_updated_at})}),
  linkSNMPCandidate: (id:string,device_id:string,expected_updated_at?:string) => api<Record<string,unknown>>(`/snmp/candidates/${id}/link`,{method:"POST",body:JSON.stringify({device_id,expected_updated_at})}),
  enrichSNMPCandidate: (id:string,device_id:string,fields:string[],overwrite=false,expected_updated_at?:string) => api<Record<string,unknown>>(`/snmp/candidates/${id}/enrich`,{method:"POST",body:JSON.stringify({device_id,fields,overwrite,expected_updated_at})}),
  reviewSNMPCandidate: (id:string,action:"ignore"|"reject"|"restore",expected_updated_at?:string) => api<import("./types").SNMPDiscoveryCandidate>(`/snmp/candidates/${id}/${action}`,{method:"POST",body:JSON.stringify({expected_updated_at})}),
  snmpInterfaces: (filters:Record<string,string|number|undefined>={}) => api<import("./types").SNMPPage<import("./types").SNMPInterface>>(`/snmp/interfaces${queryString(filters)}`),
  snmpTargetInterfaces: (id:string,filters:Record<string,string|number|undefined>={}) => api<import("./types").SNMPPage<import("./types").SNMPInterface>>(`/snmp/targets/${id}/interfaces${queryString(filters)}`),
  snmpInterface: (id:string) => api<import("./types").SNMPInterface>(`/snmp/interfaces/${id}`),
  snmpInterfaceChanges: (id:string,page=1) => api<import("./types").SNMPPage<import("./types").SNMPInterfaceChange>>(`/snmp/interfaces/${id}/changes${queryString({page,page_size:50})}`),
  snmpInterfaceMetrics: (id:string,filters:Record<string,string|number|undefined>={}) => api<import("./types").SNMPPage<import("./types").SNMPMetric>>(`/snmp/interfaces/${id}/metrics${queryString(filters)}`),
  snmpMetrics: (filters:Record<string,string|number|undefined>={}) => api<import("./types").SNMPPage<import("./types").SNMPMetric>>(`/snmp/metrics${queryString(filters)}`),
  snmpTargetMetrics: (id:string,filters:Record<string,string|number|undefined>={}) => api<import("./types").SNMPPage<import("./types").SNMPMetric>>(`/snmp/targets/${id}/metrics${queryString(filters)}`),
  snmpMetricSummary: (id:string,metric_key:string) => api<import("./types").SNMPMetricSummary>(`/snmp/targets/${id}/metric-summary${queryString({metric_key})}`),
  snmpStateChanges: (filters:Record<string,string|number|undefined>={}) => api<import("./types").SNMPPage<import("./types").SNMPStateChange>>(`/snmp/state-changes${queryString(filters)}`),
  snmpRetentionPreview: () => api<import("./types").SNMPRetentionPreview>("/snmp/retention/preview"),
  runSNMPRetentionCleanup: () => api<import("./types").SNMPRetentionPreview>("/snmp/retention/cleanup",{method:"POST"}),
  snmpAlertRules: (filters:Record<string,string|number|boolean|undefined>={}) => api<import("./types").SNMPPage<import("./types").SNMPAlertRule>>(`/snmp/alert-rules${queryString(filters)}`),
  createSNMPAlertRule: (body:Record<string,unknown>) => api<import("./types").SNMPAlertRule>("/snmp/alert-rules",{method:"POST",body:JSON.stringify(body)}),
  updateSNMPAlertRule: (id:string,body:Record<string,unknown>) => api<import("./types").SNMPAlertRule>(`/snmp/alert-rules/${id}`,{method:"PATCH",body:JSON.stringify(body)}),
  previewSNMPAlertRule: (body:Record<string,unknown>) => api<{items:Array<{target_id:string;would_trigger:boolean;sample_count:number}>;estimated_alert_count:number}>("/snmp/alert-rules/preview",{method:"POST",body:JSON.stringify(body)}),
  snmpAlerts: (filters:Record<string,string|number|boolean|undefined>={}) => api<import("./types").SNMPPage<import("./types").SNMPAlertEvent>>(`/snmp/alerts${queryString(filters)}`),
  evaluateSNMPAlerts: (id:string) => api<Record<string,number>>(`/snmp/targets/${id}/evaluate-alerts`,{method:"POST"}),
  snmpSchedulerHealth: () => api<import("./types").SNMPSchedulerHealth>("/snmp/scheduler/health"),
  reconcileSNMPScheduler: () => api<Record<string,number>>("/snmp/scheduler/reconcile",{method:"POST"}),
  pauseSNMPPolling: (id:string) => api<Record<string,number>>(`/snmp/targets/${id}/polling/pause`,{method:"POST"}),
  resumeSNMPPolling: (id:string) => api<Record<string,number>>(`/snmp/targets/${id}/polling/resume`,{method:"POST"}),
  setSNMPMaintenance: (id:string,enabled:boolean,reason="") => api<import("./types").SNMPPollingConfiguration>(`/snmp/targets/${id}/maintenance${queryString({enabled,reason})}`,{method:"POST"}),
  topologies: (filters:Record<string,string|number|boolean|undefined>={}) => api<import("./types").TopologyPage<import("./types").Topology>>(`/topology${queryString(filters)}`),
  topology: (id:string) => api<import("./types").Topology>(`/topology/${id}`),
  createTopology: (body:Record<string,unknown>) => api<import("./types").Topology>("/topology",{method:"POST",body:JSON.stringify(body)}),
  updateTopology: (id:string,body:Record<string,unknown>) => api<import("./types").Topology>(`/topology/${id}`,{method:"PATCH",body:JSON.stringify(body)}),
  setDefaultTopology: (id:string) => api<import("./types").Topology>(`/topology/${id}/set-default`,{method:"POST"}),
  enableTopology: (id:string,enabled:boolean) => api<import("./types").Topology>(`/topology/${id}/${enabled?"enable":"disable"}`,{method:"POST"}),
  bootstrapTopology: (id:string,body:Record<string,unknown>) => api<Record<string,unknown>>(`/topology/bootstrap${queryString({topology_id:id})}`,{method:"POST",body:JSON.stringify(body)}),
  topologyGraph: (id:string,filters:Record<string,string|number|boolean|undefined>={}) => api<import("./types").TopologyGraph>(`/topology/${id}/graph${queryString(filters)}`),
  topologyStats: (id:string) => api<import("./types").TopologyStats>(`/topology/${id}/stats`),
  topologyNodes: (id:string,filters:Record<string,string|number|boolean|undefined>={}) => api<import("./types").TopologyPage<import("./types").TopologyNode>>(`/topology/${id}/nodes${queryString(filters)}`),
  topologyNode: (id:string,nodeId:string) => api<import("./types").TopologyNode>(`/topology/${id}/nodes/${nodeId}`),
  createTopologyNode: (id:string,body:Record<string,unknown>) => api<import("./types").TopologyNode>(`/topology/${id}/nodes`,{method:"POST",body:JSON.stringify(body)}),
  updateTopologyNode: (id:string,nodeId:string,body:Record<string,unknown>) => api<import("./types").TopologyNode>(`/topology/${id}/nodes/${nodeId}`,{method:"PATCH",body:JSON.stringify(body)}),
  hideTopologyNode: (id:string,nodeId:string,hide=true) => api<import("./types").TopologyNode>(`/topology/${id}/nodes/${nodeId}/${hide?"hide":"restore"}`,{method:"POST"}),
  topologyLinks: (id:string,filters:Record<string,string|number|boolean|undefined>={}) => api<import("./types").TopologyPage<import("./types").TopologyLink>>(`/topology/${id}/links${queryString(filters)}`),
  topologyLink: (id:string,linkId:string) => api<import("./types").TopologyLink>(`/topology/${id}/links/${linkId}`),
  createTopologyLink: (id:string,body:Record<string,unknown>) => api<import("./types").TopologyLink>(`/topology/${id}/links`,{method:"POST",body:JSON.stringify(body)}),
  updateTopologyLink: (id:string,linkId:string,body:Record<string,unknown>) => api<import("./types").TopologyLink>(`/topology/${id}/links/${linkId}`,{method:"PATCH",body:JSON.stringify(body)}),
  topologyLinkAction: (id:string,linkId:string,action:"confirm"|"suppress"|"restore") => api<import("./types").TopologyLink>(`/topology/${id}/links/${linkId}/${action}`,{method:"POST"}),
  topologySegments: (id:string) => api<import("./types").TopologyPage<import("./types").NetworkSegment>>(`/topology/${id}/segments?page_size=100`),
  topologyDependencies: (id:string) => api<import("./types").TopologyPage<import("./types").DeviceDependency>>(`/topology/${id}/dependencies?page_size=100`),
  topologyLayout: (id:string) => api<{items:import("./types").NodePosition[];total:number}>(`/topology/${id}/layout`),
  saveTopologyLayout: (id:string,body:import("./types").NodePosition[]) => api<{updated:number}>(`/topology/${id}/layout`,{method:"PUT",body:JSON.stringify(body)}),
  topologyNeighbors: (id:string,nodeId:string) => api<{node_id:string;nodes:import("./types").TopologyNode[];links:import("./types").TopologyLink[]}>(`/topology/${id}/neighbors/${nodeId}`),
  topologyPath: (id:string,source:string,target:string,pathType:string) => api<import("./types").TopologyPathResult>(`/topology/${id}/path-analysis${queryString({source_node_id:source,target_node_id:target,path_type:pathType,max_paths:5})}`),
  topologyImpact: (id:string,nodeId:string) => api<import("./types").TopologyImpact>(`/topology/${id}/impact-analysis${queryString({node_id:nodeId})}`),
  topologyOrphans: (id:string) => api<{items:import("./types").TopologyNode[];total:number}>(`/topology/${id}/orphans`),
  topologyInference: (id:string) => api<import("./types").TopologyInferenceState>(`/topology/${id}/inference`),
  runTopologyInference: (id:string,dryRun=false) => api<import("./types").TopologyInferenceRun>(`/topology/${id}/run-inference`,{method:"POST",body:JSON.stringify({dry_run:dryRun,include_dependencies:true,include_layer_suggestions:true})}),
  topologyConflicts: (id:string,filters:Record<string,string|number|undefined>={}) => api<import("./types").TopologyPage<import("./types").TopologyConflict>>(`/topology/${id}/conflicts${queryString(filters)}`),
  topologyReviewItems: (id:string,filters:Record<string,string|number|undefined>={}) => api<import("./types").TopologyPage<import("./types").TopologyReviewItem>>(`/topology/${id}/review-items${queryString(filters)}`),
  resolveTopologyReview: (id:string,itemId:string,action:"approve"|"reject"|"ignore",note="") => api<import("./types").TopologyReviewItem>(`/topology/${id}/review-items/${itemId}/${action}`,{method:"POST",body:JSON.stringify({note:note||null})}),
  topologyCandidateLinks: (id:string,filters:Record<string,string|number|undefined>={}) => api<import("./types").TopologyPage<import("./types").TopologyLink>>(`/topology/${id}/candidate-links${queryString(filters)}`),
  topologyCandidateLinkAction: (id:string,linkId:string,action:"confirm"|"reject"|"suppress") => api<import("./types").TopologyLink>(`/topology/${id}/candidate-links/${linkId}/${action}`,{method:"POST"}),
  topologySnapshots: (id:string,filters:Record<string,string|number|undefined>={}) => api<import("./types").TopologyPage<import("./types").TopologySnapshot>>(`/topology/${id}/snapshots${queryString(filters)}`),
  createTopologySnapshot: (id:string,body:Record<string,unknown>) => api<import("./types").TopologySnapshot>(`/topology/${id}/snapshots`,{method:"POST",body:JSON.stringify(body)}),
  topologySnapshotGraph: (id:string,snapshotId:string) => api<import("./types").TopologySnapshotGraph>(`/topology/${id}/snapshots/${snapshotId}/graph`),
  compareTopologySnapshot: (id:string,snapshotId:string) => api<import("./types").SnapshotComparison>(`/topology/${id}/comparison${queryString({snapshot_id:snapshotId})}`),
  topologyChanges: (id:string,filters:Record<string,string|number|undefined>={}) => api<import("./types").TopologyPage<import("./types").TopologyChange>>(`/topology/${id}/changes${queryString(filters)}`),
  topologySchedule: (id:string) => api<import("./types").TopologySchedule>(`/topology/${id}/schedule`),
  updateTopologySchedule: (id:string,body:Omit<import("./types").TopologySchedule,"id"|"topology_id"|"maintenance_mode"|"maintenance_reason"|"maintenance_started_at"|"maintenance_ends_at"|"last_scheduler_reconciliation_at"|"created_at"|"updated_at">) => api<import("./types").TopologySchedule>(`/topology/${id}/schedule`,{method:"PUT",body:JSON.stringify(body)}),
  pauseTopologySchedule: (id:string) => api<{paused_jobs:number}>(`/topology/${id}/schedule/pause`,{method:"POST"}),
  resumeTopologySchedule: (id:string) => api<{resumed_jobs:number}>(`/topology/${id}/schedule/resume`,{method:"POST"}),
  topologySchedulerStatus: (id:string) => api<import("./types").TopologySchedulerStatus>(`/topology/${id}/scheduler-status`),
  topologyHealth: (id:string) => api<import("./types").TopologyHealth>(`/topology/${id}/health`),
  topologyAnalytics: (id:string) => api<import("./types").TopologyAnalytics>(`/topology/${id}/analytics`),
  topologyOperationalRuns: (id:string,filters:Record<string,string|number|undefined>={}) => api<import("./types").TopologyPage<import("./types").TopologyOperationalRun>>(`/topology/${id}/operational-runs${queryString(filters)}`),
  topologyAlertRules: (filters:Record<string,string|number|boolean|undefined>={}) => api<import("./types").TopologyPage<import("./types").TopologyAlertRule>>(`/topology/alert-rules${queryString(filters)}`),
  createTopologyAlertRule: (body:Record<string,unknown>) => api<import("./types").TopologyAlertRule>("/topology/alert-rules",{method:"POST",body:JSON.stringify(body)}),
  updateTopologyAlertRule: (id:string,body:Record<string,unknown>) => api<import("./types").TopologyAlertRule>(`/topology/alert-rules/${id}`,{method:"PATCH",body:JSON.stringify(body)}),
  previewTopologyAlertRule: (id:string,topologyId:string) => api<{rule_id:string;would_trigger:boolean;evidence?:Record<string,unknown>}>(`/topology/alert-rules/${id}/preview${queryString({topology_id:topologyId})}`,{method:"POST"}),
  topologyAlerts: (filters:Record<string,string|number|boolean|undefined>={}) => api<import("./types").TopologyPage<import("./types").TopologyAlertEvent>>(`/topology/alerts${queryString(filters)}`),
  startTopologyMaintenance: (id:string,reason:string,ends_at?:string) => api<import("./types").TopologySchedule>(`/topology/${id}/maintenance/start`,{method:"POST",body:JSON.stringify({reason,ends_at:ends_at||null})}),
  endTopologyMaintenance: (id:string) => api<import("./types").TopologySchedule>(`/topology/${id}/maintenance/end`,{method:"POST"}),
  topologyReportSummary: (id:string) => api<{health:import("./types").TopologyHealth;analytics:import("./types").TopologyAnalytics;open_alerts:number;failed_runs:number}>(`/topology/${id}/reports/summary`),
  exportTopologyCsv: (id:string,kind:"nodes"|"links") => download(`/topology/${id}/exports/${kind}.csv`),
  topologyRetentionPreview: () => api<import("./types").TopologyRetentionPreview>("/topology/retention/preview"),
  runTopologyRetentionCleanup: () => api<import("./types").TopologyRetentionPreview>("/topology/retention/cleanup",{method:"POST"}),
  setTopologyBaseline: (id:string,snapshotId:string) => api<{snapshot_id:string;is_operational_baseline:boolean;is_protected:boolean}>(`/topology/${id}/snapshots/${snapshotId}/baseline`,{method:"POST"}),
};
