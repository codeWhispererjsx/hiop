# HIOP Administrator Guide

## Hotel IT Operations Portal — Version 1.0.0

---

## Table of Contents

1. [Deployment](#deployment)
2. [Initial Setup](#initial-setup)
3. [User Management](#user-management)
4. [Permissions and Roles](#permissions-and-roles)
5. [Network Scanner Configuration](#network-scanner-configuration)
6. [Active Directory Integration Foundation](#active-directory-integration-foundation)
7. [Backups](#backups)
8. [Monitoring](#monitoring)
9. [Troubleshooting](#troubleshooting)
10. [Maintenance](#maintenance)
11. [Recovery](#recovery)


---

## Deployment

### Prerequisites

- Docker Engine 24+ and Docker Compose v2+
- PostgreSQL 16+
- Python 3.12+
- Node.js 22+
- Nginx (production)

### Production Deployment (Docker)

```bash
# Clone the repository
git clone https://github.com/codeWhispererjsx/hiop.git
cd hiop

# Configure environment
cp backend/.env.example backend/.env
# Edit backend/.env with production values

# Start services
docker compose up -d
```

### Manual Deployment

**Backend:**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with production values
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

**Frontend:**
```bash
cd frontend
npm install
npm run build
# Serve the dist/ directory via Nginx
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `APP_NAME` | Yes | Application display name |
| `APP_VERSION` | Yes | Version string |
| `ENVIRONMENT` | Yes | `development`, `testing`, or `production` |
| `DEBUG` | Yes | `true` or `false` |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `SECRET_KEY` | Yes | JWT signing key (32+ chars in production) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | Token lifetime (default: 60) |
| `CORS_ORIGINS` | Yes | Allowed origins (JSON array) |
| `LOG_LEVEL` | No | Logging level (default: INFO) |
| `SCHEDULER_ENABLED` | No | Enable background scheduler (default: true) |

---

## Initial Setup

### First-Time Login

1. Deploy the application
2. Navigate to the login page
3. Use the initial admin credentials (created via seed script or database)
4. Change the default password immediately

### Configuration Checklist

- [ ] Set `ENVIRONMENT=production`
- [ ] Set `DEBUG=false`
- [ ] Generate a strong `SECRET_KEY` (32+ random characters)
- [ ] Configure `CORS_ORIGINS` with production HTTPS origins
- [ ] Set up PostgreSQL with proper credentials
- [ ] Configure email settings for notifications
- [ ] Set the approved network CIDR for scanning
- [ ] Enable HTTPS via Nginx or reverse proxy

---

## User Management

### Creating Users

1. Navigate to **Settings** → **Users**
2. Click **Add user**
3. Enter:
   - Username
   - Email address
   - Role (Administrator, Technician, Staff)
   - Initial password
4. Click **Create**

### Modifying Users

- **Edit**: Update username or email
- **Change role**: Promote or demote user role
- **Reset password**: Generate a new password
- **Deactivate**: Disable account without deleting

### Role Descriptions

| Role | Description |
|------|-------------|
| **Administrator** | Full system access including user management, settings, and all operations |
| **Technician** | Operational access for device management, scanning, tickets, and alerts |
| **Staff** | Read-only access to monitoring views |

### Security Policies

- Passwords are bcrypt-hashed
- JWT tokens expire after the configured interval
- Inactive users cannot authenticate
- Last administrator cannot be demoted or deactivated
- Self-deactivation is prevented

---

## Permissions and Roles

### Module Access by Role

| Module | Admin | Technician | Staff |
|--------|-------|------------|-------|
| Dashboard | ✓ | ✓ | ✓ |
| Devices | Full | View/Scan | View |
| Network | Full | Scan | View |
| Alerts | Full | View/Acknowledge | View |
| Tickets | Full | Full | View/Create |
| Reports | Full | View/Export | View |
| Users | Full | — | — |
| Audit | Full | View | View |
| Settings | Full | — | — |
| Hierarchy | Full | — | — |
| Discovery | Full | View | View |
| Imports | Full | View | View |

---

## Network Scanner Configuration

### Approved Network Range

The scanner is restricted to a configured private CIDR range:

1. Navigate to **Settings** → **Network**
2. Set **Approved network** (e.g., `10.0.0.0/8`)
3. Configure **Scan interval** (minutes)
4. Set **Ping timeout** (seconds)
5. Configure **Max concurrent workers**

### Automatic Alerts and Tickets

Enable automatic alerting and ticket creation when devices go offline:

1. Navigate to **Settings** → **Network**
2. Enable **Automatic alerts**
3. Enable **Automatic offline tickets**
4. Set **Offline threshold** (minutes before triggering)

### Discovery Settings

1. Navigate to **Settings** → **Discovery**
2. Enable Discovery
3. Set authorized CIDR ranges
4. Configure ignore ranges
5. Set scan interval and concurrency limits

---

## Active Directory Integration Foundation

HIOP `2.0.0-dev` includes a backend foundation for Microsoft Active Directory integration:
- Domain connections, search bases, and ports are managed via `/api/v1/active-directory/connections` (Admin only).
- Bind credentials are encrypted at rest using AES-256 / Fernet abstractions and treated as write-only.
- Staging models track directory users, computers, and groups (`active_directory_objects`).
- Live directory querying and background synchronization belong to Epic 3B.

---

## Backups


### Database Backup

The project includes backup and restore scripts:

```bash
# Backup
./scripts/backup-postgres.sh

# Restore
./scripts/restore-postgres.sh
```

### Manual Backup

```bash
pg_dump -U hiop -h localhost hiop > hiop-backup-$(date +%Y%m%d).sql
```

### Backup Best Practices

- Schedule daily database backups
- Store backups off-site or in secure cloud storage
- Test restore procedures regularly
- Keep at least 7 days of backup history
- Document backup locations and procedures

---

## Monitoring

### Health Check Endpoint

```
GET /api/v1/settings/system-health
```

Returns:
- API status
- Database connectivity
- Scheduler status
- WebSocket status
- Email configuration
- Last scan time
- Application version
- Environment

### Logging

- Logs are written to stdout/stderr (Docker)
- Configure `LOG_LEVEL` for verbosity
- Structured logging for machine parsing

### Key Metrics to Monitor

- Device online/offline ratio
- Scan success rate
- Alert frequency
- Ticket resolution time
- API response times
- Database connection pool usage

---

## Troubleshooting

### Application Won't Start

**Check:**
1. Database is running and accessible
2. Environment variables are correctly set
3. Database migrations are up to date
4. Required ports are available

**Solution:**
```bash
# Verify database connection
psql -U hiop -h localhost -d hiop -c "SELECT 1"

# Run migrations
alembic upgrade head

# Check logs
docker compose logs backend
```

### Users Cannot Log In

**Check:**
1. User account is active
2. Password is correct
3. JWT secret key hasn't changed
4. Token hasn't expired

**Solution:**
- Reset the user's password via admin panel
- Verify `SECRET_KEY` consistency across restarts

### Scanner Not Working

**Check:**
1. Approved network CIDR is configured
2. Target devices are reachable
3. ICMP is not blocked by firewall
4. Scheduler is enabled

**Solution:**
- Verify network range in Settings
- Test ping manually from the server
- Check firewall rules

### WebSocket Disconnections

**Check:**
1. Browser console for errors
2. Backend logs for WebSocket errors
3. Network connectivity
4. Proxy configuration (if behind Nginx)

**Solution:**
- Verify WebSocket path configuration
- Check Nginx WebSocket proxy settings
- Ensure no load balancer timeout is too low

---

## Maintenance

### Routine Tasks

| Frequency | Task |
|-----------|------|
| Daily | Review alerts and tickets |
| Weekly | Check system health endpoint |
| Monthly | Review audit logs |
| Monthly | Test backup restoration |
| Quarterly | Update dependencies |
| Annually | Review security policies |

### Database Maintenance

```bash
# Vacuum analyze
psql -U hiop -d hiop -c "VACUUM ANALYZE;"

# Reindex
psql -U hiop -d hiop -c "REINDEX DATABASE hiop;"
```

### Log Rotation

In Docker, logs are managed by the Docker logging driver. For manual deployments, configure log rotation in your process manager.

---

## Recovery

### Database Recovery

```bash
# Restore from backup
./scripts/restore-postgres.sh <backup-file.sql>

# Or manually
psql -U hiop -h localhost -d hiop < hiop-backup-20260101.sql
```

### Application Recovery

1. Stop the application
2. Restore the database from backup
3. Verify environment configuration
4. Start the application
5. Run health checks
6. Verify user access

### Disaster Recovery Plan

1. **Assess**: Determine the scope of the failure
2. **Isolate**: Prevent further damage
3. **Restore**: Restore from latest verified backup
4. **Verify**: Confirm data integrity and application functionality
5. **Communicate**: Notify affected users
6. **Document**: Record the incident and recovery steps

---

## Security Considerations

- All API traffic should use HTTPS in production
- JWT tokens are stored in sessionStorage (cleared on tab close)
- CORS is restricted to known origins
- Passwords are never returned in API responses
- Secrets are environment-only, never in the database
- Export files are sanitized to prevent formula injection
- File uploads are validated for type, size, and content
- The scanner is restricted to approved private networks only

---

## Support

For additional assistance, refer to:
- `DEVELOPER_GUIDE.md` — Development and contribution guide
- `DEPLOYMENT.md` — Detailed deployment instructions
- `OPERATIONS.md` — Operational runbook
- GitHub Issues: https://github.com/codeWhispererjsx/hiop/issues

## Inventory Import administration (2.0.0-dev)

Administrators can start and resolve imports from `/imports`. HIOP accepts only backend-validated CSV and XLSX content, stores generated server filenames, limits previews, never evaluates formulas or macros, and does not insert uploaded rows directly into inventory.

Review the mapping before validation, export validation findings when correction is needed, and use candidate evidence rather than score alone. Bulk acceptance is restricted to pending exact candidates without conflicts; every item is submitted independently so failures remain in the queue. Location overrides must reference active records already present in the HIOP hierarchy.

Do not treat hidden controls as authorization. Upload, mapping, validation, matching, cancellation, and resolution endpoints enforce the administrator role on the server. Read endpoints permit the established administrator/technician reader roles.

Epic 2D stops at readiness preparation. There is no supported final bulk-create, merge execution, automatic conflict dismissal, rollback, scheduled import, Active Directory, or SNMP workflow. Those remain pending Epic 2E.

### Epic 2E execution policy

Generate and review the server plan immediately before finalization. Plans are versioned and lock on execution. Create rows must satisfy the normal Device schema and uniqueness constraints. Links never overwrite inventory. Enrichment and merge apply only recorded approved fields; existing values remain unless reviewed overwrites are enabled and explicitly listed.

Retry only safely retryable failures. Identifier and stale-target conflicts require renewed review. Always request a rollback preview immediately before rollback. HIOP refuses compensation after later inventory changes, retires import-created devices rather than silently deleting them, and retains audit/import history.
