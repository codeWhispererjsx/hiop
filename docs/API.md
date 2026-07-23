# HIOP 1.0.0 API

## Active Directory synchronization (2.0.0-dev)

Administrators start staging-only full, incremental, or dry-run synchronization with `POST /api/v1/active-directory/connections/{id}/sync`. Run detail, cancellation, safe errors, summary, and projections are under `/sync-runs/{id}`. Staged detail/history are under `/objects/{id}`. Technician reads redact email/raw attributes; raw LDAP filters are never accepted.

## Active Directory matching and reconciliation

- `POST /active-directory/connections/{id}/match`
- `GET /active-directory/objects/{id}/matches`
- `GET /active-directory/objects/{id}/reconciliation-plan`
- `POST /active-directory/objects/{id}/accept-match`
- `POST /active-directory/objects/{id}/reject-match`
- `POST /active-directory/objects/{id}/mark-create`
- `POST /active-directory/objects/{id}/ignore`
- `POST /active-directory/objects/{id}/resolve`
- `POST /active-directory/bulk-review`
- `GET|POST /active-directory/connections/{id}/mappings/{kind}`

Mutations require Admin. Resolution requires explicit confirmation and performs source/target freshness and link-consistency checks.

## Final import endpoints

- `POST /imports/{session_id}/rows/{row_id}/disposition`
- `GET /imports/{session_id}/readiness`
- `GET /imports/{session_id}/execution-plan?persist=true`
- `POST /imports/{session_id}/finalize`
- `GET /imports/{session_id}/results`
- `GET /imports/{session_id}/rollback-preview`
- `POST /imports/{session_id}/rollback`
- `POST /imports/{session_id}/retry-failed`

Finalize, disposition mutation, rollback, and retry are administrator-only. Read endpoints use the existing import reader policy.

Development base URL: `http://127.0.0.1:8001/api/v1`. Production clients use same-origin `/api/v1`. FastAPI exposes the authoritative OpenAPI document at `/openapi.json` and interactive documentation at `/docs` when enabled.

Except for `POST /auth/login`, all application routes require `Authorization: Bearer <JWT>`. `/health` is intentionally public and secret-safe. The dashboard WebSocket is `/ws/dashboard` and requires the JWT as the second WebSocket subprotocol after `hiop`.

## Endpoint catalog

| Area | Endpoints |
| --- | --- |
| Authentication | `POST /auth/login`, `GET /auth/me` |
| Dashboard | `GET /dashboard/` |
| Devices | `GET/POST /devices/`, `GET/PUT/DELETE /devices/{id}` |
| Device history | `GET /devices/{id}/scans`, `/alerts`, `/tickets`, `/audit-logs` |
| Network | `POST /network/scan`, `POST /network/scan-all`, `POST /network/scan-range`, `GET /network/history` |
| Alerts | `GET /alerts`, `PATCH /alerts/{id}/acknowledge` |
| Tickets | `GET/POST /tickets/`, `GET/PUT/DELETE /tickets/{id}`, `PATCH /tickets/{id}/assign`, `PATCH /tickets/{id}/close` |
| Users | `GET /users/roles`, `GET /users/eligible-assignees`, admin CRUD/status/role/reset-password routes under `/users` |
| User audit | `GET /users/{id}/audit` |
| Audit | `GET /audit-logs`, `GET /audit-logs/{id}`, `GET /audit-logs/export` |
| Reports | `GET /reports/summary`, `GET /reports/{name}`, `GET /reports/{name}/export` |
| Hierarchy | `GET /hierarchy`, admin create/update/deactivate under `/hierarchy/{kind}` |
| Settings | `GET /settings/public`; admin `GET /settings`, grouped `PUT` routes, and `GET /settings/system-health` |
| Live updates | `WS /ws/dashboard` |
| Discovery | `GET /discovery`, `/discovery/{id}`, `/discovery/stats`, `/discovery/export`; admin run, approve, ignore, reject, and bulk routes |
| Inventory imports | Admin upload/mapping/validate/cancel under `/imports`; admin/technician session, columns, staged rows, errors, and safe error export |
| Active Directory | Admin CRUD, secret rotation, real bounded connection test, safe RootDSE, and non-persistent user/computer/group previews under `/active-directory/connections`; admin/technician read-only staged history remains under `/sync-runs`, `/objects`, `/matches` |


Inventory import endpoints stage validated device candidates only. They never create or update official inventory. Upload accepts multipart `.csv` and `.xlsx`, returns a bounded mapping preview, and never exposes the temporary server filename or path. Mutation routes are administrator-only.

Epic 2C adds administrator matching/recompute, candidate accept/reject, create-new recommendation, and location-review routes under `/imports/{session_id}`. Admins and technicians can list ranked candidates and inspect evidence or a non-destructive merge plan. These routes retain staging history and never create, overwrite, merge, or delete an official inventory device.

Supported report names are `devices`, `network`, `alerts`, `tickets`, `users`, `audit`, and `discovery`. CSV export honors filters and neutralizes spreadsheet-formula prefixes.

Discovery settings are returned in the administrator settings bundle and updated with `PUT /settings/discovery`. The API accepts only validated private IPv4 CIDRs and bounded execution values. Discovery mutation routes are administrator-only; authenticated users may read Discovery data.

## Authorization summary

- Admin: global configuration, reports, full audit, user and hierarchy management, device mutations/retirement, ticket deletion, and all supported operational actions.
- Technician: supported monitoring, alert acknowledgement, ticket assignment/closure, eligible assignees, and authenticated operational reads.
- Staff: authenticated reads and ticket reporting where the backend permits them.

Frontend visibility is convenience only; FastAPI role dependencies are authoritative.

## Response behavior

- `400`: malformed business request.
- `401`: missing, invalid, expired, or inactive-user authentication.
- `403`: authenticated but insufficient role.
- `404`: requested record does not exist.
- `409`: uniqueness or lifecycle conflict where explicitly handled.
- `422`: schema, enum, UUID, query-bound, approved-network, IP, or MAC validation failure.
- `429`: login throttle exceeded, including `Retry-After`.

Errors use FastAPI's `detail` field. The frontend safely handles string and validation-array details and falls back for non-JSON failures.

## Important semantics

- `DELETE /devices/{id}` soft-retires; it does not erase the device or history.
- `DELETE /users/{id}` is a compatibility alias for account deactivation.
- `DELETE /tickets/{id}` physically deletes and is administrator-only.
- `Device.inventory_status` and `Device.network_status` are independent.
- Scanner targets must fall inside the configured approved private CIDR.
- Alert resolution, direct alert-ticket linking, ticket comments/attachments, and ticket-specific WebSocket events are not 1.0.0 API capabilities.

## Secret handling

Settings responses never return the JWT secret, database credentials, SMTP password, password hashes, tokens, private keys, or raw connection strings. Tokens belong only in the authorization header or authenticated WebSocket subprotocol and must not be logged.
