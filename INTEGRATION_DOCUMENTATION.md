# HIOP INTEGRATION DOCUMENTATION

## Overview

HIOP integrates with various external systems for discovery, monitoring, and notification purposes. This document provides production configuration and troubleshooting guidance for each integration.

## Supported Deployment Model

**Scheduler: Single Instance**
- One scheduler instance per deployment
- One scheduler-owning process
- Horizontal scheduler scaling is NOT supported
- Multiple API replicas are NOT supported

**Important:** Do not attempt to run multiple scheduler instances or horizontally scale the scheduler. This will cause duplicate job execution and race conditions.

## DNS Integration

### Configuration
- **Method:** System DNS resolution via socket.gethostbyaddr/getaddrinfo
- **Scope:** Per-discovery, per-device
- **Timeout:** 1.0 second (configurable)
- **Retry:** None (single attempt)
- **Failure Handling:** Graceful degradation

### Behavior
- **Success:** PTR record found and forward-confirmed
- **Timeout:** DNS resolution timed out - marks as "timeout"
- **Failure:** DNS unavailable - marks as "unavailable"
- **Error:** DNS resolution error - marks as "error"

### Production Notes
- DNS failures do NOT mark devices as broken
- DNS enrichment is additive - other discovery sources remain valid
- Do not block core discovery because DNS fails
- Timeout prevents indefinite hanging on DNS issues

### Troubleshooting
- Check DNS server connectivity
- Verify firewall allows DNS queries
- Check DNS server response times
- Review DNS server logs for resolution failures

## DHCP Integration

### Configuration
- **Method:** Database correlation of imported DHCP leases
- **Scope:** Per-organization, per-property
- **Source:** Administrator-approved DHCP import
- **Credential Storage:** None (import-based)
- **Connection Test:** Not applicable (import-based)

### Behavior
- **Available:** Correlates with imported leases
- **Unavailable:** No correlation data available
- **Stale Data:** Uses most recent import with timestamp

### Production Notes
- DHCP correlation is NOT active polling
- Requires manual/administrator-approved lease imports
- Does NOT fabricate leases
- Does NOT treat old leases as current without evidence
- Lease timestamps indicate validity period

### Troubleshooting
- Verify DHCP lease imports are up-to-date
- Check lease timestamp validity
- Ensure imports are organization/property scoped
- Review import process for stale data

## SNMP Integration

### Configuration
- **Versions Supported:** v1, v2c, v3
- **Credential Storage:** Encrypted (Fernet with environment key)
- **Timeout:** Configurable per target (default 60s max)
- **Retry Count:** Configurable per target (with global max)
- **Backoff:** Exponential (0.1s * 2^attempt, max 0.5s)
- **Organization/Property Scope:** Per-target scoping

### Behavior
- **Success:** OID data retrieved successfully
- **Timeout:** Target did not respond before timeout (retryable)
- **Authentication Failed:** Invalid credentials (not retryable)
- **Privacy Failed:** Encryption/decryption error (not retryable)
- **Access Denied:** Authorization error (not retryable)
- **Host Unreachable:** Network error (retryable)
- **Transport Error:** Connection failed (retryable)

### Production Notes
- Each target handled independently
- Single unreachable switch does NOT block all SNMP polling
- Unsupported OIDs handled gracefully
- Partial responses processed with warnings
- Polling schedule respects target configuration
- Organization/property isolation enforced

### Troubleshooting
- Check target reachability (ping, telnet)
- Verify SNMP credentials (community string, auth/privacy)
- Check SNMP version compatibility
- Review firewall rules for SNMP ports (161/162)
- Check target SNMP agent status
- Review network latency for timeout issues

## Active Directory Integration

### Configuration
- **Method:** LDAP v3 over TLS (STARTTLS) or SSL
- **Credential Storage:** Encrypted (Fernet with environment key)
- **Connection Timeout:** Configurable per connection
- **Search Scope:** Configurable base DN and filters
- **Organization/Property Scoping:** Per-connection
- **Agent Routing:** Read-only computer enrichment via local agents

### Behavior
- **Success:** Computer data retrieved successfully
- **Bind Failure:** Authentication/connection error
- **Timeout:** Connection timeout
- **Unavailable:** AD server unreachable
- **Partial Failure:** Some queries succeed, others fail

### Production Notes
- AD enrichment is additive - existing device identity remains available
- Do NOT delete previously known device data because latest AD query failed
- Supports secure transport (TLS/SSL)
- Connection testing available
- Computer search base configurable
- Organization/property scoping enforced

### Troubleshooting
- Verify AD server connectivity
- Check LDAP credentials and permissions
- Verify TLS/SSL certificate validity
- Check base DN and search filters
- Review AD server logs for connection issues
- Verify firewall allows LDAP ports (389/636)

## SMTP/Email Integration

### Configuration
- **Method:** SMTP with configurable security (NONE, STARTTLS, SSL)
- **Host:** Configurable (no longer hardcoded to Gmail)
- **Port:** Configurable (default 587 for STARTTLS, 465 for SSL)
- **Security Mode:** Configurable (NONE, STARTTLS, SSL)
- **Authentication:** Username/password when required
- **Sender Address:** Configurable
- **Sender Name:** Configurable (default "HIOP Notifications")
- **Connection Timeout:** 15 seconds (configurable)
- **Send Timeout:** 30 seconds (configurable)
- **Max Retries:** 3 (configurable)
- **Retry Backoff:** 5 seconds (configurable)

### Legacy Configuration (Deprecated)
- **Hardcoded:** smtp.gmail.com:465 with SSL
- **Status:** Still supported for backward compatibility
- **Migration:** Use new production SMTP settings

### Secret Handling
- Credentials encrypted in environment variables
- Never exposed in API responses
- Never logged
- Never returned to frontend JavaScript
- UI shows "Configured" or "Not configured"
- Allows replacement without revealing current secret

### Retry Behavior
- **Retryable Errors:** Connection failures, timeout, transient SMTP errors
- **Non-Retryable Errors:** Authentication failures, permanent configuration errors
- **Max Retries:** 3 attempts (configurable)
- **Backoff:** Exponential (5s * attempt number)
- **Final State:** PENDING → SENT or FAILED

### Delivery State Tracking
- **PENDING:** Email queued for delivery
- **SENT:** Successfully delivered
- **FAILED:** Final failure after max retries
- **RETRYING:** Currently retrying

### Organization/Property Isolation
- Notifications scoped to organization/property
- No global recipient fallback
- No cross-tenant notification leakage

### Production Notes
- Do NOT hardcode Gmail credentials
- Do NOT hardcode port 465
- Do NOT hardcode sender identity
- Use environment-specific configuration
- Implement bounded retries (not indefinite)
- Record final failure state

### Troubleshooting
- Test email configuration via admin interface
- Check SMTP server connectivity
- Verify authentication credentials
- Check firewall allows SMTP ports (25, 587, 465)
- Review SMTP server logs for delivery issues
- Verify sender address is authorized by SMTP server

## Agent Integration (P4)

### Configuration
- **Authentication:** JWT bearer tokens
- **Organization/Property Binding:** Agent registration scoping
- **Job Delivery:** Agent-specific job queues
- **Observation Ingestion:** Agent-specific ingestion endpoints
- **Retry:** Configurable agent reconnection
- **Duplicate Protection:** Job IDs and observation deduplication

### Behavior
- **Connected:** Agent actively polling and reporting
- **Disconnected:** Agent not responding
- **Stale State:** Agent data not recently updated
- **Reconnected:** Agent recovered and reporting

### Production Notes
- Backend-generated jobs respect organization/property boundaries
- No cross-tenant job execution
- Agent authentication enforced
- Job delivery reliability critical
- Duplicate observation prevention

### Troubleshooting
- Check agent connectivity to backend
- Verify agent authentication tokens
- Review agent registration scoping
- Check agent job queue status
- Review observation ingestion logs
- Verify agent reconnection behavior

## Discovery Failure Handling

### Failure Types
- **Invalid Configuration:** Rejected before execution
- **Agent Unavailable:** Discovery fails completely
- **Network Unreachable:** Partial discovery possible
- **Target Timeout:** Individual target failures
- **Partial Success:** Some targets succeed, others fail
- **Complete Failure:** All targets fail

### Behavior
- **Partial Success:** Records successful observations, notes failures
- **Complete Failure:** No observations recorded
- **Network Issues:** Graceful degradation where possible
- **Configuration Errors:** Rejected before execution

### Production Notes
- Do NOT mark all devices offline on partial failure
- Preserve successful observations
- Record specific failure reasons
- Do not duplicate observations on retry

## Monitoring Failure Handling

### Failure Distinction
- **Monitoring Failure:** Polling source/infrastructure issue
- **Device Failure:** Actual device/network problem

### Behavior
- **Source Failure:** Explicit monitoring failure recorded
- **Device Failure:** Specific device health recorded
- **Polling Issues:** Do NOT mark every device offline
- **Previous Health:** Preserved during monitoring failures

### Production Notes
- Distinguish monitoring infrastructure failures from device failures
- Do not erase previous health on monitoring failure
- Do not create alert storms
- Do not duplicate telemetry

## Alert Processing

### Deduplication
- Same ongoing condition → one active alert
- Recovery → resolve existing alert
- New outage → new alert
- No duplicate active alerts for same condition

### Debounce
- Time-based alert suppression
- Configurable debounce intervals
- Prevents alert storms

### Event Ordering
- Timestamp-based event ordering
- Race condition handling
- State transition tracking

### Production Notes
- Implement proper alert deduplication
- Use appropriate debounce intervals
- Handle alert resolution correctly
- Prevent duplicate alert creation

## Job Execution

### Timeout Behavior
- All background jobs have bounded execution
- Discovery: Configurable timeout
- Monitoring: Configurable timeout
- Reports: Configurable timeout
- Notifications: SMTP timeout
- Enrichment: Configurable timeout
- Imports: Configurable timeout

### Retry Policy
- **Good Retry Candidates:** Network failures, temporary DB issues, SMTP transient failures, agent/backend transient failures
- **Bad Retry Candidates:** Invalid configuration, unauthorized credentials, malformed data, permission denial
- **Max Retries:** Configurable per job type
- **Backoff:** Exponential backoff where appropriate

### Production Notes
- Jobs must NOT hang indefinitely
- Use reasonable timeout/cancellation handling
- Do NOT retry permanent failures indefinitely
- Configure appropriate retry behavior per job type

## Export Safety

### Scope Enforcement
- Organization/property isolation enforced
- Permission checks before export
- User authentication required

### Large Export Handling
- Streaming where practical
- Memory limits enforced
- File size limits
- Temporary file cleanup

### File Safety
- Safe filename generation
- No path traversal
- No executable content
- Temporary file cleanup

### Production Notes
- Do NOT fetch thousands of records into browser unnecessarily
- Stream large exports where possible
- Clean up temporary files
- Enforce size limits

## Import Safety

### Scope Enforcement
- Organization/property isolation
- Authorization required
- Size limits enforced

### File Safety
- Safe filename generation
- No path traversal
- No executable content
- Content validation
- Temporary file cleanup

### Production Notes
- Temporary files must NOT remain forever
- Validate file content before processing
- Enforce size limits
- Clean up staging files

## Error Handling

### External Integration Errors
- **Bad:** "ConnectionError"
- **Better:** "SNMP target did not respond within 5 seconds"

### Guidelines
- Do NOT expose internal stack traces
- Log detailed diagnostics securely
- Return safe user-facing errors
- Provide actionable error messages

### Production Notes
- Error messages must be understandable
- Log full diagnostics for troubleshooting
- Return safe messages to users
- No internal stack traces in responses

## Integration Status

### Status Levels
- **NOT CONFIGURED:** Integration not set up
- **CONFIGURED:** Configuration exists but not tested
- **REACHABLE:** Connection successful
- **DEGRADED:** Partial functionality
- **FAILED:** Complete failure

### Status Reporting
- Use P5 health semantics
- CONFIGURED ≠ HEALTHY
- Show last success/failure timestamps
- Track error counts
- Provide troubleshooting guidance

### Production Notes
- Show truthful integration status
- Track last success/failure timestamps
- Track error counts for intermittent issues
- Use consistent status semantics

## Circuit-Breaker Behavior

### Simple Backoff Strategy
- Repeated failures → backoff
- Show degraded status
- Retry later with longer intervals
- Prevent hammering failing systems

### Example
- SNMP target failing repeatedly
- → backoff with increasing intervals
- → show degraded status
- → retry later

### Production Notes
- Do NOT build full resilience framework
- Use simple cooldown/backoff where appropriate
- Prevent continuous hammering of failing systems
- Show degraded status appropriately

## Configuration Validation

### Validation Rules
- **Invalid SMTP host:** Reject
- **Invalid SNMP target:** Allow save if appropriate, show unreachable
- **Invalid network range:** Reject
- **Invalid port:** Reject
- **Invalid AD URL:** Reject

### Production Notes
- Validate configuration before activation
- Do NOT silently save malformed configuration
- Provide clear validation error messages
- Allow saving unreachable targets with warnings

## Integration History

### Tracked Information
- **Last Success:** Timestamp of last successful operation
- **Last Failure:** Timestamp of last failure
- **Last Test:** Timestamp of last configuration test
- **Error Count:** Number of consecutive failures

### Production Notes
- Helps operators understand intermittent problems
- Track error trends
- Identify chronic issues
- Support troubleshooting decisions

## Security Considerations

### Tenant Isolation
- All integrations respect organization/property boundaries
- No cross-tenant data leakage
- Authentication and authorization enforced

### Credential Protection
- All credentials encrypted at rest
- No credential exposure in logs or API responses
- Secure credential rotation
- No hardcoded production credentials

### Network Security
- TLS/SSL for all external connections where possible
- Secure LDAP for AD integration
- Certificate validation
- Firewall configuration guidance

## Documentation Maintenance

### Update Requirements
- Update this document when integration behavior changes
- Update when new integrations are added
- Update when configuration options change
- Update when troubleshooting procedures change

### Version Control
- Document integration versions
- Track configuration schema changes
- Note deprecation timelines
- Maintain change history

## Testing Guidelines

### Isolated Testing
- Use isolated/test infrastructure
- Do NOT disrupt real hotel production infrastructure
- Safe to deliberately stop test services
- Safe to simulate network failures

### Test Scenarios
- DNS: success, timeout, unavailable
- DHCP: available, unavailable, stale data
- SNMP: success, timeout, invalid credentials, unsupported data, repeated failure
- AD: success, bind failure, timeout, unavailable
- SMTP: success, connection failure, authentication failure, retry, final failure
- Discovery: partial success, complete failure, retry, duplicate prevention
- Monitoring: source failure vs device failure
- Alerts: debounce, deduplicate, resolve
- Agent: disconnect, reconnect, retry, duplicate observation
- Pagination: correct page, correct scope, large dataset
- Export: organization isolation, permission checks

## Troubleshooting Common Issues

### DNS Issues
- DNS timeouts: Check DNS server response times
- DNS unavailable: Check DNS server connectivity
- Forward confirmation failures: Check DNS record consistency

### SNMP Issues
- Timeout: Check network latency and target response time
- Authentication: Verify community string or v3 credentials
- Unsupported OIDs: Check target SNMP MIB support
- Partial responses: Review target configuration

### AD Issues
- Bind failures: Check credentials and connection
- Timeout: Check network connectivity to AD server
- Certificate errors: Verify TLS/SSL certificate validity
- Search scope: Verify base DN and filters

### SMTP Issues
- Connection failures: Check SMTP server connectivity
- Authentication: Verify username/password
- Certificate errors: Check TLS/SSL certificate
- Delivery failures: Check recipient address and sender authorization

### Agent Issues
- Connection failures: Check agent connectivity to backend
- Authentication: Verify agent tokens
- Job delivery: Check agent job queue status
- Observation ingestion: Review agent upload logs

## Support and Escalation

### When to Escalate
- Integration failures affecting production
- Security concerns with external connections
- Performance issues with external systems
- Data consistency issues
- Configuration problems

### Information to Collect
- Integration status and error messages
- Timestamps of failures
- Configuration details (sanitized)
- Network connectivity information
- System health status
- Recent changes

### Support Contacts
- Internal platform team for infrastructure issues
- External vendor support for third-party systems
- Network team for connectivity issues
- Security team for credential/authentication issues