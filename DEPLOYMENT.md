# HIOP Production Deployment

## Vercel frontend deployment

HIOP uses a split production architecture. Vercel hosts the compiled React frontend. FastAPI, PostgreSQL, WebSockets, the scheduler, discovery, monitoring, backups, and agent ingestion must run on a persistent backend host.

1. Deploy the backend first and confirm `https://<backend-host>/healthz` returns healthy.
2. Import the repository root into Vercel. The root `vercel.json` builds `frontend/` and preserves React Router deep links.
3. Add `VITE_API_URL=https://<backend-host>/api/v1` and `VITE_WS_URL=wss://<backend-host>/ws/dashboard` to the Vercel Production environment.
4. Set the backend `CORS_ORIGINS` to a JSON list containing the exact Vercel production URL and only the preview URLs you intentionally support.
5. Redeploy after changing either Vite variable because Vite embeds them at build time.

The Vercel build intentionally fails when either endpoint is missing or insecure. Do not deploy FastAPI as a Vercel function: HIOP requires persistent processes, WebSockets, scheduled jobs, database pooling, and local-network integrations.

## Architecture

The supported v1.0 topology is:

`Browser → TLS Nginx → frontend Nginx → FastAPI/Uvicorn → PostgreSQL`

The frontend Nginx serves immutable Vite assets, falls back to `index.html` for React Router, proxies `/api/`, and upgrades `/ws/`. FastAPI owns authentication, authorization, the scanner, audit records, and one embedded APScheduler instance. PostgreSQL stores all operational state in a persistent volume.

HIOP v1.0 must run one backend process while the scheduler is embedded. Multiple Uvicorn workers or backend replicas would each start a scheduler and can duplicate scans. Scale the reverse proxy and database independently; move scheduling to a dedicated worker with a distributed lock before scaling the API horizontally.

## Requirements

- Docker Engine 24+ and Docker Compose v2, or Python 3.12, Node.js 22, Nginx, and PostgreSQL 16 for manual deployment.
- A DNS hostname, TLS certificate, and outbound SMTP/network access as required by the deployment.
- Linux `NET_RAW` capability for the backend scanner container. Restrict the approved CIDR through HIOP settings and network firewall rules.
- A secrets manager or protected deployment environment. Never store production values in the repository.

## Environment profiles

- Development: copy `backend/.env.example` to `backend/.env`; Vite reads `frontend/.env.development`.
- Testing: copy `backend/.env.testing.example` to a temporary untracked `.env`; Vite test mode reads `frontend/.env.test`.
- Production: use `backend/.env.production.example` as a key reference only. Inject values through Compose, the orchestrator, or a secrets manager. Vite uses same-origin `/api/v1` and derives `wss://<host>/ws/dashboard` under HTTPS.

Required backend settings:

- `APP_NAME`, `APP_VERSION`, `ENVIRONMENT`, `DEBUG`
- `DATABASE_URL`
- `SECRET_KEY` of at least 32 cryptographically random characters
- `CORS_ORIGINS` as a JSON list containing only production HTTPS origins
- `ACCESS_TOKEN_EXPIRE_MINUTES`
- `LOG_LEVEL`
- `DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW`, `DATABASE_POOL_RECYCLE_SECONDS`
- `SCHEDULER_ENABLED`
- Dedicated credential encryption keys: `HIOP_AD_SECRET_KEY`, `HIOP_SNMP_SECRET_KEY`, and `HIOP_DISCOVERY_CREDENTIAL_KEY` (32+ random characters each)
- Optional `EMAIL_ADDRESS`, `EMAIL_PASSWORD`, and `EMAIL_RECIPIENT`

Generate secrets outside the repository, for example with a managed secrets service or `openssl rand -hex 32`. Do not paste generated values into tickets, logs, or documentation.

## Docker Compose deployment

Create an untracked root `.env` or inject these variables from the deployment system:

```text
HIOP_HOST=hiop.example.com
POSTGRES_DB=hiop
POSTGRES_USER=hiop
POSTGRES_PASSWORD=<secret>
DATABASE_URL=postgresql+psycopg2://hiop:<URL-encoded-secret>@db:5432/hiop
SECRET_KEY=<64-character-random-secret>
HIOP_AD_SECRET_KEY=<64-character-random-secret>
HIOP_SNMP_SECRET_KEY=<64-character-random-secret>
HIOP_DISCOVERY_CREDENTIAL_KEY=<64-character-random-secret>
```

URL-encode reserved characters in the database password when constructing `DATABASE_URL`. Keep `POSTGRES_PASSWORD` as the original unencoded value for PostgreSQL initialization.

Validate and start:

```bash
docker compose config
docker compose build --pull
docker compose up -d
docker compose ps
```

Compose waits for PostgreSQL, runs `alembic upgrade head` as a one-shot migration service, starts one backend worker, then exposes frontend Nginx on port `8080` by default. PostgreSQL data persists in `hiop_postgres_data`. The database is not published to the host network.

On a genuinely empty database, Alembic creates the current application schema as a deterministic baseline, creates the required public-ID sequences and initial plan configuration, and records the current migration head. A database containing any application tables is never treated as empty and continues through the normal incremental migration path.

Do not run schema downgrades in production. Apply upgrades in a maintenance window after a verified backup. Review new migrations before deployment and keep application rollback images available; schema rollback requires an explicit recovery plan.

## Clean installation and first administrator

The supported clean-install sequence is deterministic and requires no source edits:

1. Configure all required environment variables and secrets.
2. Run `docker compose config`; placeholder or missing production values must fail here or during application settings validation.
3. Run `docker compose build --pull` and `docker compose up -d db`.
4. Run `docker compose run --rm migrate`. It must complete `alembic upgrade head` before the API starts.
5. Create the one-time first platform administrator interactively:

   ```bash
   docker compose run --rm -it backend python scripts/bootstrap_platform_admin.py --username platform-owner --email owner@example.com
   ```

   The password is entered twice without terminal echo. The command refuses to run if any platform administrator already exists, never overwrites an account, and writes an audit event.
6. Run `docker compose up -d backend frontend`, verify `/health`, `/healthz`, and the frontend `/healthz`, then sign in at `/login`.
7. Create the customer organization, initial property, and organization administrator through the Platform Control Center. A new organization must show zero operational records.

The migration service may be rerun safely when already at head; it does not bootstrap users or reset data. Never use `backend/scripts/reset_operational_data.py` in a production installation.

## Supported upgrade baseline

The supported baseline is any database whose Alembic revision is present in this repository's single migration chain. Before upgrading, record `alembic current`, create and verify a PostgreSQL custom-format backup, review all revisions between current and head, and rehearse the upgrade on an isolated restore. Databases with missing, manually stamped, or unknown revisions require investigation; do not force-stamp them.

Upgrade sequence: stop writes, back up, run the one-shot migration job, deploy one backend replica, deploy the frontend, and run module-level read checks. Rebuilding or recreating application containers does not remove PostgreSQL data. `docker compose down -v`, removing `hiop_postgres_data`, or running a clean restore is destructive.

## Manual backend deployment

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install --requirement requirements.txt
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips=127.0.0.1
```

Run under systemd or another supervisor with restart limits, an unprivileged account, a read-only application directory, and environment values loaded from a protected service credential. Keep one worker until scheduler separation is implemented.

## Frontend build

```bash
cd frontend
npm ci
npm run lint
npm run build
```

Serve only `frontend/dist`; never deploy the Vite development server. The production image uses a multi-stage Node build and Nginx runtime. Hashed assets receive a one-year immutable cache; `index.html` is not cached. Route-level lazy loading remains enabled.

## Nginx and HTTPS

`frontend/nginx.conf` is the internal HTTP configuration. `deploy/nginx/hiop-tls.conf` is an HTTPS-ready host-proxy example. Replace `hiop.example.com`, validate with `nginx -t`, and reload gracefully.

For Let's Encrypt on a conventional host:

```bash
certbot certonly --webroot -w /var/www/certbot -d hiop.example.com
nginx -t && systemctl reload nginx
certbot renew --dry-run
```

Keep port 80 only for ACME and HTTPS redirects. Restrict TLS to 1.2/1.3, enable HSTS only after HTTPS is confirmed for every subdomain, and automate certificate renewal. The frontend CSP, framing, referrer, permissions, compression, static caching, API size limit, and WebSocket forwarding are defined in Nginx.

HIOP uses Authorization-header bearer tokens rather than cookies; secure-cookie configuration is not currently applicable. If cookies are introduced, require `Secure`, `HttpOnly`, `SameSite`, and CSRF protection.

## Health and monitoring

`GET /health` is unauthenticated and intentionally contains no secrets. It reports API, PostgreSQL, application version, environment, UTC timestamp, scheduler state, WebSocket process state, scanner configuration, and last scan. It returns `503` when required components are degraded. Frontend Nginx exposes `/healthz`.

Backend `GET /healthz` is the readiness baseline and checks API process, database connectivity, and scheduler state. Discovery is reported only as configured; this endpoint does not claim that a hotel network or integration is reachable.

**System Health API:** HIOP now provides comprehensive system health monitoring via:
- Platform Control Center → System Health
- API: `/system-health/platform` (platform administrators)
- API: `/system-health/organizations/{org_id}` (organization administrators)

**Health states:** HEALTHY, DEGRADED, STALE, FAILED, NOT_CONFIGURED, UNKNOWN

**Components monitored:** API, Database, Scheduler, Discovery, Monitoring, Alert Processing, Notifications, Agents, Backup

Monitor:

- HTTP status and latency for `/health` and `/healthz`
- authentication `401/403/429` rates
- API error and latency percentiles
- WebSocket connection/reconnect counts
- scheduler scan completion/failure messages and age of `last_scan`
- PostgreSQL connections, locks, storage, replication/backup age, and slow queries
- container restarts, CPU, memory, disk, and network reachability
- System Health component status (API, Database, Scheduler, Backup, etc.)
- Backup age and verification status
- Agent connectivity and queue status

Logs are JSON on stdout/stderr and include timestamp, level, logger, and message. Route application/access/error/security streams in the log collector using the logger field. Never enable SQL echo (`DEBUG=true`) in production or collect Authorization/WebSocket protocol headers.

## Backup and recovery

**Important:** See [DISASTER_RECOVERY_RUNBOOK.md](DISASTER_RECOVERY_RUNBOOK.md) for comprehensive disaster recovery procedures.

Back up PostgreSQL outside the source tree and container volume. `scripts/backup-postgres.sh` creates a permission-restricted custom-format dump, checksum, and age-based retention. Provide `PGHOST`, `PGDATABASE`, `PGUSER`, and `PGPASSWORD` securely. Store encrypted copies off-host and define RPO/RTO with the hotel.

**Backup tracking:** HIOP now tracks backup operations in the database. Monitor backup status via:
- Platform Control Center → Backup & Recovery
- API: `/backup-recovery/health`

**Backup states:**
- HEALTHY: Recent successful backup, verified checksum
- DEGRADED: Backup too old (>48 hours)
- FAILED: Last backup failed
- UNKNOWN: No backup record found

**Current RPO:** 24 hours (based on daily backup schedule)
**Current RTO:** 34-70 minutes (restore + migrations + validation)

Test restoration quarterly in an isolated database. `scripts/restore-postgres.sh` requires an explicit `CONFIRM_RESTORE=RESTORE_HIOP`, verifies the checksum when present, and performs a destructive clean restore. Take a rollback backup and stop application writes first. After restore, run `alembic upgrade head`, start HIOP, verify `/health`, authenticate, open each module, and confirm scan/audit continuity before reopening traffic.

**Secret recovery:** Application secrets (database passwords, encryption keys, API keys) must be recovered through the organization's secure secret-management system. Do NOT store secrets in application backups. If encryption keys are lost, encrypted data cannot be recovered—this is an operational requirement.

There are no uploaded assets in HIOP v1.0. Back up deployment manifests, encrypted environment/secrets through their owning platform, TLS certificates according to CA policy, and operational runbooks. Never include secrets or dumps in Git.

RPO and RTO are **not yet contractually defined**. RPO is determined by the operator's verified backup schedule and off-host replication. RTO is determined by PostgreSQL restore time, migration time, image availability, and validation procedure. Measure both during each recovery rehearsal before setting service commitments.

## Persistence and restart proof

PostgreSQL is the only required persistent application volume: `hiop_postgres_data`. Backend and frontend containers are disposable. For a rehearsal, create uniquely named test organization/property/device records, capture their IDs, restart backend and frontend, restart PostgreSQL in an approved isolated environment, and verify the same IDs through authenticated APIs. Confirm the scheduler job inventory does not duplicate. The supported topology remains exactly one backend process because APScheduler is embedded.

## Local files, imports, and attachments

Current imports are processed through bounded request/temporary data paths; no production attachment/document store is provided. Containers use ephemeral `/tmp`. Do not treat container filesystems as durable storage. If future deployment-specific import staging is enabled, mount a separate permission-restricted volume, define size/retention/cleanup, and include it explicitly in backup scope. PostgreSQL remains authoritative for current product records.

## Release procedure

1. Review the release commit and dependency advisories.
2. Build immutable images tagged with commit SHA; scan and sign them.
3. Confirm a recent successful backup and restore test.
4. Deploy migration job once.
5. Deploy backend, then frontend; wait for health checks.
6. Verify login, API, PostgreSQL data, WebSocket Live status, scanner, scheduler, and audit events.
7. Monitor error rate and latency; rollback the application image if required. Do not blindly downgrade the database.
