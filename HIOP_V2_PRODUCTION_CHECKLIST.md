# HIOP v2 Production Checklist

## V2F data continuity evidence — 2026-08-09

- [Passed] 8 existing Device UUIDs preserved; 8 remain approved/Active.
- [Passed] 8 devices retain linked V2 discovery evidence; no replacement inventory rows created.
- [Passed] 667 monitoring observations inspected; zero missing Device references.
- [Passed] Existing device-linked incident retained; zero incident orphans.
- [Passed] Duplicate scan found zero normalized MAC, hostname, or IP groups.
- [Passed] Reconciliation is idempotent, audited, and preserves authoritative inventory values.
- [Passed] Alembic remains at one head, `9f1a2b3c4d70`; no V2F migration required.
- [Pending] Live SNMP/AD provider validation requires configured read-only endpoints.

See `HIOP_V2F_RECONCILIATION_REPORT.md` for the point-in-time comparison and limitations.

Acceptance status: **Pilot required / release blocked** as of 2026-07-28. Owner and deployment evidence remain to be supplied by the release operator.

- Set `APP_VERSION=2.0.0-rc1`, strong `SECRET_KEY`, encryption keys, database URL, and production CORS.
- Run `alembic upgrade head`; record `alembic current` and take a PostgreSQL backup.
- Verify restore, HTTPS, proxy headers, WebSockets, scheduler single-worker ownership, and health checks.
- Enable Discovery, LDAP/LDAPS, SNMP, topology, and analytics independently with approved private ranges and read-only pilot scope.
- Rotate secrets through supported write-only flows; never place credentials in logs, exports, screenshots, or source control.
- Configure retention, monitoring, structured logs, backups, alert notification delivery, and rollback ownership.
- Review analytics rule thresholds, baseline coverage, event limits, maintenance windows, and protected audit/source records.
- Complete pilot acceptance and security review before enabling production writes or expanding device scope.

## Evidence status

- [Passed] Application and frontend automated tests recorded in `HIOP_V2_ACCEPTANCE_REPORT.md`.
- [Passed] Alembic head `e7f8a9b0c1d2` verified.
- [Passed] Compose configuration validated with safe placeholders.
- [Not verified] Backup/restore drill.
- [Not verified] Rollback/redeploy drill.
- [Blocked] Docker image build and controlled startup pending an available Docker engine.
- [Blocked] Controlled pilot owner, approved scope, dates, and acceptance metrics pending.
- [Not verified] Production-scale performance and browser matrix.
