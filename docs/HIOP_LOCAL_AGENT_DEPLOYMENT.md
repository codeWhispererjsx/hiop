# HIOP Local Agent Deployment Guide

## Purpose and supported platform

The HIOP Local Agent (version 1.3.0) is a .NET 10 Windows service with a system-tray app for Windows 10/11 and Windows Server computers inside a hotel network. It connects outbound to HIOP over HTTPS, sends heartbeats and device health, runs allowlisted observation jobs, and shows administrator notices. It has no inbound listener, shell, remote desktop, arbitrary PowerShell, remote power control, or general command channel.

Source, build steps, and behavior details are in [agent-windows/README.md](../agent-windows/README.md). The earlier Python agent has been removed.

Hosted deployments use Browser to HIOP Cloud to outbound HTTPS to Property Agent to Hotel LAN. On-premises deployments use the same boundary with an internal HTTPS HIOP server.

## Prerequisites

- Local administrator permission for installation only.
- Outbound TCP 443 from the computer to the HIOP backend.
- DNS resolution for HIOP and a certificate trusted by Windows. Non-loopback server URLs must use HTTPS.
- Local firewall permission for the ICMP and DNS targets used by discovery and monitoring.

The service has no inbound firewall rule.

## Enrollment and installation

1. Download `HIOP-Agent-Windows.exe` from HIOP and run it on the company computer.
2. Enter the hotel's HTTPS HIOP address and approve the Windows administrator prompt. The installer creates the service, applies restrictive ACLs to its credential and queue directory, and starts the tray app.
3. In HIOP, open Local agents, select the property, and create a one-time enrollment code.
4. Enter the code in the tray enrollment window.

The machine credential is protected with Windows DPAPI. The administrator's password and browser token are never stored. The ZIP package remains available for administrators who deploy the component files manually.

## Configuration and recovery

Non-secret configuration is stored at `%ProgramData%\HIOP\Agent\agent.json`; the credential and offline queues are in `%ProgramData%\HIOP\Agent\State`. Observations and power events wait in durable local queues while offline and upload after recovery. Duplicate IDs are accepted idempotently. HIOP derives online, stale, and offline state from heartbeat age.

- Service status: `Get-Service "HIOP Local Agent"`
- Restart: `Restart-Service "HIOP Local Agent"`

A revoked agent receives HTTP 401 and cannot heartbeat, fetch jobs, or submit observations.

## Revocation, re-enrollment, upgrade, and uninstall

Use Revoke in HIOP to invalidate the machine credential immediately while retaining history. Re-enrollment requires a new one-time code.

Running `Install HIOP Agent.cmd` from a newer package updates the binaries without replacing the enrolled credential or offline queue. Automatic upgrade is not supported; deploy reviewed updates through the hotel's normal software process. `Remove HIOP Agent.cmd` removes the service, credential, and queue. Server-side identity, audit history, and observations remain.

## Security boundary

The authenticated machine identity, never request headers or payload IDs, determines organization and property. Mismatched scope claims are denied. The agent executes only DISCOVERY, MONITORING, PING, DNS_LOOKUP, and ARP_SNAPSHOT jobs and rejects any other job type. Administrator notices are bounded plain text and are never interpreted as markup or commands. End-of-day reminders, the Stay On prompt, automatic shutdown, and Smart Lock run locally on the computer, and every power event is audited.
