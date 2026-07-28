# HIOP v2 Backup and Restore Report

## Status

**Not verified in this environment.** No production or hotel database was accessed, and no database dump is tracked in Git.

## Runbook

1. Set a temporary `PGPASSWORD` from the deployment secret store and run `pg_dump --format=custom --file=<protected-path> <database>`. Record checksum and size outside Git.
2. Validate with `pg_restore --list <protected-path>` and restore into a new isolated PostgreSQL database.
3. Run `alembic upgrade head` against the restored database and confirm `e7f8a9b0c1d2`.
4. Start the backend with the restored `DATABASE_URL`, verify `/health`, `/api/v1/auth/me` after login, and read-only checks for devices, AD, SNMP, topology, analytics, audit, and reports.
5. Keep the backup and test database access-controlled; remove temporary copies according to retention policy.

## Acceptance evidence required

Record operator, timestamp, database version, backup checksum, restore duration, migration head, health response, authentication result, key-record counts, and cleanup confirmation. Do not paste database content or credentials into this report.
