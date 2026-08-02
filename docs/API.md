# HIOP 1.0.0 API

## Multi-property API

`/api/v1/enterprise` provides paginated organizations, regions and property groups; hierarchy and membership management; administrative scopes and effective permissions; inherited settings; policy lifecycle, assignments, compliance and approved exceptions; executive dashboards; cross-property analytics/operations; tenant-isolated global search; notifications; corporate reports; and PDF/XLSX/CSV export. Mutations require corporate administration roles and are audited.

## Epic 6 Problem Management

`/api/v1/problems` provides paginated/filterable Problems, detail, patch, and guarded transitions. Subresources cover `/rca`, `/rca/causes`, `/rca/five-whys`, `/rca/fishbone`, `/known-errors`, `/workarounds`, `/capa`, `/reviews`, `/relationships/graph`, `/correlations`, `/reports`, `/search`, and CSV/XLSX/PDF export. Readers can query; technicians contribute; administrators approve, publish, retire, verify, and initiate correlation evaluation.

## Epic 3A automation

`/api/v1/automation` provides role-protected workflow, immutable version, step,
dependency, execution-plan, dry-run, manual-run, run-step, approval, cancellation,
and retry APIs. Workflow mutations require Admin. Read access is filtered to
authorized properties for non-administrators. Definitions accept structured,
bounded JSON only; no endpoint accepts shell commands, executable code, arbitrary
network requests, or dynamic handler references.

## Epic 3B scheduled and event-triggered automation

`/api/v1/automation/events`, `/triggers`, `/trigger-executions`, `/schedules`,
and `/scheduler-status` expose property-scoped orchestration state. Admins may
submit only registered internal event types, manage trigger subscriptions, and
create/update/delete schedules. Readers see only authorized property records.
Schedules pin approved workflow versions and support recurring intervals or
one-time execution. Event payloads are bounded and reject secret-bearing fields;
no public webhook, arbitrary event, executable expression, or arbitrary network
action endpoint exists.

Operational endpoints include `/event-catalogue`, event detail/reprocessing,
trigger validation/testing/history, schedule enable/disable/run-now/history,
`/correlation-groups`, `/dead-letter-events`, `/outbox/process`,
`/retention/preview`, confirmed `/retention/cleanup`, `/reports/summary`, and
`/scheduler-status`. Mutations require Admin; reader results remain
property-scoped. The event POST is an authenticated internal/testing surface,
not an unauthenticated or externally trusted webhook.

## Epic 6B analytics operations

Under `/api/v1/analytics`, Epic 6B adds schedule read/update and pause/resume, scheduler status, backfill preview/start, run progress/errors/retry, bounded trends and comparison, capacity/SLA/reliability summaries, data quality, and retention preview/confirmed cleanup. Mutations require Admin.

## Epic 6C forecast API

Forecast list, latest entity forecast, history, summary, and report endpoints allow authorized analytics readers to inspect deterministic projections. `POST /analytics/forecast/run` and forecast evaluation require Admin. Requests select an enabled metric definition, entity, bounded aggregate period, bucket, approved statistical method, and bounded horizon; arbitrary expressions and raw-source forecasting are not accepted.

## Topology API

`/api/v1/topology` exposes authenticated, bounded topology CRUD and graph analysis. Admins mutate; administrators and authorized technicians read.

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
## SNMP configuration foundation (2.0.0-dev)

`/api/v1/snmp` provides administrator mutation and administrator/technician reads for credentials, targets, device profiles, OID definitions, inactive polling configuration, and paginated observation foundations. Credential responses expose only secret-presence booleans. There are no target-test, GET, WALK, poll, scheduler, alert, onboarding, or arbitrary endpoint-probing APIs in Epic 4A. See `SNMP.md`.

Epic 4B adds admin-only `POST /targets/{id}/test`, `GET /targets/{id}/system-identity`, and `POST /targets/{id}/poll`. Poll types are limited to availability, system, interfaces preview, and custom profile. Run detail, cancellation, and bounded results are under `/poll-runs/{id}`. There remains no public raw GET, OID-array, WALK, or BULK-WALK endpoint.
# SNMP Epic 4C

`/api/v1/snmp` now includes administrator-only candidate matching and reviewed approve/link/enrich/ignore/reject/restore actions; `POST /targets/{id}/collect` accepts only allow-listed collection groups. Read roles can use bounded candidate matches, target interfaces, interface changes/metrics, target metrics, and metric summaries. Retention preview and cleanup are administrator-only. No route accepts a raw OID, community, auth secret, privacy secret, or unbounded time-series request.

Epic 4D adds the paginated `GET /api/v1/snmp/state-changes` integration endpoint with target, interface, type, severity, and date filters. It returns safe evidence only and does not create or mutate Alert records.
## SNMP Epic 4E

Authenticated APIs cover alert-rule CRUD/enable/disable/preview, target evaluation, unresolved events, scheduler
health/reconciliation, target pause/resume, and maintenance. Mutations are admin-only; preview creates no alerts.
## Epic 5B topology neighbor discovery

Admin-only collection and review routes are available under `/api/v1/topology/{topology_id}`: `collect-neighbors`, `targets/{target_id}/collect-neighbors`, `neighbor-runs`, run cancellation/results, `neighbor-observations`, `neighbor-candidates` with match/ignore/restore/confirm-node-match actions, and `candidate-links` with confirm/reject/suppress actions. List/detail routes allow admin and technician roles.

Collection accepts only target IDs, `auto|lldp|cdp|both`, and `dry_run`. It never accepts credentials, endpoints, OIDs, or arbitrary walk roots. All lists are paginated.

## Epic 5C topology inference

Reads require admin or technician access; inference execution and review resolution require admin:

- `GET /api/v1/topology/{id}/inference`
- `POST /api/v1/topology/{id}/run-inference`
- `GET /api/v1/topology/{id}/conflicts`
- `GET /api/v1/topology/{id}/review-items`
- `POST /api/v1/topology/{id}/review-items/{item_id}/approve`
- `POST /api/v1/topology/{id}/review-items/{item_id}/reject`
- `POST /api/v1/topology/{id}/review-items/{item_id}/ignore`
- `GET /api/v1/topology/{id}/path-analysis`
- `GET /api/v1/topology/{id}/impact-analysis`
- `GET /api/v1/topology/{id}/comparison?snapshot_id=...`

Inference requests may select dry-run, dependency inference, and layer suggestions. Path analysis accepts only bounded path type, depth, and result-count parameters.

## Epic 5D interactive topology client

The `/topology` frontend consumes these existing bounded contracts through one typed client. Initial maps use `GET /topology/{id}/graph`; explicit positions use `GET/PUT /topology/{id}/layout`; path and impact modes use `path-analysis` and `impact-analysis`; conflict/review workspaces use their paginated endpoints; and historical views use snapshots, snapshot graphs, comparison, and changes. No public route accepts arbitrary discovery algorithms, device commands, or unbounded graph input.

## Epic 5E topology operations API

- `GET/PUT /topology/{id}/schedule`; `POST .../pause|resume`; `GET /topology/{id}/scheduler-status`
- `POST /topology/{id}/maintenance/start|end`
- `GET /topology/{id}/health`, `/analytics`, `/operational-runs`, and `/reports/summary`
- `GET/POST /topology/alert-rules`; `GET/PATCH /topology/alert-rules/{id}`; enable, disable, and preview actions
- `GET /topology/alerts`
- `GET /topology/retention/preview`; `POST /topology/retention/cleanup`
- `GET /topology/{id}/exports/nodes.csv|links.csv`
- `POST /topology/{id}/snapshots/{snapshot_id}/baseline`

All mutations require Admin. Read endpoints require Admin or Technician. Lists are paginated and exports are bounded/formula-safe.

## Epic 6A analytics API

Authenticated `/analytics` endpoints provide metric-definition CRUD, paginated aggregate queries, bounded UTC time series, availability, current/historical health, health-configuration CRUD, capacity policy/assessment queries, SLA definition/measurement queries, reliability measurements, manual dry/live runs with cancellation, and system/entity summaries. Admin is required for configuration and run mutations; Admin and Technician may read. No route accepts SQL, expressions, source table names, arbitrary transforms, unbounded time ranges, or analytics schedules.
# Hospitality foundation APIs (v3)

- `GET /api/v1/organizations` — authenticated paginated organization directory
- `POST /api/v1/organizations` — administrator organization creation
- `GET /api/v1/properties` — authenticated paginated/filterable property directory
- `POST /api/v1/properties` — administrator property creation
- `GET /api/v1/properties/{id}` — authenticated property detail
- `PATCH /api/v1/properties/{id}` — administrator property update
- `DELETE /api/v1/properties/{id}` — administrator safe archive

These endpoints preserve existing `/api/v1/hierarchy` routes and do not create multi-tenant SaaS boundaries.
## Incident management

The protected `/api/v1/incidents` surface provides declaration and duplicate
review, controlled transitions, sources, participants, tasks, checklists,
timeline, evidence, decisions, communications, impact, deterministic
recommendations, recovery verification, cause assessment, post-incident review,
follow-ups, escalation evaluation, redacted evidence bundles, and reporting.
`/api/v1/incidents/playbooks` and `/playbook-versions` provide admin-only
structured playbook lifecycle management. All reads and mutations enforce
property access; there is no public webhook or arbitrary action endpoint.

Run operations under `/api/v1/incidents/playbook-runs` expose bounded
pause/resume/cancel controls, ordered step status, explicit approval and
verification completion, version-limited retry, and administrator-only safe
compensation. Compensation keys are part of the approved immutable playbook
version and must resolve to the fixed automation handler catalogue.
# Knowledge operations API

Authenticated endpoints under `/api/v1/knowledge` cover dashboard metrics, articles and lifecycle actions, revisions/rollback, comments, ratings, favorites, categories, tags, approval queues, runbook versions/steps/executions, SOP sections/acknowledgements, service catalogs and dependencies, document versions, troubleshooting steps, checklist executions, relationships, deterministic search, reports, and bounded CSV/XLSX/PDF exports. Lists are property scoped; mutations require contributor or publisher roles. OpenAPI groups the surface under **Knowledge Management**.

# Enterprise change management API

Authenticated endpoints under `/api/v1/changes` provide RFC CRUD/lifecycle, approvals, tasks, comments, bounded attachments, revisions, risk, relationships, CAB meetings/membership/attendance/agenda/votes/decisions, maintenance windows/approvals/conflicts, execution checkpoints/evidence/verification/rollback, releases/packages/versions/deployments, communications, dashboards, audit, and bounded CSV/XLSX/PDF reports. Property scope and role authorization are enforced per object. There is no arbitrary command, autonomous deployment, or AI approval endpoint.

# Enterprise CMDB API

The 28 protected `/api/v1/cmdb` paths cover dashboard, classes/types/status/lifecycle, paginated CI CRUD/search, lifecycle, typed attributes/history, identifiers/aliases, relationship types/relationships/history, dependency graph/snapshots, impact, reconciliation runs/decisions, health/history, bounded bulk operations, summaries, and CSV/XLSX/PDF export. Mutations require contributor/admin roles and property access. No endpoint accepts executable relationship rules or creates inferred relationships.

# Epic 7 Asset, Vendor and Procurement API

Protected `/api/v1/asset-management` endpoints provide assets, lifecycle/timeline, depreciation/TCO, vendor approval, procurement decisions/orders/receiving, contracts/renewals, warranties/claims, licenses/compliance, inventory movements, relationships, dashboards, and bounded CSV/XLSX/PDF reports. OpenAPI exposes validation and roles; no endpoint performs autonomous purchasing.

# Epic 8 Enterprise BI API

Protected `/api/v1/business-intelligence` endpoints provide paginated KPIs, definitions, targets, thresholds, recalculation, trends, analytics, audience dashboards, hospitality metrics, SLA, capacity, templates, reports, ordered sections, executions, schedules, operational coverage, and PDF/XLSX/CSV/print exports. Formulas accept only governed source keys and allow-listed operations.

# Epic 9.5 Discovery Intelligence API

Protected `/api/v1/discovery-intelligence` endpoints expose capabilities, dashboard statistics, policies, encrypted credential metadata, jobs/stages/tasks, results/evidence/fingerprints, explainable confidence, review actions, local OUI updates, reviewed topology, history, and deduplicated CMDB synchronization. Mutations require administrators and secrets are write-only.
