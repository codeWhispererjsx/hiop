# Backend APIs still required

The current React application contains no mock operational records. Every active page reads or writes through FastAPI. The following product features are intentionally not rendered as working controls because their backend contracts do not exist yet:

| Future workflow | Required backend contract |
| --- | --- |
| Password change and recovery | `POST /api/v1/auth/change-password`, reset request/confirm endpoints |
| Alert resolution and ownership | `PATCH /api/v1/alerts/{id}/resolve`, `PATCH /api/v1/alerts/{id}/assign` |
| Link an alert to a service ticket | `POST /api/v1/alerts/{id}/ticket` or a `ticket_id` field |
| Reports and downloadable exports | Inventory, uptime, ticket and audit export endpoints (CSV/PDF) |
| Per-device monitoring history | `GET /api/v1/devices/{id}/scans` with pagination/date filters |
| Discovery import | An endpoint that converts approved range-scan results into device inventory records |
| Pagination/server-side filtering | Query parameters and paginated response metadata for devices, tickets, alerts, users and audit logs |
| Monitoring policy enforcement | Persisted scheduler jobs that apply `ping`, `scan`, and `threshold` settings without a process restart |
| First-admin bootstrap | A one-time, deployment-only command or endpoint; public registration is intentionally disabled |

`GET/PUT /api/v1/settings` now persists configuration. The current scheduler still uses its startup interval, so changes to scan cadence are stored but need scheduler rescheduling support before they alter the running job.
