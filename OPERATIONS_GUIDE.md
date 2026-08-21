# HIOP Operations Guide

## Overview

This guide provides operational procedures for running HIOP in production, including backup, restore, disaster recovery, and day-to-day maintenance.

**Target Audience:** Platform administrators and operators responsible for HIOP availability and data integrity.

---

## Quick Reference

| Component | Health Check | Recovery |
|-----------|--------------|----------|
| PostgreSQL | `/health` endpoint | Restore from backup |
| Backend API | `/health` endpoint | Restart service |
| Scheduler | System Health → Scheduler | Restart backend |
| Agents | System Health → Agents | Restart agent service |
| Backups | System Health → Backup | Use Disaster Recovery Runbook |

---

## Startup and Shutdown

### Starting HIOP

1. **Start PostgreSQL**
   ```bash
   # Windows service
   Start-Service -Name "postgresql-x64-18"
   
   # Or Linux
   sudo systemctl start postgresql
   ```

2. **Start Backend**
   ```bash
   cd c:/hiop/backend
   .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
   ```

3. **Start Frontend**
   ```bash
   cd c:/hiop/frontend
   npm run build
   npm run preview
   ```

4. **Verify Health**
   ```bash
   curl http://localhost:8001/health
   ```

### Stopping HIOP

1. **Stop Backend** (wait for in-flight requests)
2. **Stop Frontend**
3. **Stop PostgreSQL** (only if necessary)

**Always stop services gracefully before maintenance.**

---

## Health Monitoring

### System Health

Access health status via:
- **Platform Control Center → System Health**
- **API:** `/system-health/platform` (platform admins)
- **API:** `/system-health/organizations/{org_id}` (org admins)

### Health States

- **HEALTHY:** Component functioning normally
- **DEGRADED:** Partially working or repeated failures
- **STALE:** No recent success within expected window
- **FAILED:** Known active failure
- **NOT_CONFIGURED:** Required component not configured
- **UNKNOWN:** Insufficient evidence

### Critical Components

| Component | Freshness Window | Action if STALE/FAILED |
|-----------|------------------|------------------------|
| API | N/A | Restart backend |
| Database | N/A | Check PostgreSQL, restart if needed |
| Scheduler | 120 seconds | Restart backend, check jobs |
| Discovery | 1 hour | Check discovery configuration |
| Monitoring | 5 minutes | Check monitoring configuration |
| Agents | 10 minutes | Check agent connectivity |
| Backup | 48 hours | Review backup failures, run manual backup |

---

## Backup Operations

### Automated Backup (Daily)

The backup script runs automatically via cron/scheduled job:

```bash
./scripts/backup-postgres.sh
```

**Required environment variables:**
- `PGHOST` - PostgreSQL host
- `PGDATABASE` - Database name
- `PGUSER` - PostgreSQL user
- `PGPASSWORD` - Database password (inject securely)
- `BACKUP_DIR` - Backup storage location
- `RETENTION_DAYS` - Backup retention (default: 14 days)

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

### Backup Verification

Verify a backup file is valid:

```bash
# Check file exists
ls -lh /path/to/backup.dump

# Verify checksum
sha256sum -c /path/to/backup.dump.sha256

# Verify backup can be read
pg_restore --list /path/to/backup.dump
```

### Backup Health Monitoring

Monitor backup status via:
- **Platform Control Center → Backup & Recovery**
- **API:** `/backup-recovery/health`

**Backup States:**
- **HEALTHY:** Recent successful backup, verified checksum
- **DEGRADED:** Backup too old (>48 hours)
- **FAILED:** Last backup failed
- **UNKNOWN:** No backup record found

### Backup Retention

**Current policy:**
- Daily backups: 14 days
- Automatic cleanup: Backups older than `RETENTION_DAYS` are deleted

**Best practices:**
- Configure off-host backup storage
- Periodically verify restore procedures
- Document retention policy for compliance

---

## Restore Operations

**IMPORTANT:** Always review the [Disaster Recovery Runbook](DISASTER_RECOVERY_RUNBOOK.md) before performing any restore operation.

### Pre-Restore Checklist

- [ ] Identify target backup file
- [ ] Verify backup checksum
- [ ] Verify backup age is acceptable
- [ ] Confirm PostgreSQL superuser access
- [ ] Confirm database version compatibility
- [ ] Have application secrets ready for re-injection
- [ ] Inform stakeholders of scheduled downtime
- [ ] Prepare isolated test environment for test restores

### Restore to Test Database (Isolated)

```bash
# Set environment
export PGHOST="test-postgres-host"
export PGUSER="postgres"
export PGPASSWORD="test-password"

# Create new database
createdb hiop_restore_test

# Restore backup
pg_restore --format=custom --dbname=hiop_restore_test --no-owner --no-acl /path/to/backup.dump

# Run migrations
cd /path/to/backend
.venv/bin/python -m alembic upgrade head

# Verify migration head
.venv/bin/python -m alembic current

# Start backend with test DATABASE_URL
# Validate: /health, /api/v1/auth/me, critical data counts

# Cleanup
dropdb hiop_restore_test
```

### Production Restore (Disaster Recovery)

**STOP:** This is a destructive operation. Perform only when absolutely necessary.

See [Disaster Recovery Runbook](DISASTER_RECOVERY_RUNBOOK.md) for detailed production restore procedures.

---

## Scheduled Jobs

The HIOP scheduler runs various recurring jobs:

### Job Categories

- **Discovery:** Network device discovery
- **Monitoring:** Device polling and health checks
- **Alert Processing:** Event processing and alert generation
- **Notifications:** Email and notification delivery
- **Analytics:** Data aggregation and reporting
- **Automation:** Workflow execution
- **Incidents:** SLA evaluation and escalation
- **Topology:** Network topology collection and inference
- **Active Directory:** AD sync and enrichment
- **SNMP:** Device polling via SNMP

### Job Health Monitoring

Monitor job health via:
- **System Health → Scheduler**
- **API:** `/system-health/platform` (includes job execution history)

**Job States:**
- **RUNNING:** Job currently executing
- **SUCCESS:** Job completed successfully
- **FAILED:** Job failed with error
- **STALE:** Job has not run within expected window
- **WAITING:** Job waiting for scheduled time
- **DISABLED:** Job disabled by configuration

### Job Failure Response

If a job fails:

1. Check System Health for job details
2. Review job error message
3. Check logs for stack traces
4. Verify required configuration (e.g., SNMP credentials)
5. Restart scheduler if needed (restart backend)
6. Verify job resumes on next scheduled interval

---

## Agent Operations

### Agent Status

Monitor agent health via:
- **Platform Control Center → Local Agents**
- **System Health → Agents**

**Agent States:**
- **ONLINE:** Heartbeat current (≤10 minutes)
- **STALE:** Heartbeat stale (10-60 minutes)
- **OFFLINE:** No heartbeat (>60 minutes)
- **REVOKED:** Agent revoked by platform admin
- **RETIRE:**** Agent retired

### Agent Troubleshooting

**Agent not connecting:**
1. Check agent service status on hotel network
2. Check network connectivity between agent and HIOP
3. Verify agent credentials
4. Check HIOP backend logs for authentication errors

**Agent queue backing up:**
1. Check network bandwidth
2. Reduce observation frequency
3. Check agent disk space
4. Restart agent service

---

## Database Maintenance

### Connection Pool

HIOP uses SQLAlchemy connection pooling. Monitor for connection exhaustion:

**Symptoms:**
- `FATAL: remaining connection slots are reserved for roles with the SUPERUSER attribute`
- Application connection timeouts

**Resolution:**
1. Check PostgreSQL `max_connections` setting
2. Review connection pool configuration in backend
3. Identify long-running queries
4. Restart PostgreSQL if necessary

### Migration Management

**Before applying migrations:**
1. Always create a backup
2. Verify backup and checksum
3. Review migration code in isolated environment
4. Document expected changes

**Applying migrations:**
```bash
cd backend
.venv/bin/python -m alembic upgrade head
```

**Migration failure:**
1. STOP: Do not attempt manual database repairs
2. Restore from pre-migration backup
3. Review migration code for issues
4. Fix migration issues
5. Retry migration

---

## Security Operations

### Secret Management

**Never:**
- Store secrets in source code
- Commit secrets to version control
- Share secrets via email or chat
- Place encryption keys beside backup files

**Always:**
- Use organization's secret-management system
- Rotate secrets periodically
- Document secret recovery procedures
- Use secure secret injection at deployment

### Audit Logs

Review audit logs regularly:
- **Platform Control Center → Audit**
- Check for unusual administrative actions
- Monitor for unauthorized access attempts
- Review failed authentication attempts

---

## Upgrade Procedures

### Pre-Upgrade Checklist

- [ ] Create full backup
- [ ] Verify backup and checksum
- [ ] Document current version
- [ ] Review upgrade notes
- [ ] Schedule maintenance window
- [ ] Inform stakeholders
- [ ] Prepare rollback plan

### Upgrade Steps

1. **Backup**
   ```bash
   ./scripts/backup-postgres.sh
   sha256sum -c backups/hiop-*.dump.sha256
   ```

2. **Stop Services**
   - Stop backend
   - Stop frontend

3. **Update Code**
   ```bash
   git pull origin main
   ```

4. **Install Dependencies**
   ```bash
   cd backend
   .venv/bin/pip install -r requirements.txt
   
   cd ../frontend
   npm install
   ```

5. **Run Migrations**
   ```bash
   cd backend
   .venv/bin/python -m alembic upgrade head
   ```

6. **Build Frontend**
   ```bash
   cd frontend
   npm run build
   ```

7. **Start Services**
   - Start backend
   - Start frontend

8. **Validate**
   - Check `/health` endpoint
   - Log in as platform admin
   - Verify critical workflows
   - Check System Health

### Rollback

If upgrade fails:

1. Stop services
2. Restore from pre-upgrade backup
3. Verify backup
4. Start services
5. Validate health

---

## Disaster Scenarios

See [Disaster Recovery Runbook](DISASTER_RECOVERY_RUNBOOK.md) for detailed procedures.

### Quick Reference

| Scenario | Detection | Immediate Action |
|----------|-----------|------------------|
| Database failure | Health: Database FAILED | Check PostgreSQL, restart or restore |
| Backend failure | Health: API FAILED | Restart backend |
| Scheduler failure | Health: Scheduler FAILED/STALE | Restart backend |
| Agent disconnection | Health: Agents STALE | Check agent service |
| Backup failure | Health: Backup FAILED | Review backup logs, run manual backup |
| Migration failure | Migration command fails | Restore from backup, fix migration |

---

## Monitoring and Alerts

### Key Metrics

- Component health status
- Backup age and verification status
- Job execution success rate
- Agent connectivity
- Database connection pool utilization
- Application error rates

### Alert Configuration

Configure alerts for:
- Component FAILED state
- Backup DEGRADED/FAILED state
- Job failure rate > threshold
- Agent STALE/FAILED state
- Database connection exhaustion

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

This guide must be updated when:
- Backup procedures change
- New components are added
- Recovery procedures are tested and improved
- New failure scenarios are identified
- Architecture changes affect operations

---

## Contact Information

**Platform Operations:** [Contact details]
**Database Administration:** [Contact details]
**Emergency Response:** [Contact details]

---

**Document Version:** 2.0
**Last Updated:** 2025-01-19
**HIOP Version:** 1.0.0
