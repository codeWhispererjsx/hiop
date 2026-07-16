# HIOP Project Status

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
