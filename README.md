# HIOP — Hotel IT Operations Portal

HIOP 2.0.0-dev is an internal operations portal for hotel IT teams. It combines device inventory, safe private-network discovery, network monitoring, alerting, service tickets, user administration, immutable audit records, reports, and runtime-safe settings in one authenticated application.

Reviewed CSV/XLSX inventory sessions can now be finalized transactionally. Administrators receive server readiness checks, versioned plans, create/link/enrich/merge execution, Discovery linking, persistent results, safe retry, and compensating rollback. Unreviewed imports, Active Directory, SNMP, and scheduled imports remain unsupported.

## Release status

Version `2.0.0-dev` contains the integrated Discovery module and is not a release. Discovery is disabled by default; administrators must configure authorized private CIDRs before enabling scheduled runs. The Version 1.0.0 release evidence remains in [RELEASE_CANDIDATE.md](RELEASE_CANDIDATE.md).

## Technology

- React 19, TypeScript, Vite, React Router
- FastAPI, Pydantic, SQLAlchemy, Alembic, APScheduler
- PostgreSQL 16
- JWT bearer authentication and authenticated WebSocket updates
- Docker Compose and Nginx production deployment

## Local development

Prerequisites: Node.js 20+, Python 3.12+, and PostgreSQL.

1. Copy `backend/.env.example` to `backend/.env` and supply local values. Never commit that file.
2. Install backend dependencies from `backend/requirements.txt`.
3. From `backend`, run `alembic upgrade head`, then start FastAPI:

   ```powershell
   uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
   ```

4. From `frontend`, install and start the UI:

   ```powershell
   npm ci
   npm run dev
   ```

5. Open `http://localhost:5173`. API documentation is at `http://127.0.0.1:8001/docs` in development.

The committed development frontend configuration targets port `8001`; production uses same-origin `/api/v1` and `/ws/dashboard` behind Nginx.

## Verification

```powershell
cd frontend
npm run lint
npm run build

cd ..\backend
python -m unittest discover -s tests -v
python -m compileall -q app
alembic current
alembic heads
```

Production and container commands are documented in [DEPLOYMENT.md](DEPLOYMENT.md). Operational checks, backup, restore, and incident procedures are in [OPERATIONS.md](OPERATIONS.md).

## Documentation

- [Architecture](docs/Architecture.md)
- [API contract](docs/API.md)
- [Database design](docs/Database.md)
- [User guide](USER_GUIDE.md)
- [Administrator guide](ADMIN_GUIDE.md)
- [Developer guide](DEVELOPER_GUIDE.md)
- [Security report](SECURITY_REPORT.md)
- [Performance report](PERFORMANCE_REPORT.md)
- [Project status](PROJECT_STATUS.md)
- [Bug tracker](BUG_TRACKER.md)
- [Changelog](CHANGELOG.md)

## Security

Never commit `.env` files, credentials, tokens, database dumps, exports, backups, virtual environments, `node_modules`, or build output. Report security concerns through the organization’s internal IT security process; do not place secrets in tickets or audit descriptions.

HIOP is internal-use software. No public license is granted unless the repository owner states otherwise.
