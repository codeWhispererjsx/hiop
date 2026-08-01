# HIOP 2.0.0-dev architecture

Epic 6B adds an isolated analytics scheduler over controlled operational-source adapters. Deterministic jobs create bounded runs, checkpoints drive incremental aggregation, and retention never deletes operational source or audit data.

Epic 6C adds a deterministic forecast layer above persisted aggregates. Statistical methods are explicit application code, produce auditable assumptions and bounds, and persist results in PostgreSQL without AI, ML libraries, external prediction services, or access to raw monitoring samples.

## Epic 5A network topology

The topology layer is a relational graph over inventory, discovery, and SNMP identities. Nodes, links, evidence, segments, dependencies, layout state, snapshots, and reviewed changes are separate so evidence cannot silently mutate inventory. See `docs/TOPOLOGY.md`.

## Epic 3 Active Directory integration

Epics 3A–3E provide an opt-in Active Directory administration module. `ActiveDirectoryConnection` models connection profiles; `ActiveDirectorySyncConfiguration` manages per-domain synchronization; `ActiveDirectoryObject` stages directory users, computers, and groups; `ActiveDirectorySyncRun` captures execution telemetry; and explainable candidates support reviewed matching and reconciliation with HIOP users and devices. Bind secrets use authenticated Fernet encryption, are write-only, and are excluded from API responses.

The React administration workspace provides connection health, safe secret rotation, RootDSE/search-base assistance, manual and scheduled synchronization, staged object review, mappings, reconciliation, reports, and missing/disabled queues. APScheduler reconciles deterministic per-connection jobs on startup, prevents overlap, and recovers stale runs. LDAP access is read-only: HIOP does not authenticate against AD, synchronize passwords, join domains, manage policy, or mutate AD objects. See `docs/ACTIVE_DIRECTORY.md`.

## Epic 4A SNMP integration foundation

The backend defines encrypted SNMP credential profiles, authorized-network targets, non-executable device profiles and OID definitions, inactive polling configuration, poll-run/metric/interface storage, and review-only discovery candidates. Configuration APIs are role-protected and secret-safe. The client contract fails closed: Epic 4A performs no SNMP network operation, polling, scheduling, alerting, topology, onboarding, or frontend work. See `docs/SNMP.md`.

## Epic 2E final import

Final inventory import is a backend-orchestrated state machine. A versioned plan and unique per-row execution results provide idempotency; session row locks, configurable batches, and row savepoints provide concurrency and failure isolation. Before/after snapshots support later-change-aware compensating rollback without deleting inventory history or audit records. See `docs/IMPORT_ARCHITECTURE.md`.

## Intelligent inventory import foundation

Epic 2A adds a backend-only staging bounded context beside official inventory and Discovery. `ImportSession` owns staged `ImportedDevice` rows; repositories provide persistence only; an unimplemented `ImportService` reserves orchestration; and abstract field validators reserve future normalization contracts. No API, parser, matcher, approval flow, inventory merge, scheduler, or frontend is registered. See `IMPORT_ARCHITECTURE.md`.

## System shape

HIOP is a three-tier internal operations application:

```text
Browser (React + TypeScript)
        | HTTPS REST + authenticated WebSocket
Nginx reverse proxy
        | /api/v1 and /ws/dashboard
FastAPI application
        | SQLAlchemy / Alembic
PostgreSQL
        |
Approved private network targets (ICMP scanner)
```

The frontend is a Vite single-page application. React Router owns navigation and lazy-loads each page. A centralized API client attaches the session-scoped JWT, normalizes errors, coalesces identical in-flight GET requests, and redirects invalid sessions to login. `DashboardLayout` owns one authenticated WebSocket connection and distributes live device-status events to active pages.

FastAPI groups thin route modules around authentication, devices, scanner operations, tickets, users, audit, reports, hierarchy, dashboard, settings, and WebSockets. Services contain mutation/query logic. Pydantic schemas validate transport data. SQLAlchemy sessions are dependency-scoped and mutations roll back on failure.

The Discovery foundation is backend-only. Its SQLAlchemy models and Alembic migration reserve persistence and identity constraints; persistence-only repositories isolate database access; and an unimplemented service contract reserves later orchestration boundaries. Epic 1A registers no route, scheduler job, scanner, approval flow, inventory mutation, or frontend page. See `DISCOVERY.md`.

## Security boundaries

- Login issues an expiring JWT with issuer, issued-at, and unique-token claims.
- Bearer tokens are stored in `sessionStorage`, removed on logout/401, and never placed in URLs or logs.
- The WebSocket requires the token as a subprotocol and verifies an active user.
- Backend role checks are authoritative. Administrators manage users, hierarchy, reports, audit, and settings; technicians receive only supported operational access.
- Passwords are bcrypt-hashed. Responses never contain hashes.
- Range and single-device scans are restricted to the persisted approved private CIDR.
- Deployment secrets remain environment-only and are excluded from settings responses and audit descriptions.

Because bearer authentication uses an explicit `Authorization` header rather than ambient cookies, browser CSRF is not the primary threat. CORS remains allow-listed, while XSS prevention and token lifetime limit token theft risk.

## Operational flows

### Device monitoring

An administrator or technician scans an inventory device, or the embedded scheduler scans active inventory. Each attempt creates a `network_scans` row and updates `Device.network_status`. A real status transition may persist an alert, create an offline ticket according to settings, and emit `device_status_changed` over the authenticated socket.

Inventory lifecycle (`Active`, `Inactive`, `Retired`) is deliberately separate from network state (`Online`, `Offline`, `Unknown`). Retirement is a soft operation and preserves scans, alerts, tickets, and audit history.

### Ticket lifecycle

Authenticated users may report tickets. Supported staff assign and close them; admins may delete. Device relationships are real foreign keys. Administrative mutations create audit entries. Ticket-specific WebSocket events, comments, attachments, and SLA timers are not part of 1.0.0.

### Configuration

Validated non-secret runtime settings are stored in `system_settings`. Secrets and infrastructure configuration remain environment variables. Scheduler changes are applied through one controlled scheduler job. The public settings endpoint returns only safe branding values.

## Deployment

Docker Compose defines PostgreSQL, one-shot migrations, one backend worker, and the Nginx-served frontend. One worker is intentional because APScheduler is embedded in the API process; horizontal API scaling requires moving scheduling behind a distributed lock or dedicated worker. See `DEPLOYMENT.md` and `OPERATIONS.md`.

## Version 1.0.0 limitations

- Alerts support acknowledgement but not a persisted resolved lifecycle or direct ticket ID.
- The scheduler is process-local.
- No refresh tokens, MFA, session revocation, email reset flow, or custom permission model.
- No ticket comments, attachments, SLA engine, or ticket-specific live events.
- No automated backup service, external metrics platform, SIEM integration, or tamper-evident audit chain.
- Discovery currently provides architectural persistence only; it performs no network discovery or workflow actions.
## SNMP scheduled operations (Epic 4E)

SNMP uses the shared scheduler, deterministic target/group jobs, startup reconciliation, stale-run recovery, jitter,
and existing locks. Alert evaluation is a separate post-persistence service; one cleanup job protects alert evidence.

Topology now follows the same single-scheduler architecture. Persisted per-topology configuration reconciles deterministic collection, inference, snapshot, change, and health jobs at startup. A topology-wide operational lock prevents overlap; existing SNMP target locks remain authoritative. Change, alert, analytics, retention, reporting, and export logic live in `TopologyOperationalService`, separate from route handlers and graph inference.

Advanced analytics remains in the primary PostgreSQL domain. Fixed source adapters normalize existing scans/SNMP/history, repositories upsert canonical buckets, and separate availability/health/capacity/SLA/reliability services produce explainable derived records. Manual execution uses bounded background tasks only; no analytics scheduler is registered. The source-adapter boundary permits a future time-series store without changing domain/API contracts.
## Automation orchestration

Domain services write validated internal-event envelopes to the PostgreSQL
outbox in the same transaction as operational changes. A bounded shared-scheduler
job processes events into property-compatible subscriptions, structured filters,
correlation groups, approvals, and version-pinned workflow runs. Calendar and
interval jobs use stable IDs and startup reconciliation. Dead letters,
trigger revisions, execution history, and audit records preserve explainability.

# Hospitality domain foundation (v3)

Version `3.0.0-dev` introduces an additive organization/property context: Organization → Property → existing Department/Room → Device. Existing route and database names remain stable, organization assignment is nullable for legacy data, and no tenant isolation is implied.
## Incident orchestration

The incident domain is property-scoped and authoritative. Immutable operational
playbook versions can reference only allowlisted automation actions; playbook
runs materialize human tasks, checklists, decisions, evidence, communications,
and verification gates. Deterministic scheduler jobs evaluate response targets
and bounded escalation. Recovery and closure are separate, human-confirmed
states. See `INCIDENT_MANAGEMENT.md`.
# Epic 3D knowledge architecture

The knowledge bounded context is implemented by `app.models.knowledge`, a service layer for lifecycle/search/execution rules, a fixed `/api/v1/knowledge` router, and the existing shared APScheduler instance. Property scope is enforced before record access. Immutable revision/version records preserve reviewed content; polymorphic relationships preserve cross-module evidence without introducing foreign-key coupling to every operational domain. PostgreSQL GIN indexes accelerate approved text fields while deterministic fallback matching supports test databases.

# Epic 4 change architecture

The `change_management` bounded context separates RFC planning, CAB decisions, deterministic risk, maintenance scheduling, execution/rollback, release records, and communication. Route handlers delegate state rules to `change_management_service`; the shared scheduler owns stable reminder and reconciliation jobs. Immutable revisions and append-only operational records retain evidence while polymorphic relationships avoid unsafe cross-domain cascades. The older configuration-restore request remains a separate compatibility context.

# Epic 5 CMDB architecture

`app.models.cmdb` is an additive authoritative CI context linked to, but separate from, Device Inventory and discovery sources. `cmdb_service` owns deterministic lifecycle, validation, relationship traversal, impact, reconciliation, graph snapshots, and health. `/api/v1/cmdb` enforces property scope and RBAC. The shared scheduler registers seven stable `cmdb_*` jobs; none creates CIs or relationships.
