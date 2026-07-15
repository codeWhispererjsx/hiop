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

### Status semantics

The current backend stores inventory lifecycle values (`Active`, `Inactive`, `Retired`) and monitoring values (`Online`, `Offline`) in the same `Device.status` column. The UI labels Online/Offline as network state and Retired as inventory state, but a full separation requires distinct backend fields such as `inventory_status` and `network_status` in:

- `backend/app/models/device.py`
- `backend/app/schemas/device.py`
- `backend/app/services/device_service.py`
- `backend/app/services/network_service.py`
- a new Alembic migration under `backend/alembic/versions/`

## Device history API coverage

The frontend integrates every real history API currently present:

- `GET /api/v1/network/history?limit=500`, filtered by `device_id`.
- `GET /api/v1/alerts`, filtered by `device_id`.
- `GET /api/v1/audit-logs`, filtered by `entity_type == "Device"` and `entity_id == device_id`. This endpoint correctly remains role-restricted to admins and technicians.
- `GET /api/v1/tickets/`, matched against hostname, asset tag, IP address, or serial number because tickets currently have no device relationship.

### Missing endpoints for exact device history

These endpoints do not currently exist. The frontend does not fabricate their responses.

1. `GET /api/v1/devices/{device_id}/scans`

   Expected response:

   ```json
   [{"id":"uuid","device_id":"uuid","ip_address":"string","status":"string","response_time":12.5,"scanned_at":"ISO-8601 timestamp"}]
   ```

   Add the route/query in `backend/app/devices/routes.py` (or `backend/app/scanner/routes.py`) and expose `scanned_at` in `backend/app/schemas/network_scan.py`.

2. `GET /api/v1/devices/{device_id}/alerts`

   Expected response:

   ```json
   [{"id":"uuid","device_id":"uuid","previous_status":"string","current_status":"string","message":"string","created_at":"ISO-8601 timestamp","acknowledged":false}]
   ```

   Add the route/query in `backend/app/devices/routes.py` or a `device_id` query parameter in `backend/app/operations/routes.py`.

3. `GET /api/v1/devices/{device_id}/tickets`

   Expected response:

   ```json
   [{"id":"uuid","device_id":"uuid","title":"string","description":"string","priority":"Medium","status":"Open","reported_by":"user-id","assigned_to":null,"created_at":"ISO-8601 timestamp"}]
   ```

   This requires a nullable `device_id` foreign key in `backend/app/models/ticket.py`, matching fields in `backend/app/schemas/ticket.py`, assignment when automated tickets are created in `backend/app/services/network_service.py`, filtering in `backend/app/tickets/routes.py`, and an Alembic migration.

4. `GET /api/v1/devices/{device_id}/audit-logs`

   Expected response:

   ```json
   [{"id":"uuid","actor":"string","action":"string","entity_type":"Device","entity_id":"uuid","description":"string","created_at":"ISO-8601 timestamp"}]
   ```

   Add the route/query in `backend/app/devices/routes.py` or a device/entity filter in `backend/app/operations/routes.py`.
