# HIOP v2 Release Candidate

## Scope

Version `2.0.0-rc1` packages the completed HIOP v2 operations platform: Discovery, reviewed Import, Active Directory, SNMP monitoring, topology collection/inference, analytics aggregation, forecasting, deterministic anomaly detection, correlation, insights, and executive analytics views.

## Architecture and data safety

Analytics intelligence consumes validated aggregates and operational events. Baselines use transparent mean/median/MAD/IQR/percentile methods; anomalies retain bounds, method, threshold, confidence, and limitations. Correlation groups use bounded event windows and probable language. No AI, black-box ML, autonomous remediation, secrets, raw SNMP payloads, or automatic inventory mutation are introduced.

## Database and operations

Apply Alembic through `e7f8a9b0c1d2`, which adds baseline, anomaly rule/anomaly, correlation group/member, and insight tables plus analytics schedule controls. Analytics intelligence jobs are disabled by default and reconcile into deterministic APScheduler IDs. Review retention before cleanup and keep audit/source records protected.

## Security and performance

Rules are controlled schemas without executable formulas. APIs enforce role checks, bounded pagination, event windows, evidence sizes, and review transitions. Indexed status/time and entity/metric queries support incremental evaluation. Correlation traversal and event processing are capped.

## Verification and acceptance

Focused analytics and scheduler tests, frontend tests/build, Alembic upgrade, backend startup, and OpenAPI route checks must pass before pilot use. Production acceptance still requires deployment-specific HTTPS, secrets, backups/restore, monitoring, and approved read-only pilot scope.

## Known limitations and risks

Topology-aware correlation is conservative and currently uses bounded shared-scope evidence; it never claims a confirmed root cause. Baseline coverage depends on sufficient aggregate history. Notification and alert integrations remain policy-controlled. Docker image verification depends on an available Docker engine.

## Rollback and pilot

Rollback uses the prior application image and a tested database backup; do not downgrade after data has been written without an approved migration rollback plan. Start with read-only analytics, synthetic fixtures, approved device ranges, AD dry runs, and a defined issue owner before expanding scope.

Deferred v3 work includes AI assistance, anomaly learning, automated remediation, topology animation, and external BI integrations.
