# HIOP 1.0.0 software requirements specification

## Epic 6 requirements

The system shall maintain auditable Problem, RCA, KEDB, workaround, CAPA, review, relationship, and correlation-suggestion records. It shall enforce sequential lifecycle gates, role permissions, bounded pagination, validation, exports, scheduled reminders, and human approval. It shall not generate root causes, create Problems autonomously, or execute workarounds.

## Purpose and scope

HIOP is the internal source of truth for hotel IT inventory, availability checks, operational alerts, service tickets, users, audit evidence, reports, hierarchy, and safe runtime configuration. It does not remotely configure, patch, reboot, or shut down managed devices.

## Actors

- Administrator: global configuration, inventory/hierarchy/user administration, reports, audit, ticket deletion, and all supported operations.
- Technician: supported monitoring, alert acknowledgement, ticket assignment/closure, and operational reads.
- Staff: authenticated reads and ticket reporting where permitted by the backend.
- Scheduler: performs configured scans within approved scope and records resulting operational state.

## Functional requirements

1. Authenticate active accounts with expiring JWTs and enforce backend roles.
2. Maintain real device inventory with separate lifecycle and network state.
3. Scan individual inventory devices and configured ranges only inside an approved private CIDR.
4. Persist scan results, status transitions, alerts, and configured automatic offline tickets.
5. Provide ticket create/view/edit/assign/close/reopen-through-update/admin-delete workflows.
6. Preserve device history across soft retirement.
7. Manage users through safe activation, role, and password-reset actions without returning secrets.
8. Provide immutable, paginated, filterable audit records and safe CSV export.
9. Generate real device, network, alert, ticket, user, and audit reports with filter-aware CSV.
10. Persist explicit non-secret settings and expose secret-safe health/branding data.
11. Deliver authenticated live device-status updates without polling.
12. Present loading, empty, error, unauthorized, not-found, and success states without dummy data.

## Non-functional requirements

- Security: bcrypt passwords, validated issuer-bound JWTs, throttled login, least-privilege CORS/RBAC, approved network scope, security headers, no secret logging/export.
- Reliability: transaction rollback, dependency-scoped sessions, health checks, persistent PostgreSQL, migration and backup/restore procedures.
- Performance: route splitting, in-flight GET coalescing, indexed operational queries, bounded database pool, and server pagination for large audit/report data.
- Accessibility: labelled keyboard-operable controls, visible focus, responsive tables/layout, and functional light/dark themes.
- Operability: structured logs, scheduler/WebSocket/database health, documented deployment, monitoring, backup, recovery, and rollback.

## Version 1.0.0 exclusions

Full alert resolution/ownership, comments, attachments, SLA timers, arbitrary network execution, remote device control, refresh tokens, MFA, email recovery, custom roles, automated backup/restore UI, multi-property permissions, and external SIEM/metrics are not implemented.
# Epic 3D requirements trace

The system shall provide property/corporate knowledge visibility, controlled article/SOP lifecycles, immutable revisions and runbook versions, reviewed publication, manual parameterized runbook/checklist execution, deterministic bounded search, cross-module relationships, RBAC, audit history, exports, and stable scheduled maintenance. It shall reject executable Markdown, traversal paths, oversized attachments, arbitrary commands, and AI-derived content.

# Epic 4 requirements trace

HIOP shall provide property-aware RFC planning, technical and CAB approvals, deterministic risk scoring, approved maintenance windows, conflict detection, manual evidence-backed execution, separately authorized rollback, release records, communication history, audit, and bounded reporting. The system shall reject invalid transitions and shall not generate approvals or execute arbitrary production actions.

# Epic 5 requirements trace

HIOP shall maintain property-aware CIs, taxonomy, lifecycle, custom attributes, normalized identifiers, evidence-backed directional relationships, cycle-safe dependency views, deterministic impact, reviewed reconciliation, data health, search, bounded bulk operations, reporting, audit, and scheduled validation. It shall reject self/duplicate links and shall never invent a relationship or auto-create an unreviewed CI.

# Epic 7 requirements

HIOP shall maintain auditable multi-property asset, vendor, procurement, contract, warranty, license, inventory, and financial records. Procurement and renewals require human approval. Depreciation and compliance calculations shall be deterministic, fixed-precision, reproducible, and free of autonomous purchasing recommendations.

# Epic 8 requirements

HIOP shall expose governed property/corporate KPIs, executive audience dashboards, deterministic periods/averages/trends/growth/variance/baselines, historical-only capacity forecasts, configurable scheduled reports, SLA and hospitality metrics, accessible visualizations, and branded exports. Formulas shall not execute arbitrary code or produce autonomous recommendations.
