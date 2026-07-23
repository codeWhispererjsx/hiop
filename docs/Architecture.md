# HIOP 2.0.0-dev architecture

## Epic 3A Active Directory integration foundation

Epic 3A adds a secure backend-only Active Directory integration foundation. `ActiveDirectoryConnection` models connection profiles; `ActiveDirectorySyncConfiguration` manages per-domain sync options; `ActiveDirectoryObject` stages directory users, computers, and groups; `ActiveDirectorySyncRun` captures execution telemetry; and `ActiveDirectoryMatchCandidate` matches staged directory objects against HIOP users and devices. Bind secrets use authenticated Fernet encryption, are treated as write-only, and are excluded from API outputs. No live LDAP connections, scheduled background sync, automatic mutations, or frontend admin pages are registered. See `docs/ACTIVE_DIRECTORY.md`.

## Epic 2E final import

Final inventory import is a backend-orchestrated state machine. A versioned plan and unique per-row execution results provide idempotency; session row locks, configurable batches, and row savepoints provide concurrency and failure isolation. Before/after snapshots support later-change-aware compensating rollback without deleting inventory history or audit records. See `docs/IMPORT_ARCHITECTURE.md`.

## Intelligent inventory import foundation

Epic 2A adds a backend-only staging bounded context beside official inventory and Discovery. `ImportSession` owns staged `ImportedDevice` rows; repositories provide persistence only; an unimplemented `ImportService` reserves orchestration; and abstract field validators reserve future normalization contracts. No API, parser, matcher, approval flow, inventory merge, scheduler, or frontend is registered. See `IMPORT_ARCHITECTURE.md`.

## System shape

HIOP is a three-tier internal operations application:

```text
Browser (React + TypeScript)
        | HTTPS REST + authenticated WebSocket
Nginx reverse proxy
        | /api/v1 and /ws/dashboard
FastAPI application
        | SQLAlchemy / Alembic
PostgreSQL
        |
Approved private network targets (ICMP scanner)
```

The frontend is a Vite single-page application. React Router owns navigation and lazy-loads each page. A centralized API client attaches the session-scoped JWT, normalizes errors, coalesces identical in-flight GET requests, and redirects invalid sessions to login. `DashboardLayout` owns one authenticated WebSocket connection and distributes live device-status events to active pages.

FastAPI groups thin route modules around authentication, devices, scanner operations, tickets, users, audit, reports, hierarchy, dashboard, settings, and WebSockets. Services contain mutation/query logic. Pydantic schemas validate transport data. SQLAlchemy sessions are dependency-scoped and mutations roll back on failure.

The Discovery foundation is backend-only. Its SQLAlchemy models and Alembic migration reserve persistence and identity constraints; persistence-only repositories isolate database access; and an unimplemented service contract reserves later orchestration boundaries. Epic 1A registers no route, scheduler job, scanner, approval flow, inventory mutation, or frontend page. See `DISCOVERY.md`.

## Security boundaries

- Login issues an expiring JWT with issuer, issued-at, and unique-token claims.
- Bearer tokens are stored in `sessionStorage`, removed on logout/401, and never placed in URLs or logs.
- The WebSocket requires the token as a subprotocol and verifies an active user.
- Backend role checks are authoritative. Administrators manage users, hierarchy, reports, audit, and settings; technicians receive only supported operational access.
- Passwords are bcrypt-hashed. Responses never contain hashes.
- Range and single-device scans are restricted to the persisted approved private CIDR.
- Deployment secrets remain environment-only and are excluded from settings responses and audit descriptions.

Because bearer authentication uses an explicit `Authorization` header rather than ambient cookies, browser CSRF is not the primary threat. CORS remains allow-listed, while XSS prevention and token lifetime limit token theft risk.

## Operational flows

### Device monitoring

An administrator or technician scans an inventory device, or the embedded scheduler scans active inventory. Each attempt creates a `network_scans` row and updates `Device.network_status`. A real status transition may persist an alert, create an offline ticket according to settings, and emit `device_status_changed` over the authenticated socket.

Inventory lifecycle (`Active`, `Inactive`, `Retired`) is deliberately separate from network state (`Online`, `Offline`, `Unknown`). Retirement is a soft operation and preserves scans, alerts, tickets, and audit history.

### Ticket lifecycle

Authenticated users may report tickets. Supported staff assign and close them; admins may delete. Device relationships are real foreign keys. Administrative mutations create audit entries. Ticket-specific WebSocket events, comments, attachments, and SLA timers are not part of 1.0.0.

### Configuration

Validated non-secret runtime settings are stored in `system_settings`. Secrets and infrastructure configuration remain environment variables. Scheduler changes are applied through one controlled scheduler job. The public settings endpoint returns only safe branding values.

## Deployment

Docker Compose defines PostgreSQL, one-shot migrations, one backend worker, and the Nginx-served frontend. One worker is intentional because APScheduler is embedded in the API process; horizontal API scaling requires moving scheduling behind a distributed lock or dedicated worker. See `DEPLOYMENT.md` and `OPERATIONS.md`.

## Version 1.0.0 limitations

- Alerts support acknowledgement but not a persisted resolved lifecycle or direct ticket ID.
- The scheduler is process-local.
- No refresh tokens, MFA, session revocation, email reset flow, or custom permission model.
- No ticket comments, attachments, SLA engine, or ticket-specific live events.
- No automated backup service, external metrics platform, SIEM integration, or tamper-evident audit chain.
- Discovery currently provides architectural persistence only; it performs no network discovery or workflow actions.
