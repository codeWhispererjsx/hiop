# HIOP v2.0.0 Release Notes (Draft)

## Status

This document is prepared for the `2.0.0-rc1` acceptance cycle. It is not a final release announcement until the acceptance report changes to Approved for final release.

## Highlights

HIOP v2 combines reviewed device discovery and import, Active Directory workflows, secure SNMP monitoring, topology evidence/inference, scheduled analytics, forecasting, deterministic anomaly detection, correlation, insights, dashboards, reports, audit, notifications, WebSockets, and scheduler controls.

### V2F data continuity checkpoint

V2F confirms that V2 enrichment upgrades existing V1 Device records rather than
replacing them. The current checkpoint preserved 8/8 UUIDs and approval states,
retained 667 monitoring observations and all linked incidents, found no duplicate
candidates or broken relationships, and required no database migration. The
administrator reconciliation operation is idempotent and does not overwrite Device
fields; IP-only and ambiguous matches require review.

## Upgrade

Back up PostgreSQL, deploy the approved image, run `alembic upgrade head`, and verify migration head `e7f8a9b0c1d2`. Review `HIOP_V2_PRODUCTION_CHECKLIST.md`, `HIOP_V2_BACKUP_RESTORE_REPORT.md`, and `HIOP_V2_ROLLBACK_PLAN.md` before enabling integrations.

## Security and operations

Use production secrets from the deployment secret store. Keep Discovery, AD, SNMP, topology, and analytics jobs disabled until approved ranges, credentials, maintenance windows, limits, and notification policy are reviewed. No real hotel network or directory access is assumed.

## Known limitations

Production backup/restore, rollback, container startup, pilot execution, production-scale performance, and browser matrix remain acceptance tasks. React Router advisories are documented in the security report. No final `v2.0.0` tag exists.

## Support

Use the acceptance report for evidence and blockers, the operations/admin guides for runbooks, and the pilot plan for controlled rollout and rollback conditions.
