# HIOP v2 Pilot Plan

1. Deploy to an isolated test environment with synthetic analytics data and a tested database backup.
2. Create named admin, technician, and viewer test accounts; verify 401/403 and read-only behavior.
3. Start with approved private ranges and a small SNMP target list. Run Discovery, AD, topology, and analytics in dry-run/read-only modes.
4. Warm analytics history before enabling reviewed baseline rules. Inspect confidence, evidence, recovery, correlation, and export safety.
5. Measure API latency, scheduler health, data freshness, false-positive review rate, and backup/restore success.
6. Report issues through the normal ticket/audit workflow. Roll back on credential exposure, unauthorized mutation, migration failure, uncontrolled event volume, or unacceptable data loss.
7. Expand only after administrator sign-off, successful restore drill, and documented acceptance metrics.

No hotel-network connection or real directory/device synchronization is assumed by this plan.
