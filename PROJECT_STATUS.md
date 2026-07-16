# HIOP Project Status

## Epic 12 — Performance optimization

The HIOP v1.0 performance pass is complete without feature or design changes.

- All pages use route-level lazy loading and code splitting. The initial shared JavaScript bundle decreased from 379.87 kB to 244.79 kB (35.6%), or from 109.51 kB to 78.15 kB gzip (28.6%).
- Concurrent identical authenticated GET requests are coalesced only while in flight, avoiding duplicate calls without retaining stale operational data.
- Shared request state ignores late responses after navigation, replacement requests, or unmount.
- Devices, Tickets, and Alerts defer expensive search filtering so typing remains responsive while preserving current filters and pagination.
- Dashboard metric queries were consolidated from seven database round trips to three.
- Audit summary metrics were consolidated from six queries to one, and the current-day predicate can use the audit timestamp index.
- Alembic revision `a71c8d9e4f20` adds targeted indexes for device hostname/IP, ticket status, active-alert ordering, audit chronology, and global/per-device scan chronology. Existing unique indexes already cover asset tags and user email addresses.
- The existing single WebSocket connection, cleanup, retry timer, authentication, and live-update behavior remain intact.

Verification passed: frontend lint, frontend production build, 10 backend contract tests, backend health/startup, Alembic upgrade/current-head checks, and authenticated browser loading of every primary module. Detailed measurements, rationale, and remaining scalability opportunities are in `PERFORMANCE_REPORT.md`.

## Sprint 11.1 — System stabilization and quality assurance

The first whole-application stabilization pass is complete. It reviewed the Dashboard, Devices, Network Operations Center, Alerts, Tickets, Users, Audit, Reports, Settings, Locations & Structure, shared authentication/API handling, routing, WebSocket lifecycle, and backend router ownership without adding new product functionality.

### Defects corrected

- Shared requests now reload when route/request dependencies change, eliminating stale details data between entity routes.
- The application shell maintains a single WebSocket connection across ordinary renders while still invoking the latest page callbacks.
- Dedicated Users and Audit routers are the sole owners of those APIs; obsolete duplicate handlers were removed from the operations router.
- The obsolete public/staff registration route and its dead frontend endpoint metadata were removed. Administrator user management remains the supported account-creation workflow.
- Scheduler diagnostics now use structured logging rather than direct standard-output prints.
- Dead imports and compatibility code associated with the removed routes were removed.

The complete defect register, severity, root cause, resolution, and status are recorded in `BUG_TRACKER.md`.

### Verification scope

- Frontend TypeScript production build and ESLint.
- Backend compilation/import and targeted `unittest` discovery from `backend/tests`.
- Authenticated API checks across Dashboard, Devices, Network, Alerts, Tickets, Users, Audit, Reports, Settings, and hierarchy endpoints.
- Invalid-token rejection and removal of the obsolete registration route.
- Browser route coverage for application modules and representative create, detail, and edit pages, including logout/login behavior, performed while the local services were reachable.

### Remaining issues and production recommendations

- Clear the orphaned local Windows listener on `127.0.0.1:8000` (normally by restarting the development machine) before repeating the complete browser mutation workflow. The active FastAPI process itself was independently healthy; no misleading application workaround was committed.
- Modularize the large shared frontend stylesheet only as a future maintainability task; it does not prevent a successful production build.
- Before production, add automated browser regression tests for authentication and the highest-risk create/edit/retire/close/deactivate workflows, run them against an isolated test database, and add them to CI.
- Continue removing compatibility fields only through planned migrations; do not combine schema cleanup with stabilization releases.

## Devices module

The Devices module is complete for the backend capabilities currently available:

- Authenticated device inventory from `GET /api/v1/devices/` with instant search, status and department filters, and 10-row client-side pagination.
- Authenticated device details from `GET /api/v1/devices/{device_id}`.
- Validated, reusable Add/Edit form covering every field in `DeviceCreate` and `DeviceUpdate`.
- Device creation through `POST /api/v1/devices/` and updates through `PUT /api/v1/devices/{device_id}`.
- Confirmed soft retirement through `DELETE /api/v1/devices/{device_id}`. The backend changes the status to `Retired`; it does not delete the row or related history.
- Overview, Scan History, Alerts, Tickets, and Audit Trail views with independent loading, empty, error, and retry states.
- JWT handling, protected routing, WebSocket status refreshes, responsive layouts, light/dark themes, and HIOP `#C29F04` branding remain active.

## Phase 1 foundation

Phase 1A and Phase 1B are implemented and migrated through Alembic revision `e4a19c7b2d50`:

- `Device.inventory_status` now owns lifecycle values (`Active`, `Inactive`, `Retired`).
- `Device.network_status` now owns monitoring values (`Online`, `Offline`, `Unknown`).
- The legacy `Device.status` field remains temporarily for backward compatibility but is no longer changed by network scans.
- Tickets have a nullable `device_id` foreign key with `ON DELETE SET NULL` semantics.
- Automated offline tickets are linked directly to their device.
- Legacy tickets are linked only when an existing hostname, asset tag, IP address, or serial number produces a match; unmatched records remain unlinked.
- Exact authenticated device history endpoints now exist for scans, alerts, tickets, and audit logs.
- Properties, buildings, floors, rooms, departments, and network zones are normalized into managed tables.
- Devices have nullable `department_id`, `room_id`, and `network_zone_id` foreign keys with `ON DELETE SET NULL` compatibility semantics.
- Existing nonblank department and location values were conservatively backfilled without inventing property, building, or floor assignments.
- Authenticated hierarchy catalog APIs and admin-only create, update, and deactivate APIs are available under `/api/v1/hierarchy`.
- The frontend includes a responsive Locations & Structure administration screen and hierarchy-backed Device form controls.
- Legacy device `department` and `location` strings remain synchronized for current clients, search, filters, and reports.
- Case-insensitive database uniqueness is enforced for hierarchy names, network-zone CIDRs are unique, and CIDR/VLAN inputs are validated.

### Status semantics

Inventory and network states are now separate. A later compatibility migration can remove the legacy `status` column after all external clients have moved to `inventory_status` and `network_status`.

## Device history API coverage

The frontend integrates every real history API currently present:

- `GET /api/v1/devices/{device_id}/scans`.
- `GET /api/v1/devices/{device_id}/alerts`.
- `GET /api/v1/devices/{device_id}/tickets` using the direct ticket foreign key.
- `GET /api/v1/devices/{device_id}/audit-logs`. This endpoint remains role-restricted to admins and technicians.

### Remaining compatibility work

- Remove the legacy `Device.status` compatibility field after downstream clients migrate.
- Remove legacy device `department` and `location` text columns only after downstream clients use normalized relationships.

## Sprint 4 — Network Operations Center

The Network Operations Center is implemented at `/network` using only persisted backend data:

- Live summary cards for total, Online, Offline, Unknown, last scan time, average latest response time, and unacknowledged alerts.
- A responsive device table combining inventory data with each device's latest recorded scan, including clear Retired handling.
- Authenticated Scan All, Scan Single Device, and Refresh Status controls with duplicate-action prevention.
- Honest running, completed, and failed scan states with an indeterminate progress indicator.
- Recent persisted scan history and network alerts linked to their device details pages.
- WebSocket-driven status refreshes with automatic reconnect behavior and a visible lost-connection warning.
- Independent loading, empty, API-error, unauthorized, and backend-unavailable behavior through the shared API layer.

### Network APIs used

- `GET /api/v1/devices/`
- `GET /api/v1/network/history?limit=100`
- `POST /api/v1/network/scan`
- `POST /api/v1/network/scan-all`
- `GET /api/v1/alerts`
- `WS /ws/dashboard`

### Remaining network backend gap

`POST /api/v1/network/scan-all` is a synchronous request and does not expose job progress or emit per-device scan-completion events. The NOC therefore displays a truthful indeterminate running state followed by completed or failed. Determinate progress would require a job-based endpoint such as `POST /api/v1/network/scan-jobs`, returning `{ id, status, total_devices, completed_devices, failed_devices }`, plus job progress events over the existing WebSocket.

## Sprint 5 — Enterprise Alerts Management

The Alerts Management module is implemented at `/alerts` using persisted scanner, device, ticket, scan, audit, and WebSocket data:

- Summary cards for total, active, acknowledged, critical, and today's alerts; resolved is explicitly shown as unavailable rather than fabricated.
- A responsive alert queue with real device metadata, status transitions, messages, acknowledgement state, and operational severity derived from the real transition (`Offline` = Critical; recovery = Informational).
- Combined search, severity, acknowledgement status, department, device, and local-date filters.
- On-demand details showing the related device, latest scan, device-related ticket, alert audit activity, and a chronological timeline.
- Real acknowledgement through the existing authenticated API with duplicate-action prevention and toast feedback.
- WebSocket-driven alert refresh and new-alert notification without polling, plus Connected, Reconnecting, and Offline states.
- Real device and ticket navigation, responsive table overflow, loading, empty, unauthorized, network-error, and backend-unavailable handling.

### Alert APIs used

- `GET /api/v1/alerts`
- `PATCH /api/v1/alerts/{alert_id}/acknowledge`
- `GET /api/v1/devices/`
- `GET /api/v1/devices/{device_id}/scans`
- `GET /api/v1/tickets/`
- `GET /api/v1/audit-logs`
- `WS /ws/dashboard`

### Missing alert backend capabilities

The existing alert table contains `device_id`, previous/current status, message, creation time, and acknowledgement boolean only. Complete lifecycle support requires:

1. Persisted alert fields such as `alert_type`, `severity`, `state`, `acknowledged_at`, `acknowledged_by`, `resolved_at`, `resolved_by`, and nullable `ticket_id`.
2. `GET /api/v1/alerts/{alert_id}` returning the alert plus exact device, ticket, scan, audit, and timeline relationships.
3. `PATCH /api/v1/alerts/{alert_id}/resolve`, returning the updated alert and recording a resolution audit entry.
4. A direct alert-to-ticket relationship instead of device-level correlation.
5. A WebSocket `alert_created` event containing the persisted alert identifier and complete alert payload. The current `device_status_changed` event triggers one authenticated alert refresh; it does not require polling.

These changes require an Alembic migration, updates to `backend/app/models/alert.py`, response schemas under `backend/app/schemas/`, lifecycle routes in `backend/app/operations/routes.py`, and richer event construction in `backend/app/services/network_service.py`.

## Epic 6 — Enterprise Ticket Management

The Tickets module is complete for the ticket capabilities currently exposed by FastAPI:

- Real-data overview metrics for total, Open, In Progress, Closed, High-priority, and unassigned tickets.
- Responsive ticket table with reporter, assignee, created/updated timestamps, optional device relationship, status/priority badges, and deep links.
- Combined title/description search plus status, priority, real assignee, and created-date filters with ten-row client-side pagination.
- Reusable validated create/edit form for title, description, supported Low/Medium/High priority, and the existing optional `device_id` relationship.
- Deep-linked ticket details with real device context, reporter/assignee names, audit-backed chronological activity, loading/error/not-found states, and no fabricated alert relationship.
- Real assignment to active admin/technician accounts, role-aware close/delete controls, confirmation dialogs, duplicate-action prevention, API errors, and success notifications.
- Reopen through the existing supported `PUT /tickets/{ticket_id}` status update operation.
- Dashboard ticket cards now navigate to real ticket details.
- JWT handling, shared API errors, protected routing, WebSocket connectivity, light/dark themes, responsive behavior, and `#C29F04` branding remain intact.

The backend now exposes `GET /api/v1/tickets/{ticket_id}` and includes the existing PostgreSQL `updated_at` field in `TicketResponse`.

### Ticket APIs used

- `GET /api/v1/tickets/`
- `GET /api/v1/tickets/{ticket_id}`
- `POST /api/v1/tickets/`
- `PUT /api/v1/tickets/{ticket_id}`
- `PATCH /api/v1/tickets/{ticket_id}/assign`
- `PATCH /api/v1/tickets/{ticket_id}/close`
- `DELETE /api/v1/tickets/{ticket_id}`
- `GET /api/v1/users`
- `GET /api/v1/auth/me`
- `GET /api/v1/devices/`
- `GET /api/v1/audit-logs`

### Ticket authorization

- Authenticated users may list, view, create, and update tickets.
- Admins and technicians may assign and close tickets.
- Admins may delete tickets and access the full users directory.
- The UI hides role-restricted lifecycle actions, while FastAPI remains the source of truth.
- The current users-list endpoint is admin-only, so a technician can call the assignment endpoint but cannot independently load the eligible-user directory. A role-scoped `GET /api/v1/users/eligible-assignees` endpoint should allow admins and technicians and return `[{ id, username, role, is_active }]`.

### Missing ticket backend capabilities

- Comments: add `GET/POST /api/v1/tickets/{ticket_id}/comments`, returning `[{ id, ticket_id, author_id, body, created_at, updated_at }]`.
- Attachments: add authenticated upload/list/delete endpoints under `/api/v1/tickets/{ticket_id}/attachments`, returning metadata such as `{ id, filename, content_type, size, uploaded_by, created_at }`.
- Direct alert relationship: add nullable `alert_id` or a ticket-alert association table and expose identifiers in both response schemas.
- SLA timers: persist response/resolution targets, breach state, and service timestamps instead of calculating unsupported deadlines in the frontend.
- Full status history: current audit entries record actions but not structured before/after values. Add `GET /api/v1/tickets/{ticket_id}/activity`, returning ordered typed events with actor, prior state, new state, and timestamp.
- Explicit reopen lifecycle: reopening works through the supported update operation but is logged as `UPDATE_TICKET`. A dedicated `PATCH /api/v1/tickets/{ticket_id}/reopen` should enforce roles and write `REOPEN_TICKET`.
- Ticket-specific WebSocket events: the existing socket only emits device status changes. Recommended persisted events are `ticket_created`, `ticket_updated`, `ticket_assigned`, `ticket_closed`, `ticket_reopened`, and `ticket_deleted` with ticket ID and current state.

### Epic 6 verification

A uniquely named runtime ticket was created against PostgreSQL, refreshed, edited, linked to a real device, assigned to a real eligible administrator, closed, reopened, filtered, and deleted. Create/update/assign/close/delete audit entries were verified, counts returned to their original values after cleanup, and no verification ticket remains.

### Next recommended epic

Epic 7 should add the missing service-desk collaboration and lifecycle backend contracts: eligible-assignee directory, structured ticket activity, comments, attachments, direct alert relationships, SLA policy/timers, explicit reopen, and ticket WebSocket events.

## Epic 7 — Users and Role Management

Epic 7 is complete for the account and authorization capabilities currently supported by HIOP:

- Real PostgreSQL user metrics, responsive directory, combined username/email search, supported-role and active-state filters, and ten-row client pagination.
- Reusable validated create/edit forms, user details, role changes, account activation/deactivation, and administrator-set temporary passwords.
- Real current-user identity remains sourced from `GET /api/v1/auth/me`; no hardcoded administrator identity or password data is displayed.
- Thin FastAPI routes backed by a transactional user service, case-insensitive uniqueness checks, secure existing password hashing, safe API errors, and audit entries for every management action.
- Backend-enforced admin authorization, self-deactivation prevention, last-active-admin protection, soft account deactivation, and inactive-login rejection.
- Ticket assignment now accepts only active administrators and technicians. Existing ticket references remain intact when an account is deactivated.
- Loading, empty, filtered-empty, unauthorized, not-found, conflict, validation, backend-unavailable, confirmation, and success states are represented without dummy users.
- JWT routing, WebSockets, light/dark themes, responsive application shell, and restrained `#C29F04` branding remain intact.

### User APIs added or used

- `GET /api/v1/users/roles`
- `GET /api/v1/users/eligible-assignees`
- `GET /api/v1/users`
- `GET /api/v1/users/{user_id}`
- `POST /api/v1/users`
- `PATCH /api/v1/users/{user_id}`
- `PATCH /api/v1/users/{user_id}/status`
- `PATCH /api/v1/users/{user_id}/role`
- `POST /api/v1/users/{user_id}/reset-password`
- `DELETE /api/v1/users/{user_id}` (compatibility soft-deactivation; no physical deletion)
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/login`
- `GET /api/v1/audit-logs`

### Roles and authorization

The existing backend supports `admin`, `technician`, and `staff`. Only administrators may list and manage the full user directory, create users, change roles, change account status, or set another user's temporary password. Administrators and technicians may load the active eligible-assignee directory. FastAPI remains the authorization source of truth even when the UI hides unavailable controls.

Safety rules prevent self-deactivation and prevent deactivation or demotion of the last active administrator. User records are never physically deleted by the management API. Password hashes are excluded from response schemas and password/token values are excluded from audit descriptions.

### Epic 7 verification

A uniquely named technician was created in PostgreSQL, refreshed, edited, changed through supported roles, deactivated, reactivated, and given a new temporary password. Runtime HTTP checks confirmed inactive login returns 401, the old password returns 401 after reset, the new password authenticates while active, and inactive users disappear from eligible ticket assignees. Audit entries for create, update, role change, activation, deactivation, and password reset were verified. The safe verification account remains inactive for traceability.

No database migration was required because username, email, hashed password, role, active state, and timestamps already existed in the user model.

### Known identity gaps

- Forgot-password email delivery and signed, expiring reset tokens
- Email verification
- Persisted last-login/login-history data
- Session listing and revocation
- Refresh-token rotation
- Multi-factor authentication
- Custom role and permission definitions beyond the supported fixed roles

### Next recommended epic

Epic 8 should implement reporting, analytics, and compliance exports across devices, scans, alerts, tickets, users, and audit activity using real aggregate APIs and role-aware access.

## Epic 8 — Enterprise Audit Center

Epic 8 is complete for the immutable audit data currently persisted by HIOP:

- Admin-only, read-only audit APIs with server-side search, combined filters, date range validation, sort order, 25/50/100-row pagination, details lookup, and full-filtered CSV export.
- Real overview counts for total events, events today, user actions, device actions, ticket actions, and supported security-related user administration events.
- Responsive Audit Center table on desktop and card presentation on narrow screens, with readable action/entity badges, long-description handling, loading/error/empty/filtered-empty states, refresh, and reset controls.
- Debounced global search across actor, stored action, entity type, entity ID, and description. Actor, action, and entity options are derived from PostgreSQL values rather than invented lists.
- Immutable detail modal retaining the raw stored action and providing safe navigation for retained Device and User records. Ticket events deliberately omit navigation because deleted tickets may no longer exist; Alert details currently use an in-page panel rather than a stable route.
- Excel-compatible UTF-8 CSV export for the complete active filter set, including an export-generation timestamp and safe filename. Tokens, passwords, hashes, and request payloads are not exported.
- Manual refresh is used because the existing WebSocket only carries device-status events; no audit events are fabricated.

### Audit APIs added

- `GET /api/v1/audit-logs`
- `GET /api/v1/audit-logs/{audit_id}`
- `GET /api/v1/audit-logs/export`

The list and export endpoints support `actor`, `action`, `entity_type`, `entity_id`, `start_date`, `end_date`, `search`, and `sort_order`. The list additionally supports `page` and `page_size`. Results default to newest first. Invalid ranges and out-of-range pages return HTTP 400, missing details return 404, and non-admin access returns 403.

### Audit authorization and immutability

Audit Center access is restricted to administrators by FastAPI. The frontend remains protected by JWT routing, but backend enforcement is authoritative. No edit, delete, clear-history, or retention controls exist. No schema migration was required because the existing audit table already stores ID, actor, action, entity type, entity ID, description, and timestamp.

### Current audit coverage

- Devices: create, update, and soft retirement
- Tickets: create, update, assign, close, and delete
- Users: create, update, role change, activate, deactivate, and administrator password reset
- Alerts: acknowledgement
- Hierarchy: create, update, and deactivate
- Monitoring settings: update

These writes use the existing transaction so the mutation and audit record commit or roll back together. Read operations are not logged.

### Missing audit support and limitations

- Authentication login success/failure is not audited. A future authentication service should record safe outcome events without storing passwords, tokens, or full credential payloads.
- Logout/token revocation cannot be audited because the project has no server-side session revocation endpoint.
- Alert resolution and alert-to-ticket creation are unavailable because those lifecycle endpoints and relationships do not exist.
- Manual scan start/completion is not intentionally audited; high-volume device status changes remain scanner/alert data rather than noisy governance records.
- The audit model has no IP address, request path, HTTP method, structured outcome, metadata, or correlation ID fields.
- No retention/archival policy, tamper-evident hash chain, external SIEM integration, or `audit_log_created` WebSocket event exists.

### Epic 8 verification

Both FastAPI and Vite were running. Real PostgreSQL verification confirmed 68 events at test time, 25-row pagination, newest-first ordering, details lookup, actor/entity/search filtering, full-filtered CSV content, and HTTP 403 for a real non-admin technician. The technician was re-deactivated after the authorization check. Browser verification confirmed combined User plus “deactivated” filtering, detail loading, safe related-user navigation, CSV success notification, light/dark themes, a 390px layout without horizontal overflow, and no console warnings or errors.

### Next recommended epic

Epic 9 should implement enterprise reporting and compliance dashboards, using server-side aggregates and scheduled, role-scoped exports across devices, scans, alerts, tickets, users, and audit events.

## Epic 9 — Enterprise Reports & Export Center

Epic 9 is complete for the operational data and historical records currently persisted by HIOP:

- An administrator-only Reports dashboard provides real, date-scoped cards for Device Inventory, Network Status, Alerts, Tickets, Users, and Audit reports.
- Each active report is loaded on demand from PostgreSQL and supports debounced search, applicable combined filters, sortable columns, and server-side 25/50/100-row pagination.
- Reporting periods include Today, Last 7 Days, Last 30 Days, Last 90 Days, and a validated custom range. The selected period applies to dashboard totals, report rows, metrics, charts, and exports.
- Real charts cover device network status, devices by department/type, network-health history, alerts by severity/department/day, ticket status/priority/assignment/day, user roles, and audit entity activity. The charts are reusable accessible React/CSS/SVG components; no chart dependency was already installed, and adding Recharts was blocked by the local package registry's self-signed certificate without weakening TLS validation.
- Full filtered Excel-compatible UTF-8 CSV export is available for every report. Filenames include the report name, date, and time; exports include generation metadata and never include JWTs, passwords, hashes, or request payloads.
- Browser printing uses report-specific print styles. Real record links connect devices, tickets, and users to their details; alert, audit, and network records link to their established module pages. Network, ticket, and critical-alert summary values provide filter-aware navigation.
- Loading, empty, filtered-empty, invalid-date, unauthorized, backend-unavailable, and export failure states are handled without blank pages.

### Reports APIs added

- `GET /api/v1/reports/summary`
- `GET /api/v1/reports/{report_name}`
- `GET /api/v1/reports/{report_name}/export`

Supported report names are `devices`, `network`, `alerts`, `tickets`, `users`, and `audit`. The list and export routes accept `start_date`, `end_date`, `search`, `status`, `department`, `category`, `sort_by`, and `sort_order`; list responses additionally accept `page` and `page_size`. All endpoints require the admin role. No migration was required.

### Reports limitations

- Alert resolution is not represented because the backend stores only acknowledgement state. Critical severity is transparently derived from an alert whose real current network status is `Offline`; no unsupported severity records are invented.
- Network trends use the existing `network_scans` history. Devices without a scan in the active period correctly show unavailable scan/response values.
- CSV is the supported Excel-compatible format. Native XLSX and PDF generation were not added because the project has no reliable existing dependency; browser print remains available.
- “Last generated” is the real timestamp of the current report request. Scheduled jobs, persisted report runs, emailed reports, and report templates do not yet exist.
- The existing WebSocket carries operational status changes, not report events. Reports refresh on navigation/filter changes and do not add polling or duplicate socket connections.

### Epic 9 verification

FastAPI and Vite were running during verification. Real PostgreSQL responses loaded all six report types, including 7 devices, 807 scan records, 12 alerts, 10 tickets, 4 users, and 70 audit events at final API verification time (the live scanner continues to add scan rows). Every CSV endpoint returned HTTP 200 with `text/csv`, unauthenticated access returned HTTP 401, and all six report views rendered through the browser without blank/error states. Search/filter behavior, network history charts, cross-module links, and light/dark theme switching were exercised. Frontend lint and the production build pass. Backend import, compilation, startup, health, and OpenAPI route registration pass; automated Python tests could not run because `pytest` is not installed in the project virtual environment.

### Next recommended epic

Epic 10 should focus on secure notification delivery and integrations: configurable alert channels, scheduled report delivery, delivery history, retry policies, and role-scoped subscription preferences.

## Epic 10 — Enterprise Settings & Administration

Epic 10 is complete for the safe runtime configuration currently supported by HIOP:

- Administrator-only, database-backed General, Organization, Network/Scanner, and Notification policy settings use explicit Pydantic schemas and audited transactions.
- Authenticated public branding supplies the saved property name to the application header without exposing administration data or secrets.
- Existing normalized departments and rooms are displayed from PostgreSQL and managed through the established Locations & Structure module. At verification time the real departments were exactly `Front Office` and `IT`.
- Scanner configuration enforces a private approved CIDR, rejects out-of-scope range scans, validates a minimum five-minute schedule, reloads the single APScheduler job safely, and applies saved ping timeout and automatic alert/ticket choices.
- Email configuration remains environment-only. The UI exposes configuration status and safe transport metadata but never returns or edits SMTP passwords.
- Appearance supports persistent Light, Dark, and System preferences without a startup theme flash. `#C29F04` remains the fixed brand accent.
- System Health reports real API, PostgreSQL, scheduler, WebSocket, email configuration, last scan, version, environment, and server time without credentials or internal paths.
- Backup & Maintenance honestly documents the PostgreSQL operating procedure; HIOP does not expose fake backup controls, destructive restores, arbitrary SQL, or shell execution.

### Epic 10 endpoints

- `GET /api/v1/settings`
- `GET /api/v1/settings/public`
- `PUT /api/v1/settings/general`
- `PUT /api/v1/settings/organization`
- `PUT /api/v1/settings/network`
- `PUT /api/v1/settings/notifications`
- `GET /api/v1/settings/system-health`

No new migration was required: Epic 10 extends the existing `system_settings` key/value table using an explicit allow-listed schema. Deployment secrets remain in environment configuration.

### Epic 10 verification

Frontend lint and production build pass. FastAPI compilation, import, startup, OpenAPI registration, health checks, and real PostgreSQL persistence pass. A safe default-page-size change persisted after a fresh request and was restored. Health returned Healthy, Connected database, and Running scheduler. An external `8.8.8.0/24` scan attempt returned HTTP 422. Unauthenticated Settings access returned HTTP 401. Browser verification covered real General values, the two real departments, live health, successful save notification, and Light/Dark/System appearance controls.

### Settings limitations and recommended stabilization

Runtime SMTP credential changes, secure test email, logo uploads, automated backup/restore, multi-property profiles, server-side personal preferences, refresh tokens, MFA, session revocation, custom permissions, and login-failure auditing remain unavailable. The next stabilization phase should add automated tests to the project virtual environment, an external secrets manager, and a deployment-tested backup/restore runbook before production rollout.
