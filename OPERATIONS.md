# HIOP Operations Guide

## Final inventory import operations

Confirm server readiness and the displayed plan version before finalization. Do not manually restart a session in `importing`; refresh its persisted results. Investigate `partial` sessions by safe error code and retry only through the retry endpoint.

Rollback requires a fresh preview. If any action is non-reversible, investigate later edits rather than changing the database manually. Successful compensation preserves import and audit history. Monitor `import_finalization_*` and `import_rollback_*` events, grouped notifications, database locks, and result retention.

## Daily checks

- Confirm frontend `/healthz` and backend `/health` are healthy.
- Confirm database status is available, scheduler is running (or intentionally disabled), and `last_scan` is recent.
- Review offline devices, active alerts, open tickets, failed authentication/rate-limit events, scheduler failures, and container restarts.
- Check PostgreSQL disk capacity, connection usage, locks, backup age, and the previous backup checksum.
- Confirm TLS certificate expiry is more than 30 days away and automated renewal is healthy.

## Safe restart

Docker Compose:

```bash
docker compose ps
docker compose restart backend
docker compose restart frontend
docker compose ps
```

Avoid restarting PostgreSQL unless required. For a full controlled restart:

```bash
docker compose down
docker compose up -d
```

Do not use `down -v`; it deletes the named database volume. After any restart, verify health, login, WebSocket Live state, scheduler state, and one read-only module view.

For systemd, use `systemctl restart hiop-backend` and `systemctl reload nginx`, then check `systemctl status` and the health endpoints.

## Logs

```bash
docker compose logs --since=30m backend
docker compose logs --since=30m frontend
docker compose logs --since=30m db
```

Application, access, error, and security records are emitted as structured container logs and distinguished by logger/level. Forward them to a protected centralized platform with retention and access controls. Redact Authorization and `Sec-WebSocket-Protocol`; never collect environment dumps, passwords, email credentials, database URLs, or request bodies containing secrets.

Audit logs are immutable application records stored in PostgreSQL and viewed through the admin Audit Center. They are not a replacement for infrastructure/security logs.

## Common incidents

### Login reports backend unavailable

1. Check `/health` and backend container state.
2. Confirm frontend `/api/` proxies to `backend:8000`.
3. Check migration-service completion and database health.
4. Check allowed production origin and TLS hostname.
5. Do not log or copy the user's token.

### WebSocket remains reconnecting

1. Confirm normal authenticated APIs work.
2. Verify Nginx forwards Upgrade/Connection and the WebSocket subprotocol header.
3. Confirm the public scheme is HTTPS/WSS and proxy read timeout exceeds the reconnect interval.
4. Look for `4401` (expired/invalid session) and ask the user to sign in again.

### Scheduler stopped or scans stale

1. Check `SCHEDULER_ENABLED` and `/health`.
2. Confirm only one backend instance is running.
3. Review scheduler errors, approved CIDR, `NET_RAW`, firewall rules, and device reachability.
4. Restart only the backend after correcting configuration; ensure no duplicate scan job appears.

### Database unavailable

1. Stop write traffic if integrity is uncertain.
2. Check PostgreSQL health, disk, memory, connections, and network.
3. Do not reset the volume or run a downgrade.
4. Escalate to the database owner; restore only under the documented recovery procedure.

### Migration service failed

Inspect `docker compose logs migrate`, verify the database backup, compare `alembic current` and `alembic heads`, and correct the migration/configuration. Never mark a revision manually without confirming the actual schema.

## Performance monitoring

Track p50/p95/p99 API latency, error rate, PostgreSQL query latency and pool saturation, WebSocket reconnects, scheduler duration, frontend load timings, container resources, and storage growth. Establish baselines before alerts. The current embedded scheduler limits backend horizontal scaling; separate it before adding replicas.

## Backup verification

- Run a scheduled daily custom-format PostgreSQL backup.
- Verify exit status, nonzero file size, SHA-256 checksum, encryption, off-host replication, and retention.
- Alert when backup age exceeds the RPO.
- Perform a quarterly isolated restore and record duration/results without copying sensitive data into tickets.
- Review `DEPLOYMENT.md` before any destructive restore.

## Escalation record

For every production incident record timestamps, symptoms, affected modules, health output, safe log references, actions, recovery, and follow-up. Never place credentials, JWTs, database URLs, raw user exports, or private guest/hotel information in incident notes.
