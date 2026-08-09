# HIOP v2 Production Acceptance Report

## V2F focused continuity addendum — 2026-08-09

The active V1/V2 product surface passed the V2F data-preservation checkpoint. Eight
existing inventory devices, their UUIDs, and their approval states were preserved.
All eight are connected to V2 discovery evidence; none was recreated. The database
contained 667 monitoring observations, one device-linked incident, and zero orphan
references. Duplicate scanning found zero MAC, hostname, or IP duplicate groups and
zero ambiguous candidates. V2F introduced no schema migration and no data loss.

The detailed point-in-time evidence is in `HIOP_V2F_RECONCILIATION_REPORT.md`.
Live SNMP/AD handshakes, backup/restore, containers, and deployment-specific pilot
work remain separate environment acceptance items. Historical acceptance material
below is retained for audit context; its old test counts and migration revision are
not the current focused V1/V2 checkpoint.

## Decision

**Pilot required before final release. Release blocked.** The repository is at `2.0.0-rc1` with one migration head and passing automated regression suites, but production acceptance cannot be claimed because backup/restore, application rollback, container startup, browser acceptance, and controlled pilot execution were not verified in this environment. The final `2.0.0` version and tag must not be created yet.

## Acceptance matrix

| Area | Status | Evidence / notes |
|---|---|---|
| Authentication | Passed | Existing backend authentication/security tests; no bypass findings in automated suite. |
| Authorization | Passed | Existing role and object-access regression tests; backend remains authoritative. |
| Device inventory | Passed | Existing full backend regression suite. |
| Discovery | Passed | Existing discovery/security regression tests with mocks; no hotel scan. |
| Import | Passed | Existing import/finalization/rollback contract tests with synthetic fixtures. |
| Active Directory | Passed | Existing AD contract and regression tests with mocks; no real directory. |
| SNMP | Passed | Existing SNMP client/onboarding/contract tests; no real devices. |
| Topology | Passed | Existing topology and operations tests with synthetic data. |
| Analytics | Passed | 374 backend tests + 11 subtests; analytics APIs and migration verified. |
| Alerts | Passed | Existing alert lifecycle regression tests. |
| Tickets | Passed | Existing ticket workflow regression tests. |
| Audit | Passed | Existing audit/security regression tests; no secrets in new analytics evidence. |
| Reports | Passed | Existing report/export tests and formula-safe analytics export checks. |
| Settings | Passed | Existing settings tests and startup configuration validation. |
| Scheduler | Passed | Scheduler regression tests; analytics job IDs are deterministic and disabled by default. |
| WebSockets | Passed | Existing WebSocket contract tests; no raw evidence broadcasts added. |
| Notifications | Passed | Existing notification tests; no real notification delivery attempted. |
| Database migrations | Passed | `alembic current`, `heads`, history, and upgrade to `e7f8a9b0c1d2`; one head. |
| Backup and restore | Not verified | No safe database backup/restore environment was available; procedure documented separately. |
| Deployment | Blocked | Compose config validates with placeholders; Docker engine/image startup was not available. |
| Security | Not verified | Static review and `pip check` passed; npm audit reports two high React Router advisories with no fix available. |
| Performance | Not verified | Automated bounded-query tests pass; production-scale load measurements were not run. |
| Documentation | Passed | RC, analytics, production checklist, pilot, backup, and rollback documents present. |
| Pilot readiness | Blocked | Pilot plan exists, but no approved owner/scope/date or execution evidence was supplied. |
| Rollback readiness | Not verified | Forward-fix and restore guidance documented; redeployment/restore drill not executed. |

## Commands and results

- Backend: `python -m pytest -q` — **374 passed, 11 subtests passed, 7 warnings**.
- Frontend: `npm.cmd run lint` — passed.
- Frontend: `npm.cmd test` — **23 passed**.
- Frontend: `npm.cmd run build` — passed.
- Backend: `pip check` — no broken requirements.
- Alembic: current/head `e7f8a9b0c1d2`; upgrade succeeded.
- Docker: `docker compose config --quiet` passed with non-production placeholders; image/startup checks not run because Docker engine was unavailable.
- Dependency audit: `npm audit --omit=dev` reports two high React Router advisories, no fix available.

## Release blockers and required evidence

1. Execute a safe PostgreSQL backup, restore it into a separate database, start the backend against the restored database, and verify key reads/authentication.
2. Execute the documented rollback/redeploy drill and record migration limitations.
3. Build and start backend/frontend containers with the target deployment engine; verify health, database connectivity, scheduler singleton, and WebSockets.
4. Run the controlled pilot plan with named owner/approver and synthetic/read-only approved scope.
5. Review the React Router advisories and document the SPA mitigation or apply an upstream-supported fix.

Until these items have evidence, release remains **blocked** and version/tag must remain `2.0.0-rc1`.
