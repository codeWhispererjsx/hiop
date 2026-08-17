# HIOP Local Agent Deployment Guide

## Purpose and supported platform

HIOP Local Agent 1.0 is an outbound-only Windows service for Windows Server 2019+ and supported Windows 10/11 machines inside a hotel network. It performs allowlisted observation jobs and uploads evidence to HIOP over HTTPS. It has no inbound listener, shell, remote desktop, arbitrary PowerShell, remediation, or infrastructure-configuration channel.

Hosted deployments use Browser to HIOP Cloud to outbound HTTPS to Property Agent to Hotel LAN. On-premises deployments use the same boundary with an internal HTTPS HIOP server.

## Prerequisites

- 64-bit Python 3.12 or later available through the Windows py launcher.
- Local administrator permission for service installation only.
- Outbound TCP 443 from the agent host to the HIOP backend.
- DNS resolution for HIOP and a certificate trusted by Windows.
- Local firewall permission for explicitly configured ICMP, DNS, LDAP/LDAPS, and SNMP targets.
- A dedicated least-privilege service account when directory or network integrations require it.

The service has no inbound firewall rule. Collection permissions depend on the job: DNS needs no elevation; ICMP and neighbor visibility follow Windows policy; SNMP/LDAP require network access and scoped read-only credentials.

## Enrollment and installation

1. Open Administration, Organization, Local agents.
2. Select the property, enter a stable name, and generate an enrollment.
3. Copy the one-time token. It expires after 15 minutes and cannot be reused.
4. In elevated PowerShell run install-service.ps1 with BackendUrl and EnrollmentToken.

The installer creates an isolated environment, enrolls the machine, protects its credential with Windows DPAPI, installs HIOPLocalAgent with automatic startup, and configures bounded restart-on-failure behavior. The human administrator password and browser token are never stored.

## Configuration and recovery

Non-secret configuration is stored at %ProgramData%\HIOP Agent\agent.json. The backend URL must use HTTPS and certificate verification stays enabled. HTTP is accepted only for explicitly enabled localhost test mode.

The durable SQLite queue is bounded by queue_max_items and queue_retention_days. When full, it removes the oldest observation. Retries use bounded exponential backoff. Duplicate observation IDs are accepted idempotently.

- Service status: Get-Service HIOPLocalAgent
- Safe log: %ProgramData%\HIOP Agent\agent.log
- Queue: %ProgramData%\HIOP Agent\queue.db
- Restart: Restart-Service HIOPLocalAgent

Logs contain timestamps, severity, and safe error types. Credentials, tokens, integration passwords, and full observation payloads are not logged. HIOP derives online, stale, and offline state from heartbeat age.

If connectivity is lost, results remain in the bounded queue and upload after recovery. Repeated rejection uses backoff. A revoked agent receives HTTP 401 and cannot heartbeat, fetch jobs, or ingest observations.

## Revocation, re-enrollment, upgrade, and uninstall

Use Revoke in HIOP to invalidate the machine credential immediately while retaining history. Re-enrollment requires a new one-time token. Automatic upgrade is intentionally not supported in P4; deploy reviewed updates through the hotel's normal software process.

Run uninstall-service.ps1 as administrator to remove the service. Server-side identity, audit history, and observations remain.

## Security boundary

The authenticated machine identity, never request headers or payload IDs, determines organization and property. Mismatched scope claims are denied. Jobs are restricted to DISCOVERY, MONITORING, PING, DNS_LOOKUP, ARP_SNAPSHOT, SNMP_POLL, and AD_ENRICHMENT. Unknown types and command execution are rejected. Payloads are limited to 1 MB and protocol schema version 1.

SNMP and Active Directory adapters require existing property-scoped HIOP integration configuration. Their credentials must be delivered only to the bound agent over TLS, held in memory for the job, and never placed in UI responses or logs.
