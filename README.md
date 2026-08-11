# HIOP — Hospitality IT Operations Platform

HIOP is currently focused on Overview, Discover, Monitor, Network Topology,
Manage, Automate, Maintain, and Administration. See
[V1/V2 focused product completion](docs/V1_V2_COMPLETION.md) for verified scope and limitations.
The V1-to-V2 data continuity checkpoint is recorded in
[HIOP V2F reconciliation report](HIOP_V2F_RECONCILIATION_REPORT.md).
The scoped Version 3 topology implementation is documented in
[HIOP V3A topology report](HIOP_V3A_TOPOLOGY_REPORT.md).
V3B adds cached, read-only switch interface and exact-port intelligence on the same V3A graph and V2 device identities; see [HIOP V3B port intelligence report](HIOP_V3B_PORT_INTELLIGENCE_REPORT.md).

Historical later-Version-3 design documents remain in `docs/` for reference, but
their specialist modules are not part of the active V3A product surface.

HIOP Version 3 Epic 6 adds Enterprise Problem Management, structured RCA, the Known Error Database, reusable workarounds, CAPA, post-resolution reviews, deterministic incident-correlation suggestions, relationship graphs, dashboards, reports, exports, and scheduled reminders. See [Problem Management](docs/PROBLEM_MANAGEMENT.md), [KEDB](docs/KNOWN_ERROR_DATABASE.md), [RCA](docs/ROOT_CAUSE_ANALYSIS.md), and [CAPA](docs/CAPA.md).

HIOP v2 analytics includes opt-in scheduled aggregation, bounded historical backfill, data-quality monitoring, and retention controls. See [docs/ANALYTICS.md](docs/ANALYTICS.md).

HIOP 3.0.0-dev is an internal hospitality IT operations platform. It combines device inventory, safe private-network discovery, network monitoring, alerting, service tickets, user administration, immutable audit records, reports, and runtime-safe settings in one authenticated application. The v3 foundation adds organization and property context while preserving existing routes and data.

## Enterprise + Hospitality interface

The React application uses a centralized semantic design system with Royal Blue primary actions, Navy enterprise navigation, Emerald operational health, and sparing Premium Gold hospitality highlights. Shared typography, spacing, radius, shadow, status, focus, and layering tokens drive every module. Light, dark, and system preferences switch instantly and remain stored locally without changing application behavior. See [UI design system](docs/UI.md).

## Epic 5: Enterprise CMDB

HIOP now includes a property-aware Configuration Management Database with reviewed CIs, hospitality taxonomy, lifecycle and attribute history, deterministic dependency/impact analysis, discovery reconciliation, health metrics, reports, and scheduled validation. The workspace is `/cmdb`. See [CMDB](docs/CMDB.md), [CI Relationships](docs/CI_RELATIONSHIPS.md), and [Discovery Reconciliation](docs/DISCOVERY_RECONCILIATION.md).

## Epic 4: Enterprise change and release management

HIOP now includes property-aware RFCs, deterministic risk assessment, technical and CAB approvals, maintenance calendars and conflict detection, reviewed execution and rollback, release records, communication history, audit, reports, and scheduled reminders. The workspace is available at `/changes`. See [Change Management](docs/CHANGE_MANAGEMENT.md), [CAB](docs/CAB.md), [Release Management](docs/RELEASE_MANAGEMENT.md), and [Maintenance Windows](docs/MAINTENANCE_WINDOWS.md).

## Epic 3D: Knowledge operations

HIOP now includes a property-aware Knowledge & Runbooks workspace for reviewed Markdown articles, immutable runbooks, SOP acknowledgement, service catalogs, document versions, troubleshooting guides, operational checklists, deterministic enterprise search, approvals, relationships, reports, and scheduled content maintenance. See [Knowledge Base](docs/KNOWLEDGE_BASE.md), [Runbooks](docs/RUNBOOKS.md), and [Search](docs/SEARCH.md).

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

## Version 3 Epic 9.5

HIOP now includes policy-bounded enterprise discovery, deterministic fingerprinting and confidence, reviewed topology, encrypted opt-in credentials, and identifier-deduplicated CMDB synchronization. See [Discovery Engine](docs/DISCOVERY_ENGINE.md) and [Discovery Pipeline](docs/DISCOVERY_PIPELINE.md).
