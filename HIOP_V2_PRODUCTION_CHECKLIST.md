# HIOP v2 Production Checklist

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
