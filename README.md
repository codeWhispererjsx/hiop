# HIOP — Hospitality IT Operations Platform

HIOP v2 analytics includes opt-in scheduled aggregation, bounded historical backfill, data-quality monitoring, and retention controls. See [docs/ANALYTICS.md](docs/ANALYTICS.md).

HIOP 3.0.0-dev is an internal hospitality IT operations platform. It combines device inventory, safe private-network discovery, network monitoring, alerting, service tickets, user administration, immutable audit records, reports, and runtime-safe settings in one authenticated application. The v3 foundation adds organization and property context while preserving existing routes and data.

Epic 3C adds property-scoped incident command and immutable operational
playbooks. Authorized teams can coordinate roles, tasks, checklists, evidence,
approved-template communications, deterministic escalation, human-reviewed
remediation, verified recovery, closure, and post-incident review from
`/incidents`. See [Incident management](docs/INCIDENT_MANAGEMENT.md).

Epic 5D adds the interactive `/topology` workspace: bounded React Flow maps, saved layouts, search/filters, path and impact analysis, conflict/inference review, snapshots/comparison, change history, and authenticated live updates. It does not schedule collection or configure devices.

Reviewed CSV/XLSX inventory sessions can now be finalized transactionally. Administrators receive server readiness checks, versioned plans, create/link/enrich/merge execution, Discovery linking, persistent results, safe retry, and compensating rollback. Unreviewed imports, Active Directory, SNMP, and scheduled imports remain unsupported.

## Release status

The active development version is `3.0.0-dev`; the v2 production acceptance
evidence remains archived in [HIOP_V2_ACCEPTANCE_REPORT.md](HIOP_V2_ACCEPTANCE_REPORT.md).
Discovery and all integration schedulers remain subject to their explicit safe
configuration and authorization controls.

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
# HIOP v2 SNMP monitoring

Version `2.0.0-rc1` includes the Epic 4D SNMP Monitoring workspace at `/snmp`: secure credential/target administration, structured tests, approved manual collection, candidate review, target/interface monitoring, bounded metric charts, state history, retention preview, and reports. It does not schedule polls, generate alert rules, map topology, receive traps, or automatically onboard devices.
> SNMP is opt-in and now supports reviewed onboarding, monitoring, deterministic schedules, maintenance, safe rules,
> and protected retention. It performs no network polling until explicitly enabled and approved.

Epic 5E adds opt-in scheduled topology operations: deterministic LLDP/CDP collection, inference, snapshots, change/health evaluation, protected baselines, maintenance-aware alerts, structural analytics, retention controls, and bounded exports. Scheduling is disabled until an administrator enables both the topology and its reviewed schedule.

Epic 6A adds an additive advanced analytics backend foundation: controlled source mappings, idempotent time buckets, availability with explicit unknown time, explainable health scores, threshold-only capacity assessments, SLA measurements, MTTR/MTBF, data quality, bounded manual runs, and protected APIs. It includes no analytics dashboard, forecasting, AI, anomaly detection, recommendations, or scheduled processing.

Epic 3B adds property-scoped scheduled and internal-event automation. Approved
workflow versions can run from validated interval/calendar schedules or fixed
HIOP events through a transactional outbox, bounded correlation, recovery
cancellation, approval gates, and dead-letter review. No external webhook,
arbitrary code, raw cron, or unreviewed destructive action is supported.
