# HIOP API contract

Base URL: `http://127.0.0.1:8000/api/v1`

All endpoints except login require `Authorization: Bearer <JWT>`. The interactive OpenAPI contract is available at `/docs` while FastAPI is running.

## Settings and administration

Settings mutations and system health are administrator-only. `GET /api/v1/settings/public` is available to authenticated users for non-sensitive branding.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/settings` | Read the explicit non-secret settings bundle |
| GET | `/settings/public` | Read application and property branding |
| PUT | `/settings/general` | Update global display and formatting defaults |
| PUT | `/settings/organization` | Update organization profile |
| PUT | `/settings/network` | Update validated scanner and scheduler settings |
| PUT | `/settings/notifications` | Update notification policy without SMTP secrets |
| GET | `/settings/system-health` | Read live secret-safe component health |

The Settings API never accepts arbitrary keys and never returns secret keys, database credentials, email passwords, tokens, hashes, private keys, or connection strings.

## Implemented endpoints

- Authentication: `POST /auth/login`, `GET /auth/me`, admin-only `POST /auth/register`
- Dashboard: `GET /dashboard/`
- Devices: `GET/POST /devices/`, `GET/PUT/DELETE /devices/{id}` (delete retires the asset)
- Monitoring: `POST /network/scan`, `POST /network/scan-all`, `POST /network/scan-range`, `GET /network/history`
- Tickets: `GET/POST /tickets/`, `PUT/DELETE /tickets/{id}`, `PATCH /tickets/{id}/assign`, `PATCH /tickets/{id}/close`
- Alerts: `GET /alerts`, `PATCH /alerts/{id}/acknowledge`
- Users: admin-only `GET /users`, `PATCH/DELETE /users/{id}`
- Audit: admin/technician `GET /audit-logs`
- Settings: `GET /settings`, admin-only `PUT /settings`
- Live events: WebSocket `/ws/dashboard`

## Data and migration requirements

Migration `f4c8e0a4b321` adds persistent alert acknowledgement and the `system_settings` table. Run `alembic upgrade head` before starting the updated API.

See [`frontend/MISSING_API.md`](../frontend/MISSING_API.md) for backend contracts required by future workflows. The frontend does not fabricate data for those features.
