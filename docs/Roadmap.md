# HIOP roadmap

## Version 3 — Epic 6 complete

Enterprise Problem Management and KEDB now connect the operational lifecycle: Incident → Problem → Change → Knowledge → CMDB. Future work may add external vendor/contract adapters without changing the human-approval boundary.

## Version 1.0.0 — release candidate

Completed: authentication/RBAC, dashboard, device inventory and hierarchy, scanner/scheduler, network operations, alerts, tickets, users, audit, reports/CSV, settings, authenticated live updates, security/performance stabilization, Docker/Nginx deployment baseline, health/logging/backups documentation, and release guidance.

## Stabilization after go-live

- Run target-environment image build/advisory scanning and load/failover tests.
- Complete production restore drills and centralized monitoring/log retention.
- Add isolated automated browser regression testing to CI.
- Externalize the scheduler before horizontal backend scaling.

## Version 2.0 candidates

- Full alert lifecycle, direct alert-ticket relation, structured activity events.
- Ticket comments, attachments, SLA policies, and ticket-specific WebSocket events.
- Refresh tokens, MFA, session revocation, email verification/recovery, and custom permissions.
- SNMP/telemetry, controlled discovery import, topology, multi-property authorization, and richer historical analytics.
- Automated encrypted backups, external metrics/tracing/SIEM, correlation IDs, and tamper-evident audit retention.

Roadmap items are not implemented controls and must pass design, authorization, migration, security, and acceptance review before development.
# Epic 3D status

Knowledge Base, Runbooks, SOPs, Service Catalog, Documentation Library, Troubleshooting, Checklists, deterministic Search, relationships, publishing workflows, reporting, and scheduled maintenance are delivered as the v3 operational-documentation foundation. Future work may add deployment-specific binary preview/storage adapters; AI search and autonomous execution remain excluded.

# Epic 4 status

Enterprise Change Management is delivered with human-reviewed RFC, CAB, risk, maintenance, execution/rollback, release, reports, and reminder foundations. Future adapters may connect approved external calendars and deployment systems, but autonomous production changes remain excluded.

# Epic 5 status

The Enterprise CMDB foundation is delivered with authoritative CIs, reviewed relationships, lifecycle, deterministic graph/impact/reconciliation/health, reports, jobs, and frontend. Problem and Known Error Management is the recommended next bounded context. Cloud/vendor adapters remain explicit future integrations.

# Version 3 progression

- [x] Epic 7 — Enterprise Asset, Vendor, Procurement & Contract Lifecycle Management
- [ ] Epic 8 — Enterprise Reporting, Executive Dashboards & Business Intelligence
