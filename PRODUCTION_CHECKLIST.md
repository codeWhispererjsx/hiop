# HIOP Production Checklist

## Version 1.0.0

---

## Pre-Deployment

### Database
- [ ] PostgreSQL 16+ is installed and running
- [ ] Database `hiop` exists
- [ ] Database user `hiop` has proper permissions
- [ ] Database migrations are up to date (`alembic upgrade head`)
- [ ] Connection pool settings are configured for expected load
- [ ] Database backup strategy is in place

### Backups
- [ ] Database backup script is tested (`./scripts/backup-postgres.sh`)
- [ ] Restore procedure is documented and tested
- [ ] Backup storage location is configured (off-site/cloud)
- [ ] Backup schedule is established (daily recommended)
- [ ] Retention policy is defined (minimum 7 days)

### HTTPS
- [ ] SSL/TLS certificate is obtained
- [ ] Nginx is configured for HTTPS
- [ ] HTTP to HTTPS redirect is enabled
- [ ] Strong TLS protocols are configured (TLS 1.2+)
- [ ] Certificate auto-renewal is configured (Let's Encrypt)
- [ ] HSTS headers are configured

### Environment Variables
- [ ] `ENVIRONMENT=production`
- [ ] `DEBUG=false`
- [ ] `SECRET_KEY` is 32+ random characters (not a placeholder)
- [ ] `DATABASE_URL` uses production credentials (not a placeholder)
- [ ] `CORS_ORIGINS` contains only production HTTPS origins
- [ ] `ACCESS_TOKEN_EXPIRE_MINUTES` is set appropriately (60-1440)
- [ ] `LOG_LEVEL` is set to `INFO` or `WARNING`
- [ ] `SCHEDULER_ENABLED` is configured as needed
- [ ] Email settings are configured (if notifications are needed)
- [ ] Frontend `.env.production` has correct `VITE_API_URL`

### Logging
- [ ] Log level is configured for production (`INFO` minimum)
- [ ] Log rotation is configured
- [ ] Log storage location has sufficient space
- [ ] Error aggregation is configured (optional)

### Monitoring
- [ ] Health check endpoint is accessible (`/api/v1/settings/system-health`)
- [ ] Uptime monitoring is configured
- [ ] Alert notifications for service degradation
- [ ] Resource monitoring (CPU, memory, disk, network)

---

## Deployment

### Application Build
- [ ] Frontend builds without errors (`npm run build`)
- [ ] Backend starts without errors
- [ ] Docker images build successfully (if using Docker)
- [ ] All static assets are compiled
- [ ] Source maps are disabled in production (optional)

### Services
- [ ] PostgreSQL is running and accepting connections
- [ ] Backend API is running and responding
- [ ] Frontend is served correctly
- [ ] Nginx reverse proxy is configured
- [ ] WebSocket connections work correctly
- [ ] Scheduler is running (if enabled)

### Verification
- [ ] Application loads in browser
- [ ] Login works with test credentials
- [ ] Dashboard displays data
- [ ] API endpoints return correct responses
- [ ] WebSocket connection is established
- [ ] No console errors in browser
- [ ] All navigation links work
- [ ] Responsive layout renders correctly

---

## Security

### Authentication
- [ ] Default admin password has been changed
- [ ] JWT token expiry is configured
- [ ] Password policy is documented
- [ ] Failed login attempts are logged
- [ ] Account lockout is configured (if needed)

### Network
- [ ] Approved network CIDR is configured for scanning
- [ ] Firewall rules restrict unnecessary ports
- [ ] Only required ports are exposed (80/443)
- [ ] Database port is not exposed publicly
- [ ] SSH access is restricted

### Configuration
- [ ] Debug mode is disabled
- [ ] CORS origins are restricted to production domains
- [ ] Secret key is not a placeholder
- [ ] Database URL uses strong password
- [ ] Email credentials are not exposed in logs

### Data Protection
- [ ] Export files are sanitized (formula injection protection)
- [ ] File upload limits are configured
- [ ] Upload content validation is enabled
- [ ] Error messages do not leak sensitive information

---

## Health Checks

### API Health
```
GET /api/v1/settings/system-health
```
Expected response (200 OK):
```json
{
  "status": "healthy",
  "api": "ok",
  "database": "connected",
  "scheduler": "running",
  "websocket": "ready",
  "email": "configured",
  "application_version": "1.0.0",
  "environment": "production"
}
```

### Database Health
```bash
psql -U hiop -h localhost -d hiop -c "SELECT 1;"
# Expected: 1 row returned
```

### WebSocket Health
- Open browser developer tools
- Navigate to Dashboard
- Verify WebSocket connection establishes (Network tab → WS)
- Verify connection status shows "connected"

### Frontend Health
- Open application in browser
- Open developer console
- Verify no JavaScript errors
- Verify all assets load (no 404s)
- Verify all routes render

---

## Rollback Plan

### Prerequisites
- [ ] Previous working version is tagged in git
- [ ] Database backup is available
- [ ] Deployment scripts are versioned
- [ ] Rollback procedure is documented

### Rollback Steps

1. **Stop the application**
   ```bash
   docker compose down
   ```

2. **Restore the database**
   ```bash
   ./scripts/restore-postgres.sh <previous-backup.sql>
   ```

3. **Revert to previous version**
   ```bash
   git checkout <previous-release-tag>
   ```

4. **Rebuild and deploy**
   ```bash
   docker compose build
   docker compose up -d
   ```

5. **Verify rollback**
   - Application loads
   - Login works
   - Data integrity is confirmed
   - All modules function correctly

### Rollback Triggers
- Critical production bug
- Data integrity issue
- Security vulnerability
- Performance degradation affecting users
- Incomplete or failed migration

---

## Post-Deployment

### Immediate (First 24 Hours)
- [ ] Monitor error logs
- [ ] Verify all scheduled tasks run
- [ ] Test user workflows
- [ ] Confirm email notifications work
- [ ] Check WebSocket stability

### Short-Term (First Week)
- [ ] Review system performance
- [ ] Verify backup jobs complete
- [ ] Collect user feedback
- [ ] Address any usability issues
- [ ] Monitor resource utilization

### Long-Term (Ongoing)
- [ ] Regularly review audit logs
- [ ] Schedule dependency updates
- [ ] Perform periodic security reviews
- [ ] Test backup restoration quarterly
- [ ] Update documentation as needed

---

## Emergency Contacts

| Role | Contact |
|------|---------|
| System Administrator | [Name/Email/Phone] |
| Database Administrator | [Name/Email/Phone] |
| Security Officer | [Name/Email/Phone] |
| Development Lead | [Name/Email/Phone] |

---

## Sign-Off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Release Manager | | | |
| QA Lead | | | |
| System Administrator | | | |
| Security Officer | | | |