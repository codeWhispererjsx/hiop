# HIOP roadmap

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
