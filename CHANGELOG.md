# Changelog

## 2.0.0-dev — Epic 4D

- Added the responsive, theme-aware SNMP Monitoring workspace and role-aware navigation.
- Added secure credential/secret flows, target setup/testing/collection, profile/OID views, candidate review plans, target/interface detail, metrics, state changes, retention, and reports.
- Added a typed SNMP frontend client, aligned TypeScript models, WebSocket-controlled refetch, polling fallback, accessible charts, and zero-dependency frontend contract tests.
- Added no scheduled polling, automatic alerts, topology, traps, arbitrary OID execution, or automatic onboarding.

## 2.0.0-dev — Epic 4C

- Added administrator-reviewed SNMP candidate matching, complete Device onboarding, authoritative linking, and explicit safe enrichment.
- Added interface inventory synchronization with grace-based missing/restored handling, interface/state history, and identity-conflict evidence.
- Added approved system/profile/interface metric collection foundations, counter wrap/reset/reboot-aware rates, utilization quality, bounded query summaries, and manual retention cleanup.
- Added no scheduler, alerts, dashboards/frontend, topology, traps, arbitrary OID execution, or unreviewed inventory creation.

## 2.0.0-dev — Epic 3E

- Added the Active Directory frontend administration interface with deep linking, live WebSocket updates, and detailed object browsing with change history.
- Hardened the APScheduler background worker with startup stale-run recovery, orphan job cleanup, and concurrent execution locks for connections.
- Integrated Active Directory module into Settings.
- Added comprehensive offline test coverage for the scheduler lifecycle.
- Real domain modification, automatic object creation without reconciliation, and password sync remain explicitly excluded.

## 2.0.0-dev — Epic 3D

- Added explainable AD user/device/Discovery/department/role matching with conservative fuzzy evidence and conflict penalties.
- Added reviewed links, fill-missing enrichment, complete Device onboarding, manual-setup User onboarding, mapping rules, stale checks, bulk safeguards, events, audit, and reports.
- Added migration `b8d4f6a10235`, reconciliation APIs, and offline tests.
- No password sync, silent Admin grant, automatic disable/retirement, scheduling, SSO, frontend AD module, or real-domain mutation was added.

## 2.0.0-dev — Epic 3C

- Added manual full, incremental, and dry-run AD staging synchronization.
- Added checkpoints, batch progress, field-level history, missing/restored state, safe errors, cancellation, events, and notifications.
- Added sync-run, staging-object, summary, dry-run, and history APIs with mocked tests.
- No reconciliation, scheduling, AD frontend, HIOP record mutation, or real-domain testing was added.

## 2.0.0-dev — Epic 3B

- Added pinned `ldap3` connectivity supporting verified LDAPS, StartTLS, and explicit development-only LDAP.
- Added RootDSE discovery, DN existence/containment validation, fixed escaped filters, bounded AD paging, and user/computer/group converters.
- Added structured rate-limited connection testing, connection health metadata, safe error classification, and administrator-only non-persistent preview APIs.
- Added migration `f4b8c2d9a731`, mock-only LDAP tests, operational/security guidance, and no synchronization or inventory mutation.

## 2.0.0-dev — Epic 3A

- Added `ActiveDirectoryConnection`, `ActiveDirectorySyncConfiguration`, `ActiveDirectoryObject`, `ActiveDirectorySyncRun`, and `ActiveDirectoryMatchCandidate` models and Alembic migration `e8a9b0c1d2e3`.
- Added authenticated Fernet bind-secret encryption (`ActiveDirectorySecretService`) with a dedicated environment key, safe fallback, write-only responses, and failure-safe errors.
- Hardened the Epic 3A foundation with configuration limits, database checks, strict DN/host/transport validation, explicit Epic 3B service boundaries, and role-policy tests.
- Added `LdapClientInterface` abstract client and `MockLdapClient` stub for offline architecture validation.
- Added Pydantic schemas, repositories, service skeletons, and admin-only REST APIs under `/api/v1/active-directory/`.
- Added audit logging for AD connection lifecycle and documentation in `docs/ACTIVE_DIRECTORY.md`.

## 2.0.0-dev — Epic 2E

- Added server readiness checks and immutable, versioned execution plans.
- Added batched finalization with per-row savepoints, persistent results, idempotency, safe retry, audit, and WebSocket progress.
- Added reviewed create, link, enrichment, merge, and Discovery-link execution without silent overwrites.
- Added later-change-aware rollback preview and compensating rollback.
- Completed final wizard confirmation, progress, results, retry, device links, and rollback UI.
- Added final-import settings, grouped notifications, Imports reporting, migration `d4f2a7c8e901`, and tests.

## 2.0.0-dev — Epic 2D

- Added the authenticated Inventory Import landing page with real session KPIs, search, status filtering, pagination, progress, resume, cancellation, and validation-error export.
- Added a backend-persisted nine-step CSV/XLSX wizard for worksheet selection, column mapping, validation, matching, location review, conflicts, summary, and final-readiness preparation.
- Added explainable candidate comparison, conflict confirmation, read-only merge plans, safe bulk-action eligibility checks, hierarchy-backed location overrides, responsive layouts, and dark/light theme support.
- Added typed import API contracts plus supporting read/list/skip/location endpoints. No final inventory mutation endpoint was added.
- Kept final create/merge execution, rollback, scheduling, Active Directory, and SNMP out of scope for Epic 2E.

All notable HIOP changes are recorded here. The project follows semantic versioning from Version 1.0.0 onward.

## 1.0.0 — 2026-07-20

### Major features

- Authenticated operational dashboard with live device-status updates via WebSocket.
- Real PostgreSQL device inventory with full CRUD lifecycle, hierarchy assignment, search, filtering, and pagination.
- Network Operations Center with approved-scope ICMP scanning, persisted status history, live events, alerts, and automated offline tickets.
- Enterprise ticket workflows with creation, priority levels, assignment, close, controlled deletion, filtering, and device relationships.
- Alert management with automatic creation on status transitions, acknowledgement workflow, severity classification, and detail panel with device context and timeline.
- Administrator user/role/status/password-reset management with last-admin and self-deactivation safeguards.
- Read-only Audit Center with server pagination, combined filters (actor, action, entity type, date range), detail views, cross-module navigation, and CSV export.
- Real-data Reports Center with seven report types (Devices, Network, Alerts, Tickets, Users, Audit, Discovery), charts (donut, bar, trend), date picker, pagination, print layout, and CSV export.
- Database-backed settings management (General, Organization, Network, Notification, Discovery) with production configuration validation and public branding endpoint.
- Organization hierarchy management (Properties, Buildings, Floors, Rooms, Departments, Network Zones) with CRUD and parent-child relationships.
- System health endpoint with API, database, scheduler, WebSocket, and email status.
- Discovery persistence, CIDR-authorized discovery API, review workflow (approve/ignore/reject), bulk operations, dashboard, detail views, and scheduled runs.
- Secure CSV and XLSX inventory import with column alias mapping, row validation, within-file duplicate detection, staged progress, and audited import APIs.
- Explainable cross-system import matching with configurable scoring, conflict penalties, ranked candidate review, non-destructive merge plans, reviewed staging links, and auditable hierarchy/network/hostname location suggestions.
- Production Docker Compose with Nginx reverse proxy, health checks, structured logs, Alembic migrations, backup/restore scripts, and operations guidance.

### Bug fixes and quality

- Fixed stale route-dependent requests that retained data from previously visited routes.
- Fixed duplicate WebSocket lifecycles caused by callback identity changes on each render.
- Fixed duplicate router ownership from legacy compatibility endpoints overlapping dedicated feature routers.
- Removed obsolete registration endpoint that bypassed admin-controlled user creation.
- Replaced temporary `print` statements in scheduler and scan code with structured logging.
- Removed unused registration endpoint from the frontend API catalog.
- Restricted single-device scans to the configured approved private CIDR range.
- Replaced the sidebar's fabricated health claim with real authenticated live-channel state.
- Aligned frontend, backend, deployment, and documentation versions on 1.0.0.
- Removed unused starter SVGs, standalone WebSocket debug page, and stale missing-API documentation.
- Fixed development configuration to consistently use port 8001.
- Standardized test discovery command.
- Fixed missing import wizard page reference causing Vite build failure.
- Added missing import wizard CSS stylesheet.

### Security

- Expiring issuer-bound JWTs with configurable token lifetime.
- Session-scoped token storage in sessionStorage (cleared on tab close).
- Active-user checks on all authenticated endpoints.
- Authenticated WebSocket connections with token subprotocol verification.
- Role-based access control enforced at the API layer.
- bcrypt password hashing (hashes never returned in responses).
- Login throttling and validation.
- Schema-level request validation via Pydantic.
- Approved network CIDR enforcement on all scanning operations.
- Export CSV formula-injection protection.
- Secret-safe settings and health endpoints.
- Production configuration validation (secret key strength, CORS origins, debug mode).
- Safe structured logging (no credentials, secrets, or sensitive data in logs).
- File upload validation (type, size, content, workbook safety).
- Disabled macro execution and formula evaluation in uploaded spreadsheets.

### Performance

- Route-level code splitting with React lazy loading.
- In-flight GET request coalescing to prevent duplicate API calls.
- Stale-request protection with version tracking.
- Deferred search inputs for responsive filtering.
- Consolidated dashboard and audit queries.
- Operational database indexes on frequently queried columns.
- Bounded database connection pooling (configurable pool size).
- Server-side pagination on all list endpoints.

### Known limitations

- Alert resolution and direct alert-ticket relationships are not persisted.
- The embedded APScheduler limits production to one backend worker.
- No ticket comments, attachments, SLA engine, or ticket-specific live events.
- No refresh tokens, MFA, session revocation, email password recovery, or custom permissions.
- No built-in automated backup service, external metrics/SIEM integration, or tamper-evident audit hashing.
- Container image build still requires a running Docker engine in the release environment.
- CSS transform is the slowest Vite build phase (open technical debt).

### Future roadmap (Version 2.0 candidates)

- Dedicated scheduler/worker model for horizontal scaling.
- Alert resolution lifecycle with direct alert-ticket relationships.
- Ticket collaboration features (comments, attachments, SLA engine).
- Stronger session controls (refresh tokens, MFA, session revocation).
- External observability and SIEM integration.
- Automated backup service.
- Multi-property authorization support.
- Inventory merge and creation from import workflow.
## 2.0.0-dev — Epic 4A

- Added the secure, backend-only SNMP integration foundation.
- Added encrypted credential profiles for v1, v2c, and validated SNMPv3 security combinations.
- Added targets, profiles, OIDs, inactive polling configuration, poll runs, metrics, interfaces, and review candidates.
- Added role-protected configuration APIs and authorized-network safeguards.
- Added no live SNMP polling, walks, schedules, dashboards, alerts, topology, frontend, or onboarding.

## 2.0.0-dev — Epic 4B

- Added pinned PySNMP transport with exact v1, v2c, and v3 security mappings.
- Added authorized, rate-limited target testing and approved manual polling APIs.
- Added bounded GET, multi-GET, WALK, BULK-WALK, parsing, lifecycle, cancellation, and locking.
- Added safe metric/interface/candidate persistence, target health, audit, WebSocket, and grouped failure notifications.
- Did not add scheduling, dashboards, alert rules, traffic analytics, topology, frontend, or onboarding.
