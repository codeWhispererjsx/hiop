# Changelog

All notable HIOP changes are recorded here. The project follows semantic versioning from Version 1.0.0 onward.

## 2.0.0-dev — Unreleased

- Added conservative private-IPv4 Discovery with CIDR authorization, ignore ranges, bounded ICMP, passive ARP inspection, PTR lookup, vendor hints, fingerprint confidence, duplicate prevention, and retained run history.
- Added secure Discovery APIs, administrator review and bulk workflows, transactional inventory approval, audit entries, email policy integration, authenticated WebSocket events, and CSV-safe export.
- Added the responsive Discovery dashboard, detail and review dialogs, real API data, Discovery settings, scheduled runs, and Discovery reporting.
- Scheduled Discovery uses one replaceable APScheduler job with overlap prevention. Discovery remains disabled by default and performs no port scanning or public-internet scanning.
- Added secure UTF-8 CSV and `.xlsx` inventory parsing, generated temporary storage, column alias detection/manual mapping, normalized row validation, within-file duplicate evidence, staged progress, audited import APIs, and CSV-safe validation-error export. Importing still creates no official inventory.

## 1.0.0 — 2026-07-16

### Major features

- Authenticated operational dashboard with live device-status updates.
- Real PostgreSQL device inventory, lifecycle management, hierarchy, scan history, alerts, tickets, and audit history.
- Network Operations Center with approved-scope scans, persisted status history, live events, alerts, and automated offline tickets.
- Enterprise ticket workflows with assignment, close, controlled deletion, filtering, pagination, details, and audit activity.
- Administrator user/role/status/password-reset management with last-admin and self-deactivation safeguards.
- Read-only Audit Center with server pagination, combined filters, details, cross-module navigation, and CSV export.
- Real-data Reports Center with charts, dates, filters, pagination, printing, navigation, and CSV exports.
- Database-backed safe settings, organization branding, normalized hierarchy administration, and system health.
- Production Docker Compose/Nginx baseline, health checks, structured logs, migrations, backup/restore scripts, and operations guidance.

### Bug fixes and quality

- Fixed stale route-dependent requests, duplicate WebSocket lifecycles, duplicate router ownership, obsolete registration paths, unsafe debugging output, inconsistent navigation/status handling, and user/audit interface defects.
- Removed unused starter assets, obsolete WebSocket test page, and stale missing-API documentation.
- Replaced the sidebar's fabricated health claim with real authenticated live-channel state.
- Restricted single-device scans to the configured approved private CIDR.
- Aligned frontend, backend, deployment, and documentation versions on 1.0.0.

### Security

- Expiring issuer-bound JWTs, session-scoped token storage, active-user checks, authenticated WebSockets, role enforcement, login throttling, schema validation, approved network scope, export neutralization, secret-safe settings/health, security headers, production configuration validation, and safe logging.

### Performance

- Route-level code splitting, in-flight GET coalescing, stale-request protection, deferred table searches, consolidated dashboard/audit queries, operational database indexes, and bounded connection pooling.

### Known limitations

- Alert resolution and direct alert-ticket relationships are not persisted.
- The embedded scheduler limits production to one backend worker.
- No ticket comments, attachments, SLA engine, or ticket-specific live events.
- No refresh tokens, MFA, session revocation, email password recovery, or custom permissions.
- No built-in automated backup service, external metrics/SIEM integration, or tamper-evident audit hashing.
- Container image build still requires a running Docker engine in the release environment.

### Roadmap

Version 2.0 candidates include a dedicated scheduler/worker model, alert lifecycle expansion, collaboration/SLA features, stronger session controls, external observability/SIEM, backup automation, and multi-property authorization.
