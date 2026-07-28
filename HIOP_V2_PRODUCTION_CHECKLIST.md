# HIOP v2 Production Checklist

- Set `APP_VERSION=2.0.0-rc1`, strong `SECRET_KEY`, encryption keys, database URL, and production CORS.
- Run `alembic upgrade head`; record `alembic current` and take a PostgreSQL backup.
- Verify restore, HTTPS, proxy headers, WebSockets, scheduler single-worker ownership, and health checks.
- Enable Discovery, LDAP/LDAPS, SNMP, topology, and analytics independently with approved private ranges and read-only pilot scope.
- Rotate secrets through supported write-only flows; never place credentials in logs, exports, screenshots, or source control.
- Configure retention, monitoring, structured logs, backups, alert notification delivery, and rollback ownership.
- Review analytics rule thresholds, baseline coverage, event limits, maintenance windows, and protected audit/source records.
- Complete pilot acceptance and security review before enabling production writes or expanding device scope.
