# HIOP Local Agent Deployment Guide

## Overview

The HIOP Local Agent is a secure, production-capable agent that runs inside hotel networks to perform local discovery, monitoring, and collection work on behalf of the hosted HIOP platform. The agent enables hosted HIOP to reach internal network resources that are otherwise inaccessible from the cloud.

## Supported Platform

**Windows Server / Windows Machine**
- Windows Server 2016 or later
- Windows 10/11 (for smaller deployments)
- Administrative privileges are NOT required for basic operations
- The agent runs as a Windows service without requiring a logged-in session

## Prerequisites

### System Requirements
- Windows Server 2016+ or Windows 10/11
- 100 MB disk space for agent installation
- 50 MB RAM minimum recommended
- Network connectivity to HIOP backend (HTTPS outbound)
- Python 3.12+ (included in agent package)

### Network Requirements
- Outbound HTTPS access to HIOP backend (port 443)
- No inbound firewall ports required
- Access to internal network targets for discovery/monitoring:
  - ICMP (ping) for device discovery
  - DNS for hostname resolution
  - SNMP for device monitoring
  - Active Directory (if AD integration is used)

### Permissions
- Standard user permissions are sufficient for basic operations
- Some advanced features may require elevated permissions:
  - ARP table access (usually available to standard users)
  - Network interface queries
  - Service information access

## Installation

### Method 1: PowerShell Service Installation (Recommended)

1. **Download the Agent Package**
   - Obtain the HIOP Agent package from your HIOP administrator
   - Extract to a temporary directory (e.g., `C:\Temp\HIOP-Agent`)

2. **Generate Enrollment Token**
   - Log in to HIOP administration panel
   - Navigate to Administration → Local Agents
   - Click "Create Enrollment"
   - Select the property and set expiration time
   - Copy the generated enrollment token

3. **Install the Service**
   ```powershell
   # Open PowerShell as Administrator
   cd C:\Temp\HIOP-Agent
   .\install-service.ps1 -BackendUrl "https://your-hiop-instance.com" -EnrollmentToken "your-enrollment-token"
   ```

4. **Verify Installation**
   ```powershell
   # Check service status
   Get-Service HIOPLocalAgent

   # View recent logs
   Get-Content "$env:ProgramData\HIOP Agent\agent.log" -Tail 20
   ```

### Method 2: Manual Installation

1. **Create Configuration File**
   ```json
   {
     "backend_url": "https://your-hiop-instance.com",
     "data_dir": "%ProgramData%\\HIOP Agent",
     "heartbeat_seconds": 60,
     "poll_seconds": 15,
     "queue_max_items": 10000,
     "queue_retention_days": 7,
     "request_timeout_seconds": 30,
     "allow_insecure_http": false
   }
   ```
   Save as `C:\ProgramData\HIOP Agent\agent.json`

2. **Enroll the Agent**
   ```powershell
   cd C:\Path\To\Agent
   python -m hiop_agent --config "C:\ProgramData\HIOP Agent\agent.json" --enroll "your-enrollment-token"
   ```

3. **Install as Service**
   ```powershell
   python -m hiop_agent.windows_service install
   python -m hiop_agent.windows_service start
   ```

## Configuration

### Configuration File Location
- Default: `C:\ProgramData\HIOP Agent\agent.json`
- Can be overridden via environment variable: `HIOP_AGENT_CONFIG`

### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `backend_url` | string | required | HIOP backend URL (HTTPS required) |
| `data_dir` | string | `%ProgramData%\HIOP Agent` | Directory for agent data and logs |
| `heartbeat_seconds` | integer | 60 | Heartbeat interval in seconds |
| `poll_seconds` | integer | 15 | Job polling interval in seconds |
| `queue_max_items` | integer | 10000 | Maximum queued observations |
| `queue_retention_days` | integer | 7 | Queue retention period in days |
| `request_timeout_seconds` | integer | 30 | HTTP request timeout |
| `allow_insecure_http` | boolean | false | Allow HTTP for local testing only |

### Security Considerations

**IMPORTANT:**
- Never set `allow_insecure_http: true` in production
- The agent credentials are stored securely using Windows DPAPI
- Enrollment tokens are one-time and expire after use
- Agent credentials support rotation through revocation/re-enrollment

## Service Management

### Start/Stop Service
```powershell
# Start
Start-Service HIOPLocalAgent

# Stop
Stop-Service HIOPLocalAgent

# Restart
Restart-Service HIOPLocalAgent
```

### Service Status
```powershell
Get-Service HIOPLocalAgent
```

### View Logs
```powershell
# Real-time log monitoring
Get-Content "$env:ProgramData\HIOP Agent\agent.log" -Wait -Tail 20

# Last 50 lines
Get-Content "$env:ProgramData\HIOP Agent\agent.log" -Tail 50
```

## Uninstallation

### Automatic Uninstallation
```powershell
cd C:\Path\To\Agent
.\uninstall-service.ps1
```

### Manual Uninstallation
```powershell
# Stop and remove service
python -m hiop_agent.windows_service stop
python -m hiop_agent.windows_service remove

# Remove files
Remove-Item -Recurse -Force "C:\ProgramData\HIOP Agent"
```

## Troubleshooting

### Agent Not Starting

**Check Service Status:**
```powershell
Get-Service HIOPLocalAgent | Select-Object Status, StartType
```

**Check Event Viewer:**
- Navigate to Windows Event Viewer → Windows Logs → Application
- Look for "HIOPLocalAgent" events

**Check Configuration:**
```powershell
Get-Content "$env:ProgramData\HIOP Agent\agent.json"
```

### Network Connectivity Issues

**Test Backend Connectivity:**
```powershell
Test-NetConnection your-hiop-instance.com -Port 443
```

**Check Proxy Settings:**
- If your network uses a proxy, configure system proxy settings
- The agent respects system proxy configuration

### Enrollment Failures

**Common Causes:**
- Invalid or expired enrollment token
- Incorrect backend URL
- Network connectivity issues
- Property ID does not exist

**Solutions:**
- Generate a new enrollment token
- Verify backend URL is correct and accessible
- Check network connectivity
- Verify property exists in HIOP

### Queue Capacity Issues

**Check Queue Status:**
```powershell
# The agent reports queue status in heartbeat
# Check agent details in HIOP administration panel
```

**Increase Queue Capacity:**
- Edit `agent.json` and increase `queue_max_items`
- Restart the service

## Security Features

### Authentication
- Unique agent identity generated during enrollment
- Secure credential storage using Windows DPAPI
- Credentials never exposed in logs or UI
- Credentials support revocation

### Organization/Property Isolation
- Agent bound to one organization and one property
- Backend validates agent identity on every request
- Agent cannot submit data for other organizations/properties
- Cross-organization access is strictly prohibited

### Job Authorization
- Only allowlisted job types are executed
- Arbitrary command execution is not supported
- Network jobs validate against approved property ranges
- Job timeouts prevent hanging operations

### Communication Security
- All communication uses HTTPS/TLS
- Certificate validation is enforced
- Request timestamps and nonces prevent replay attacks
- Payload size limits prevent resource exhaustion

## Monitoring

### Agent Health Indicators

**In HIOP Administration Panel:**
- Agent Status: ONLINE / STALE / OFFLINE / REVOKED
- Last Heartbeat timestamp
- Last Discovery timestamp
- Last Monitoring timestamp
- Pending Queue count
- Agent Uptime

**In Agent Logs:**
- Successful heartbeats
- Job execution results
- Observation upload status
- Error messages with context

### Recommended Monitoring

**Check Regularly:**
- Agent status in HIOP administration panel
- Agent logs for errors or warnings
- Queue capacity usage
- Network connectivity between agent and backend

**Alert Thresholds:**
- Agent offline for more than 10 minutes
- Queue capacity > 80%
- High error rate in agent logs
- Failed observation uploads

## Upgrade Process

### Pre-Upgrade Checklist
- Backup current configuration
- Note current agent version
- Ensure backend compatibility
- Schedule maintenance window

### Upgrade Steps
1. Stop the agent service
2. Backup configuration file
3. Replace agent files with new version
4. Restart the agent service
5. Verify agent status in HIOP panel
6. Check logs for any errors

### Rollback
If upgrade fails:
1. Stop the service
2. Restore previous agent files
3. Restore configuration file
4. Restart the service
5. Verify functionality

## Deployment Models

### Hosted HIOP (Current Model)
- HIOP backend runs in cloud
- Agent runs in hotel network
- Secure outbound communication
- No inbound firewall changes required

### On-Prem HIOP (Future)
- Both HIOP backend and agent run on-premises
- Agent communicates to local HIOP instance
- No external network access required
- Enhanced control and compliance

## Best Practices

### Security
- Use HTTPS in production environments
- Regularly rotate agent credentials via re-enrollment
- Monitor agent logs for suspicious activity
- Keep agent software updated
- Restrict access to agent configuration files

### Performance
- Monitor queue capacity regularly
- Adjust heartbeat/poll intervals based on network conditions
- Ensure adequate disk space for queue storage
- Monitor agent resource usage

### Reliability
- Configure service recovery policies
- Monitor agent connectivity
- Set up alerts for agent offline status
- Test agent failover scenarios

## Support

### Getting Help
- Check this deployment guide first
- Review agent logs for error messages
- Check HIOP administration panel for agent status
- Contact HIOP support with:
  - Agent ID
  - Organization/Property name
  - Error messages from logs
  - Configuration details (without credentials)

### Known Limitations
- Currently supports Windows only
- Linux support planned for future releases
- SNMP polling requires scoped credential configuration
- Active Directory integration requires scoped connection configuration
- Some advanced features may require elevated permissions

## Appendix

### File Locations
- **Agent executable:** Installation directory
- **Configuration:** `C:\ProgramData\HIOP Agent\agent.json`
- **Logs:** `C:\ProgramData\HIOP Agent\agent.log`
- **Queue database:** `C:\ProgramData\HIOP Agent\queue.db`
- **Credential storage:** `C:\ProgramData\HIOP Agent\credential.dpapi`

### Service Details
- **Service Name:** HIOPLocalAgent
- **Display Name:** HIOP Local Hotel Agent
- **Description:** Secure outbound observation and collection service for HIOP
- **Startup Type:** Automatic
- **Log On As:** Local System

### API Endpoints
- **Enrollment:** `POST /api/v1/agent/enroll`
- **Heartbeat:** `POST /api/v1/agent/heartbeat`
- **Job Poll:** `GET /api/v1/agent/jobs`
- **Job Update:** `POST /api/v1/agent/jobs/{job_id}`
- **Observation Upload:** `POST /api/v1/agent/observations`

### Allowed Job Types
- `DISCOVERY` - Network discovery scan
- `MONITORING` - Device monitoring
- `PING` - ICMP ping
- `DNS_LOOKUP` - DNS resolution
- `ARP_SNAPSHOT` - ARP table collection
- `SNMP_POLL` - SNMP polling (requires credential configuration)
- `AD_ENRICHMENT` - Active Directory enrichment (requires connection configuration)

---

**Document Version:** 1.0
**Last Updated:** 2025-01-19
**HIOP Version:** 1.0.0
