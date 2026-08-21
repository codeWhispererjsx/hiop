# HIOP Disaster Recovery Runbook

## Overview

This runbook provides the operational procedures for recovering HIOP from various failure scenarios. It is designed for platform administrators and operators responsible for HIOP availability and data integrity.

**IMPORTANT:** Never perform destructive tests against production infrastructure. Use isolated test environments for all failure simulation and restore drills.

---

## Backup Strategy

### Backup Type
- **Format:** PostgreSQL custom format (`pg_dump --format=custom`)
- **Compression:** Default PostgreSQL compression
- **Frequency:** Daily (configurable via `BACKUP_DIR` and cron/scheduled job)
- **Retention:** 14 days (configurable via `RETENTION_DAYS`)
- **Encryption:** Transport-level (SSL/TLS) for backup transfer; storage encryption per deployment policy

### Backup Location
- **Primary:** Configured via `BACKUP_DIR` environment variable
- **Off-host:** Must be configured to a separate server or secured storage location
- **File naming:** `hiop-YYYYMMDDTHHMMSSZ.dump` with `.sha256` checksum file

### Backup Contents
All PostgreSQL database contents including:
- Organizations and properties
- Users and roles
- Assets and devices
- Discovery history
- Monitoring history
- Alerts and incidents
- Problems and changes
- Procurement and vendors
- Knowledge articles
- Audit logs
- Agent records
- All configuration data stored in database

**NOT included:**
- Application secrets (environment variables, encryption keys)
- File attachments (if stored outside database)
- Agent configuration files on hotel networks

---

## Backup Procedures

### Automated Backup (Daily)

The backup script is located at `scripts/backup-postgres.sh`.

**Prerequisites:**
```bash
export PGHOST="your-postgres-host"
export PGDATABASE="hiop"
export PGUSER="postgres"
export PGPASSWORD="your-password"  # Use secure secret injection
export BACKUP_DIR="/secure/backup/location"
export RETENTION_DAYS="14"
```

**Execution:**
```bash
./scripts/backup-postgres.sh
```

**Expected output:**
```
Backup completed: /secure/backup/location/hiop-20260819T020000Z.dump
```

**Verification:**
```bash
# Check file exists
ls -lh /secure/backup/location/hiop-*.dump

# Verify checksum
sha256sum -c /secure/backup/location/hiop-*.dump.sha256

# Verify backup can be read
pg_restore --list /secure/backup/location/hiop-*.dump
```

### Manual Backup

For pre-upgrade or special-case backups:

```bash
# Set environment variables
export PGHOST="your-postgres-host"
export PGDATABASE="hiop"
export PGUSER="postgres"
export PGPASSWORD="your-password"  # Use secure secret injection

# Create backup
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
pg_dump --format=custom --no-owner --no-acl --file="hiop-manual-${TIMESTAMP}.dump" hiop

# Generate checksum
sha256sum "hiop-manual-${TIMESTAMP}.dump" > "hiop-manual-${TIMESTAMP}.dump.sha256"

# Verify
pg_restore --list "hiop-manual-${TIMESTAMP}.dump"
```

---

## Backup Health Monitoring

### Check Backup Status

Backup status is tracked in the `backup_records` table and exposed via System Health.

**Health states:**
- **HEALTHY:** Recent successful backup, verified checksum
- **DEGRADED:** Backup too old according to retention policy
- **FAILED:** Last backup failed
- **UNKNOWN:** No backup record found

**In Platform Control Center:**
1. Navigate to System Health
2. Check Backup status
3. Review last successful backup timestamp
4. Review backup age

### Backup Failure Response

If backup fails:

1. **Immediate:** Check backup logs for error details
2. **Diagnosis:**
   - PostgreSQL connectivity: `psql -h $PGHOST -U $PGUSER -d $PGDATABASE -c "SELECT 1"`
   - Disk space: `df -h $BACKUP_DIR`
   - Permissions: Verify write access to `BACKUP_DIR`
3. **Recovery:**
   - Fix underlying issue (connectivity, disk, permissions)
   - Run manual backup
   - Verify backup and checksum
4. **Prevention:**
   - Monitor disk space alerts
   - Schedule automatic backup monitoring
   - Configure off-host backup storage

---

## Restore Procedures

### Pre-Restore Checklist

Before any restore operation:

- [ ] Identify the target backup file
- [ ] Verify backup checksum
- [ ] Verify backup age is acceptable
- [ ] Confirm you have PostgreSQL superuser access
- [ ] Confirm database version compatibility
- [ ] Have application secrets ready for re-injection
- [ ] Inform stakeholders of scheduled downtime
- [ ] Prepare isolated test environment for test restores

### Restore to New Database (Isolated Test)

**Purpose:** Verify backup integrity without affecting production

```bash
# Set environment
export PGHOST="test-postgres-host"
export PGUSER="postgres"
export PGPASSWORD="test-password"

# Create new database
createdb hiop_restore_test

# Restore backup
pg_restore --format=custom --dbname=hiop_restore_test --no-owner --no-acl /path/to/hiop-*.dump

# Run migrations
cd /path/to/backend
.venv/bin/python -m alembic upgrade head

# Verify migration head
.venv/bin/python -m alembic current

# Start backend with DATABASE_URL pointing to test database
# Validate: /health, /api/v1/auth/me, critical data counts

# Cleanup
dropdb hiop_restore_test
```

### Production Restore (Disaster Recovery)

**IMPORTANT:** This is a destructive operation. Perform only when absolutely necessary.

```bash
# STOP: Confirm this is necessary
# STOP: Have you tried other recovery options?
# STOP: Is backup verified?

# 1. Stop HIOP services
# Stop backend containers/processes
# Stop frontend containers/processes

# 2. Backup current database (if possible)
export TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
pg_dump --format=custom --file="hiop-emergency-${TIMESTAMP}.dump" hiop

# 3. Drop existing database
dropdb hiop

# 4. Create new database
createdb hiop

# 5. Restore from backup
pg_restore --format=custom --dbname=hiop --no-owner --no-acl /path/to/verified-backup.dump

# 6. Run migrations
cd /path/to/backend
.venv/bin/python -m alembic upgrade head

# 7. Verify migration head
.venv/bin/python -m alembic current

# 8. Re-inject application secrets
# Use your organization's secure secret-management process

# 9. Start HIOP services
# Start backend
# Start frontend

# 10. Validate health
curl http://localhost:8001/health

# 11. Validate critical data
# Log in as platform admin
# Verify organizations
# Verify properties
# Verify users
# Verify assets/devices
# Verify audit logs

# 12. Verify agent connectivity
# Check agent heartbeats in Platform Control Center
```

---

## Data Integrity Verification

After any restore, verify:

### Critical Counts
```sql
-- Organizations
SELECT COUNT(*) FROM organizations;

-- Properties
SELECT COUNT(*) FROM properties;

-- Users
SELECT COUNT(*) FROM users;

-- Assets
SELECT COUNT(*) FROM managed_assets;

-- Devices
SELECT COUNT(*) FROM devices;

-- Incidents
SELECT COUNT(*) FROM operational_incidents;

-- Audit logs
SELECT COUNT(*) FROM audit_logs;
```

### Foreign Key Integrity
```sql
-- Check for broken references
SET client_min_messages TO WARNING;
SELECT 'Checking foreign key integrity...';
-- Postgres will report any FK violations
```

### Organization/Property Relationships
```sql
-- Verify property organization references
SELECT COUNT(*) FROM properties WHERE organization_id IS NULL;

-- Verify no orphaned devices
SELECT COUNT(*) FROM devices WHERE property_id IS NULL;
```

---

## Disaster Scenarios

### 1. Database Failure

**Detection:**
- Health check reports database: FAILED
- Application errors: "Database connection failed"
- Backend logs: connection errors

**Immediate Action:**
1. Check PostgreSQL service status
2. Check database disk space
3. Check network connectivity to database
4. Review PostgreSQL logs

**Recovery:**
- If PostgreSQL service failed: Restart PostgreSQL service
- If disk full: Clear space or expand storage
- If data corruption: Restore from last verified backup

**Validation:**
- Database health: HEALTHY
- Application health: HEALTHY
- Critical data counts match expectations

### 2. Backend Failure

**Detection:**
- Health check reports API: FAILED
- Frontend shows connection errors
- Backend logs: application errors

**Immediate Action:**
1. Check backend service status
2. Check backend logs for errors
3. Verify database connectivity
4. Check environment variables/secrets

**Recovery:**
- Restart backend service
- If persistent errors: Check configuration
- If configuration error: Restore from known-good config

**Validation:**
- Backend health: HEALTHY
- Health endpoint responds
- Login works

### 3. Scheduler Failure

**Detection:**
- System Health reports scheduler: FAILED or STALE
- No recent job executions
- Scheduled tasks not running

**Immediate Action:**
1. Check scheduler service status
2. Review scheduler logs
3. Verify database connectivity

**Recovery:**
- Restart backend service (includes scheduler)
- Jobs will resume on next scheduled interval
- Stale jobs will execute when scheduler recovers

**Validation:**
- Scheduler health: HEALTHY
- Recent job executions visible
- Jobs executing on schedule

### 4. Agent Disconnection

**Detection:**
- Agent health: STALE or FAILED
- No recent heartbeat
- Discovery/monitoring: STALE

**Immediate Action:**
1. Check agent service status on hotel network
2. Check network connectivity between agent and HIOP
3. Verify agent credentials

**Recovery:**
- Restart agent service
- Agent will reconnect automatically
- Queued observations will upload
- Duplicate observations will be rejected (idempotent)

**Validation:**
- Agent health: HEALTHY
- Heartbeat current
- Queue draining

### 5. Failed Migration

**Detection:**
- Migration command fails
- Database schema in inconsistent state
- Application fails to start

**Immediate Action:**
1. STOP: Do not attempt manual database repairs
2. Identify the migration that failed
3. Verify you have a pre-migration backup

**Recovery:**
1. Restore from pre-migration backup
2. Verify migration head: `alembic current`
3. Review migration code for issues
4. Fix migration issues
5. Retry migration

**Validation:**
- Application starts successfully
- Health endpoint responds
- Critical workflows work

### 6. Accidental Data Deletion

**Detection:**
- User reports missing data
- Audit logs show deletion action
- Counts don't match expectations

**Immediate Action:**
1. Identify when deletion occurred
2. Identify most recent backup before deletion
3. Assess impact scope

**Recovery:**
1. Perform isolated restore to test database
2. Extract missing data from restored backup
3. Carefully restore only affected data to production
4. Verify integrity

**Validation:**
- Missing data restored
- No unintended data changes
- Audit trail updated

---

## Recovery Point Objective (RPO)

**Current RPO: 24 hours**

Based on daily backup schedule. Any data created after the last successful backup will be lost in a disaster scenario.

**Future improvements:**
- More frequent backups (e.g., every 6 hours)
- Point-in-time recovery (WAL archiving)
- Transaction log shipping

---

## Recovery Time Objective (RTO)

**Estimated recovery time breakdown:**

- Restore database: 15-30 minutes (depending on database size)
- Run migrations: 2-5 minutes
- Start services: 2-5 minutes
- Validate health: 5-10 minutes
- Validate critical data: 10-20 minutes

**Total estimated RTO: 34-70 minutes**

**Actual RTO depends on:**
- Database size
- Backup storage speed
- Operator familiarity with procedures
- Available resources

---

## Secret Recovery

### Application Secrets

HIOP uses environment variables for sensitive configuration:
- Database passwords
- Encryption keys
- API keys
- SMTP credentials

**Secret recovery process:**
1. Use organization's secure secret-management system
2. Re-inject secrets via approved process
3. Do NOT store secrets in application backups
4. Do NOT place secrets in source code

**If encryption key is lost:**
- Encrypted data cannot be recovered
- This is an operational requirement
- Document key backup procedures in your organization

---

## File/Attachment Recovery

**Current status:** HIOP primarily stores data in PostgreSQL database. File attachments are not currently implemented in production.

**If file storage is added in future:**
- Document storage location
- Include in backup strategy
- Verify file permissions after restore
- Verify database-file references

---

## Organization/Property Integrity

**After any restore, verify:**

```sql
-- Organization isolation
SELECT organization_id, COUNT(*) FROM properties GROUP BY organization_id;

-- Property isolation
SELECT property_id, COUNT(*) FROM devices GROUP BY property_id;

-- No cross-organization data leaks
-- Verify audit logs show correct organization context
```

**P1/P2 isolation must remain intact after restore.**

---

## Off-Host Backup Strategy

**Recommended:**
- Store backups on separate server
- Use secured storage (encrypted at rest)
- Configure backup retention on off-host storage
- Document off-host backup process

**Options:**
- Separate physical server
- Network-attached storage (NAS)
- Cloud storage (if organization policy permits)
- Tape backup (for long-term archival)

**Do NOT rely solely on same-host backups.**

---

## Backup Encryption

**At rest:** Use encryption provided by storage solution
**In transit:** Use SSL/TLS for backup transfer
**Key management:** Follow organization's key management policies

**Do NOT store encryption keys beside backup files.**

---

## Backup Retention

**Current policy:**
- Daily backups: 14 days
- Weekly backups: Not currently configured
- Monthly backups: Not currently configured

**Future improvements:**
- Longer retention for compliance requirements
- Weekly/monthly archives
- Tiered storage (hot/warm/cold)

---

## Platform Control Center Integration

**System Health → Backup Status:**

Exposes:
- Backup status (HEALTHY/DEGRADED/FAILED/UNKNOWN)
- Last successful backup timestamp
- Backup age
- Verification status

**System Health → Restore Drill Status:**

Exposes:
- Last restore test date
- Restore test result
- Data integrity checks
- Operator who performed test

---

## Testing Requirements

### Backup Tests
- Successful backup status tracking
- Failed backup detection
- Stale backup detection (based on age)
- Checksum verification

### Restore Tests
- Restore to isolated database
- Data integrity verification
- Organization/property isolation verification
- Application startup verification

### Database Failure Tests
- Database unavailable simulation
- Health check detection
- Application behavior
- Recovery validation

### Scheduler Failure Tests
- Scheduler stop/start
- Stale job detection
- Job recovery validation

### Agent Failure Tests
- Agent disconnect simulation
- Reconnection handling
- Queue behavior

### Migration Recovery Tests
- Backup-before-upgrade verification
- Migration failure simulation
- Restore procedure validation

---

## Escalation Path

**Level 1:** Platform Operator
- Monitor health
- Perform routine backups
- Handle minor issues

**Level 2:** Platform Administrator
- Handle moderate failures
- Perform restore procedures
- Coordinate with stakeholders

**Level 3:** Systems/Database Administrator
- Handle database-level issues
- Manage PostgreSQL configuration
- Handle storage issues

**Level 4:** Emergency Response
- Critical failures
- Data loss incidents
- Security incidents

---

## Documentation Maintenance

This runbook must be updated when:
- Backup procedures change
- New data sources are added
- Recovery procedures are tested and improved
- New failure scenarios are identified
- Architecture changes affect recovery

---

## Contact Information

**Platform Operations:** [Contact details]
**Database Administration:** [Contact details]
**Emergency Response:** [Contact details]

---

**Document Version:** 1.0
**Last Updated:** 2025-01-19
**HIOP Version:** 1.0.0
