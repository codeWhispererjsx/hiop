# HIOP 2.0.0-dev administrator guide

## Discovery administration

Discovery is disabled by default. In Settings → Discovery, enter only organization-owned private IPv4 CIDRs, narrow ignore ranges where required, keep the host and concurrency limits conservative, then enable scheduling. Saving replaces the one scheduled Discovery job; it does not create duplicate jobs. Use the Discovery dashboard for manual runs and review. Approval creates an inventory record transactionally; Ignore and Reject retain history. Review audit entries and Discovery reports after operational changes.

Never authorize public, guest, third-party, or otherwise unapproved networks. Discovery performs ICMP, passive local neighbor-cache inspection, and reverse DNS only. Run one scheduler-owning backend worker until a distributed scheduler lock is implemented.

## Responsibilities

Administrators own deployment secrets, database migrations, account lifecycle, approved scan scope, settings, backups, audit review, and release validation. Frontend controls are not a security boundary; verify backend responses and audit records for privileged changes.

## Deployment and upgrades

Follow `DEPLOYMENT.md`. Populate production environment variables outside Git, enforce HTTPS, run a verified backup, execute the one-shot Alembic migration, start one backend worker, then start the frontend proxy. Validate `/health`, login, WebSocket connectivity, a read-only module sweep, and backup status before opening access.

Version 1.0.0 keeps APScheduler in the backend process, so do not scale backend replicas without first externalizing scheduling or adding a distributed lock.

## Users and permissions

Supported stored roles are `admin`, `technician`, and legacy `staff`; global administration remains admin-only. Create accounts with unique username/email and a strong temporary password. Use deactivation rather than deletion to preserve ticket and audit references. HIOP prevents self-deactivation and removal of the last active admin. Resetting a password never reveals the prior password or hash.

## Scanner administration

Set `approved_network` to the exact private CIDR authorized for the property. Single-device and range scans are rejected outside it. Use conservative timeouts, worker counts, intervals, and offline thresholds. Confirm the scheduler state after changing network settings and ensure only one scheduler job exists.

`NET_RAW` is required for ICMP in the production backend container. Do not grant host networking or arbitrary command execution.

## Backups and recovery

Use the scripts and procedures in `OPERATIONS.md`. Keep encrypted backups off-host, record retention, test restores regularly, and verify restored migrations and authentication in isolation. A backup that has never passed a restore drill is not production-ready.

## Monitoring

Monitor public `/health`, Nginx access/error logs, backend application/error/security logs, PostgreSQL capacity, scheduler state, scan freshness, WebSocket reconnect rates, and backup completion. Audit records are application data, not a substitute for infrastructure/security logs.

## Maintenance and troubleshooting

- API unavailable: check container/process health, database connectivity, migration state, and backend error logs.
- Login failures: verify active status, generic 401 behavior, throttle state, clock synchronization, and JWT environment configuration.
- Stale monitoring: check scheduler state, approved CIDR, ICMP capability, scan timestamps, and device network policy.
- WebSocket offline: verify `/ws/dashboard` proxy upgrade headers and token subprotocol handling.
- Migration failure: stop rollout, retain logs, restore only through the documented recovery decision, and never edit Alembic history manually in production.

## Security rules

Never expose `.env`, JWT secrets, SMTP passwords, database URLs, hashes, backups, or exported reports. Rotate secrets through the deployment environment, not Settings. Review `SECURITY_REPORT.md` before production and after material dependency or infrastructure changes.

## Release and rollback

Use `PRODUCTION_CHECKLIST.md`. Record the deployed commit and image digest. Roll back application images only with schema compatibility confirmed; otherwise restore the matching database backup in an isolated recovery workflow. Preserve logs and audit evidence throughout an incident.
