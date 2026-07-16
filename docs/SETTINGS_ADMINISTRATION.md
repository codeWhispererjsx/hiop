# HIOP Settings and Administration

## Configuration classification

HIOP separates configuration into three security classes:

1. **Database-backed runtime settings** — application display defaults, organization profile, scanner scheduling and safe scanner behavior, and notification policy. These are explicit schema fields stored in `system_settings`; arbitrary keys are not accepted.
2. **User/browser preferences** — light, dark, or system appearance is stored in the browser under `hiop_theme`. The startup script applies it before React renders to prevent a theme flash.
3. **Environment-only deployment configuration** — `SECRET_KEY`, `DATABASE_URL`, email address/password, connection credentials, tokens, private keys, and raw connection strings. These are never returned by Settings APIs and cannot be edited in the UI.

## Settings APIs

- `GET /api/v1/settings` — complete non-secret administration bundle (admin only)
- `GET /api/v1/settings/public` — authenticated application/property branding
- `PUT /api/v1/settings/general` — global display and formatting defaults (admin only)
- `PUT /api/v1/settings/organization` — organization profile (admin only)
- `PUT /api/v1/settings/network` — validated private-network and scheduler controls (admin only)
- `PUT /api/v1/settings/notifications` — notification policy, without SMTP secrets (admin only)
- `GET /api/v1/settings/system-health` — secret-safe live component status (admin only)

Every mutation writes a safe audit event in the same database transaction. SMTP credentials, passwords, tokens, connection strings, and private keys are excluded from responses and audit descriptions.

## Departments and locations

Departments, properties, buildings, floors, rooms, and network zones use the normalized hierarchy introduced before Epic 10. Settings links to that existing administration workflow instead of creating a second hierarchy system. Names are case-insensitively unique, deactivation is soft, and device string values remain preserved for compatibility and history.

## Scanner behavior

The automatic scan interval is reloaded into the existing APScheduler job without creating duplicate jobs. Intervals below five minutes are rejected. Manual range scans must be a subnet of the saved approved private CIDR. Ping timeout and automatic alert/offline-ticket choices are read from the database during scans. Retired devices remain excluded by the existing inventory rule.

The approved network remains a runtime guard; firewall rules and deployment network boundaries remain infrastructure responsibilities.

## Email configuration

The UI reports only whether email is configured and safe transport metadata. SMTP credentials remain environment variables. Blank-password replacement, runtime SMTP mutation, and test email are intentionally unavailable because the project has no external secrets manager or encrypted credential store.

## PostgreSQL backup and restore guide

HIOP has no application-managed backup or restore engine. Operators should:

1. Run `pg_dump` using a secured deployment service account outside the repository.
2. Encrypt and copy the dump to access-controlled off-host storage.
3. Apply a retention policy appropriate to the deployment.
4. Test restoration with `pg_restore` in an isolated environment.
5. Stop application writes or follow an approved consistency procedure before a production restore.

Database clearing, arbitrary SQL, shell execution, destructive restore, and backup-file downloads are deliberately not exposed in the web application.

## Remaining security and administration gaps

- Secure logo/file uploads and managed object storage
- Automated backup history, scheduling, retention, and restore workflow
- External secrets manager and encrypted runtime SMTP credential rotation
- Test-email rate limiting and delivery history
- Multi-property organization profiles
- Refresh tokens, MFA, session revocation, and custom permissions
- Login-failure auditing and security-event correlation
- Per-user server-side preferences and density/sidebar preferences
