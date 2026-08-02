# Changelog

## 3.0.0-dev — Epic 9 Multi-Property Operations & Corporate Management

- Added corporate hierarchy, scoped and delegated administration, inherited permissions with explicit denial, global/regional/property configuration, policies, compliance, exceptions, and tenant-isolated queries.
- Added the Executive Operations Center, cross-property analytics, global search, notifications, corporate reports and PDF/XLSX/CSV exports, plus six governed background jobs.

## 3.0.0-dev — Epic 8 Enterprise Reporting & Business Intelligence

- Added governed KPI definitions, values, targets, thresholds, snapshots, executive audiences, dashboards, widgets, and cache.
- Added deterministic analytics, hospitality/SLA/capacity views, configurable reports, schedules, recipients, email distribution, and Blue & Gold PDF/XLSX/CSV/print exports.

## 3.0.0-dev — Epic 7 Enterprise Asset, Vendor & Procurement Lifecycle

- Added the enterprise registry, audited lifecycle, location, assignment, transfer, disposal, CMDB linkage, and financial history.
- Added vendor scorecards, procurement approvals and receiving, contracts, warranties, licensing, inventory, reports, exports, and scheduled reviews.

## 3.0.0-dev — Epic 6 Enterprise Problem Management

- Added auditable Problem records and guarded ITIL lifecycle transitions.
- Added structured RCA, 5 Whys, Fishbone, validated causes, and findings.
- Added versioned KEDB records, approval/publishing/retirement, and workarounds.
- Added CAPA plans, assigned tasks, verification, and post-resolution review sign-off.
- Added explicit relationships, deterministic incident-correlation suggestions, dashboards, search, reports, and CSV/XLSX/PDF exports.
- Added scheduled review, due-date, aging, correlation, and statistics jobs.

## 3.0.0-dev — Enterprise + Hospitality design system

- Centralized color, typography, spacing, radius, elevation, focus, and z-index tokens across the React application.
- Adopted Royal Blue/Navy enterprise structure, Emerald health semantics, and restrained Premium Gold hospitality accents.
- Refreshed login, authenticated shell, navigation, cards, controls, tables, dialogs, notifications, charts, and responsive states without changing routes, APIs, permissions, or business behavior.
- Added full light/dark/system theme behavior, reduced-motion support, sticky table headers, consistent focus treatment, semantic chart palettes, and design-system regression checks.

## 3.0.0-dev — Enterprise CMDB (Epic 5)

- Added 16 property-aware CMDB tables, 40 hospitality CI types, 14 directional relationship types, identifiers, aliases, typed attributes, immutable attribute/relationship/lifecycle history, and source-system links.
- Added reviewed discovery reconciliation, duplicate/orphan analysis, cycle-safe dependency graphs, deterministic impact summaries, health snapshots, bounded bulk operations, audit, summarized WebSocket events, grouped warranty notifications, and seven scheduler jobs.
- Added 28 protected REST paths, bounded formula-safe reports, the responsive `/cmdb` workspace, focused backend/frontend coverage, and migration `c0d1e2f3a4b5`.
- No AI relationships, automatic assumptions, unreviewed CI creation, or autonomous production actions were introduced.

## 3.0.0-dev — Enterprise change and release management (Epic 4)

- Added property-aware RFC lifecycle, required planning, revisions, tasks, comments, attachments, relationships, and human approval controls.
- Added deterministic ten-factor risk scoring, technical/CAB review with quorum and voting, maintenance calendars, blackout/overlap conflict detection, reviewed execution/evidence/verification, and separately approved rollback.
- Added releases, packages, versions, deployment waves, artifacts, communications, dashboards, bounded formula-safe exports, audit, summarized WebSocket events, grouped notifications, and eight stable scheduler jobs.
- Added the responsive `/changes` workspace, migration `b9c0d1e2f3a4`, backend/frontend tests, and operational documentation. No AI approval, arbitrary execution, autonomous deployment, or production mutation was introduced.

## 3.0.0-dev — Knowledge operations (Epic 3D)

- Added centralized knowledge articles, taxonomy, ratings, favorites, comments, attachments, revisions, approvals, controlled publishing, and audit history.
- Added immutable operational runbooks with parameterized manual execution, SOP review/acknowledgement, service catalogs, document versions, troubleshooting guides, and operational checklists.
- Added property-aware deterministic search, cross-module relationships, knowledge reports/CSV-XLSX-PDF exports, and stable scheduled content-maintenance jobs.
- Added the responsive Knowledge & Runbooks frontend workspace and focused backend/frontend regression coverage.

## 3.0.0-dev — Physical infrastructure hierarchy

- Added property-aware buildings, floors, zones, hierarchy APIs, and management pages.

## 3.0.0-dev — Property context
- Added authorized property context resolution and user-property access assignments.

## 3.0.0-dev — Hospitality operations
- Added hospitality asset categories/types, technology services, operations summaries, and property operations navigation.

## 3.0.0-dev — Configuration management foundation
- Added encrypted manual configuration version storage, profiles, policies, runs, and metadata APIs.

## 3.0.0-dev — Collector foundation
- Added safe mock collector workflow, known-host trust records, and connectivity-test run metadata.

## 3.0.0-dev — Configuration comparison foundation
- Added checksum-first comparison records, drift records, and explicit baseline promotion.

## 3.0.0-dev — Compliance foundation
- Added structured compliance standards, policies, rules, result, violation, and exception records.

## 3.0.0-dev — Restore workflow foundation
- Added approval-gated change requests, change windows, restore plans, and safe blocked dry-run records.

## 3.0.0-dev — Automation foundation
- Completed approval-safe automation definitions, immutable versions, structured conditions, step dependencies, deterministic plans, safe fixed handlers, dry runs, manual execution, approval checkpoints, retry/cancellation, compensation foundations, audit/live events, grouped notifications, typed frontend APIs, and the Automation workspace.
- Added additive execution migration `f2a3b4c5d6e7` and fixed safe-action seed migration `f3a4b5c6d7e9`; arbitrary code, shell commands, external webhooks, autonomous remediation, and unreviewed destructive actions remain unavailable.

## 3.0.0-dev — Scheduled and event-triggered automation
- Added fixed-catalogue internal events, structured trigger filters/conditions/input mappings, replay protection, correlation-window deduplication, cooldown, storm limits, delayed execution, approval gates, and maintenance/blackout suppression.
- Added recurring and one-time APScheduler jobs with stable IDs, overlap prevention, startup reconciliation, stale-run recovery, scheduler health, property-scoped APIs, audit/live updates, and Automation workspace controls.
- Added additive orchestration migration `f4b5c6d7e8f9`; public webhooks, arbitrary event ingestion, arbitrary code, and unreviewed destructive actions remain unavailable.
- Completed transactional outbox/dead-letter processing, bounded multi-event correlation, recovery cancellation, checksum-backed trigger revisions, validated daily/weekly/monthly recurrence, retention cleanup, reporting summaries, and migration `f5c6d7e8f9a0`.

## 3.0.0-dev — Operational playbooks and incident orchestration
- Completed property-scoped incident command, reviewed duplicate/merge handling, participants, tasks, checklists, decisions, evidence, approved-template communications, impact assessment, response targets, bounded escalation, deterministic remediation recommendations, verified recovery, closure safeguards, cause assessment, post-incident reviews, and follow-ups.
- Added immutable checksum-backed playbook versions, structured steps and run state, stable `incident_*` jobs, redacted evidence bundles, reports, typed frontend APIs, the incident command workspace, and migration `f6d7e8f9a0b1`.
- Preserved human authority: no generative AI, autonomous remediation, arbitrary code, public webhooks, external incident integrations, or automatic configuration restore.

## 3.0.0-dev — Hospitality foundation

- Rebranded HIOP as Hospitality IT Operations Platform while preserving the acronym, repository, database, environment prefixes, and existing API routes.
- Added additive Organization and Property domain models with hospitality types/statuses and nullable device property context.
- Added RBAC-protected organization/property APIs and responsive frontend directories.
- Added migration `f3a4b5c6d7e8`, compatibility tests, and `docs/HOSPITALITY_FOUNDATION.md`.
- Excluded SaaS tenancy, billing, licensing, automation, AI, mobile, integrations, and configuration backups.

## 2.0.0-rc1 — Epic 6E

- Added deterministic aggregate-only baselines using rolling mean/median, MAD, IQR, and percentile bounds.
- Added controlled anomaly rules, explainable anomaly evidence/lifecycle/recovery, bounded correlation groups, deterministic insights, review APIs, summaries, and scheduler job registration.
- Added migration `e7f8a9b0c1d2`, release-candidate documentation, production checklist, and pilot plan.
- Hardened analytics scheduling with baseline, anomaly, correlation, insight, and recovery jobs, all disabled by default and protected by stable IDs and overlap limits.
- Excluded AI, black-box machine learning, autonomous remediation, guaranteed root-cause claims, and final v2 release tagging.

## 2.0.0-dev — Epic 6D

- Added protected Analytics navigation and the executive KPI workbench.
- Added health, capacity, availability, SLA, reliability, forecast, trend, and report views backed only by existing APIs.
- Added responsive, theme-aware line, area, bar, donut, and heatmap components with confidence bands and accessible tabular summaries.
- Added URL-persisted filters, loading/empty/error states, safe JSON/CSV/print exports, aligned TypeScript contracts, and frontend tests.
- Excluded anomaly detection, AI recommendations, new forecasting logic, and external BI integrations.

## 2.0.0-dev — Epic 6C

- Added deterministic aggregate-only forecasting with linear regression, moving average, weighted moving average, simple exponential smoothing, and growth-percentage projection.
- Added explainable growth rates, descriptive seasonal comparison, confidence, bounds, trend direction, capacity risk, and forecast-versus-actual evaluation.
- Added forecast APIs, summaries, bounded reports, migration `d9f7c5e3b812`, synthetic tests, and operating documentation.
- Excluded AI, machine learning, anomaly detection, forecast alerts, remediation, recommendations, and executive dashboards.

## 2.0.0-dev — Epic 6B

- Added deterministic scheduled analytics jobs, reconciliation, pause/resume, stale-run recovery, and isolated locking.
- Added checkpoints, late-data overlap, weighted rollups, bounded backfill, progress/retry/cancellation, trends, data quality, and retention cleanup.
- Added migration `c8e6b4d2a701`, synthetic tests, and operations documentation.

## 2.0.0-dev — Epic 6A

- Added advanced analytics definitions, idempotent aggregates, availability, explainable health scores/configurations, capacity policies/assessments, SLA definitions/measurements, reliability, data quality, and manual-run models.
- Added controlled source mapping, bounded UTC time-series aggregation, percentiles, unknown/maintenance-aware availability, deterministic health/capacity/SLA/MTTR/MTBF services, and authenticated APIs.
- Added additive migration `b7d9e2f4a601`, audit/WebSocket run integration, safe settings, synthetic tests, and analytics architecture/operations documentation.
- Excluded dashboards, AI, forecasting, anomaly detection, automatic recommendations, scheduled analytics, and real hotel-data benchmarking.

## 2.0.0-dev — Epic 5E

- Added deterministic scheduled topology collection, inference, snapshots, change evaluation, health checks, startup reconciliation, stale-run recovery, jitter, coalescing, and per-topology overlap protection.
- Added protected baselines, deduplicated change findings, maintenance-aware alert rules/events, topology health, structural analytics, bounded operations history, retention preview/cleanup, and formula-safe CSV exports.
- Added the topology operations frontend with schedule controls, run/health monitoring, alert-rule administration, maintenance controls, retention, exports, typed clients, tests, and operating documentation.
- Preserved reviewed topology and inventory authority; excluded traps, device configuration, automatic remediation, and unapproved real-network collection.

## 2.0.0-dev — Epic 5D

- Added the React Flow interactive Network Topology workspace, protected route, and authorized navigation.
- Added real-API topology landing, map, details, filters, layouts, path/impact, review, conflicts, manual links, snapshots/comparison, changes, and settings.
- Added typed topology clients/contracts, authenticated live-event refresh, responsive dark/light styling, accessible table fallbacks, and frontend tests.
- Added `@xyflow/react` as the sole graph visualization dependency.

## 2.0.0-dev — Epic 5C

- Added explainable topology inference runs, confidence history, evidence fusion, conflict records, and administrator review items.
- Added safe provisional-link merging, duplicate-node recommendations, layer/link classification, dependency inference, orphan analysis, multiple path reconstruction, and snapshot comparison APIs.
- Preserved confirmed manual links and official inventory identities; excluded frontend topology maps, scheduling, alerts, bridge/MAC/STP inference, device configuration, and real-network execution.

## 2.0.0-dev — Epic 5B

- Added secure bounded LLDP and Cisco CDP neighbor collection using approved fixed OID roots.
- Added collection runs, observations, candidates, provisional nodes/links, confidence evidence, conflict handling, grace aging, review APIs, tests, and documentation.
- Preserved manual-link precedence and excluded arbitrary walks, inventory mutation, auto-confirmation, scheduling, topology maps, and real hotel-network collection.

## 2.0.0-dev — Epic 5A

- Added relational topology models, repositories, services, APIs, snapshots, bootstrap, migration, tests, and documentation.
- Fixed Settings partial loading, Reports AD reconciliation rendering, Active Directory live-update cleanup, and sidebar scroll persistence.

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
## Unreleased — 2.0.0-dev

- Added deterministic scheduled SNMP polling, reconciliation, jitter, locks, and stale-run recovery.
- Added reviewed rules, deduplicated evidence, multi-sample recovery, maintenance suppression, and frontend views.
- Added protected scheduled retention and aggregate production health data.

## 3.0.0-dev — Epic 9.5 Enterprise Discovery & Configuration Intelligence

- Added bounded policies, twenty-stage jobs, retries, fingerprints, OUI/service identification, snapshots, evidence, and explainable confidence.
- Added review, reviewed topology, deduplicated CMDB sync, encrypted credentials, schedulers, protected APIs, React pages, tests, and documentation.
- Excluded intrusive scanning, exploits, fabricated links, autonomous changes, and secret retrieval.
