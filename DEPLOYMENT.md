# HIOP Production Deployment

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

Do not run schema downgrades in production. Apply upgrades in a maintenance window after a verified backup. Review new migrations before deployment and keep application rollback images available; schema rollback requires an explicit recovery plan.

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

`GET /health` is unauthenticated and intentionally contains no secrets. It reports API, PostgreSQL, application version, environment, UTC timestamp, scheduler state, WebSocket availability/active count, scanner availability, and last scan. It returns `503` when required components are degraded. Frontend Nginx exposes `/healthz`.

Monitor:

- HTTP status and latency for `/health` and `/healthz`
- authentication `401/403/429` rates
- API error and latency percentiles
- WebSocket connection/reconnect counts
- scheduler scan completion/failure messages and age of `last_scan`
- PostgreSQL connections, locks, storage, replication/backup age, and slow queries
- container restarts, CPU, memory, disk, and network reachability

Logs are JSON on stdout/stderr and include timestamp, level, logger, and message. Route application/access/error/security streams in the log collector using the logger field. Never enable SQL echo (`DEBUG=true`) in production or collect Authorization/WebSocket protocol headers.

## Backup and recovery

Back up PostgreSQL outside the source tree and container volume. `scripts/backup-postgres.sh` creates a permission-restricted custom-format dump, checksum, and age-based retention. Provide `PGHOST`, `PGDATABASE`, `PGUSER`, and `PGPASSWORD` securely. Store encrypted copies off-host and define RPO/RTO with the hotel.

Test restoration quarterly in an isolated database. `scripts/restore-postgres.sh` requires an explicit `CONFIRM_RESTORE=RESTORE_HIOP`, verifies the checksum when present, and performs a destructive clean restore. Take a rollback backup and stop application writes first. After restore, run `alembic upgrade head`, start HIOP, verify `/health`, authenticate, open each module, and confirm scan/audit continuity before reopening traffic.

There are no uploaded assets in HIOP v1.0. Back up deployment manifests, encrypted environment/secrets through their owning platform, TLS certificates according to CA policy, and operational runbooks. Never include secrets or dumps in Git.

## Release procedure

1. Review the release commit and dependency advisories.
2. Build immutable images tagged with commit SHA; scan and sign them.
3. Confirm a recent successful backup and restore test.
4. Deploy migration job once.
5. Deploy backend, then frontend; wait for health checks.
6. Verify login, API, PostgreSQL data, WebSocket Live status, scanner, scheduler, and audit events.
7. Monitor error rate and latency; rollback the application image if required. Do not blindly downgrade the database.
