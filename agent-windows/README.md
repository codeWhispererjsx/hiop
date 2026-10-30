# HIOP Windows Agent

The agent is a .NET 10 Windows service and a system-tray application. The service uses HIOP's existing one-time enrollment, heartbeat, and allowlisted discovery/monitoring job APIs. Machine credentials are protected with Windows DPAPI and stored in the service-only ProgramData directory. The tray app lets an on-site user enroll the computer, view connection status, and receive admin notices.

The agent reports heartbeat telemetry, approved inventory/network observations, and device health (Fast Startup, lid-close action, battery health, pending Windows updates, and the latest shutdown event). Authorized administrators can send short-lived plain-text notices to explicitly selected agents. The interactive tray requests one notice toast per poll and acknowledges that display request to HIOP; Windows does not confirm whether a user saw it. Notice text is bounded and is never interpreted as markup or a command.

End-of-day nudges run locally at 10:45 p.m. device time. At 11:30 p.m., a device idle for at least 30 minutes may show a reasoned Stay On prompt and a 60-second countdown. The tray requests a normal Windows shutdown only after 60 continuous seconds of idle, when no known work apps are running, no unrecognized visible application windows remain, and every safety check succeeds; it never force-closes applications. A conservative process list blocks common document editors and browsers even when they have no visible window. HIOP cannot confirm whether an unknown hidden application has unsaved work, so failed checks and detected work apps or windows block automatic shutdown. Smart Lock is also local: the server heartbeat supplies only a fixed five-minute idle policy, and the tray applies it to the signed-in session. Power events and Stay On reasons are stored in a durable local queue and submitted to the property-scoped audit API when connected.

There is no remote shutdown, restart, lock command, broadcast target, or general command channel. Updating an older agent package stops and removes the legacy LocalSystem command broker.

Run a discovery scan that includes the enrolled computer so HIOP can safely link its directly observed Windows identity to the managed device. Heartbeats report endpoint resource telemetry, including the current IP address and logged-in user; the server stores five-minute samples for the seven-day uptime graph. Health reports are available under Reports → System Maintenance. Legacy scheduled endpoint-control rules are retained for audit visibility but are disabled and cannot be created or edited in Phase 1. No database migration is needed for notices; they use the existing agent-job table.

Non-loopback server URLs must use HTTPS with a certificate trusted by the endpoint PCs. Configure the hotel server's HTTPS endpoint and internal certificate trust before enrolling agents from other computers; a download over plain HTTP will not make remote enrollment work.

## Build and test

Run from the repository root:

```powershell
dotnet test .\agent-windows\Hiop.Agent.slnx
.\agent-windows\scripts\build-agent.ps1
```

The build script publishes the self-contained x64 service and tray executables, creates `backend\app\distributions\hiop-agent-windows.zip`, and builds the single-file `backend\app\distributions\HIOP-Agent-Windows.exe` installer. The installer asks for the hotel's HTTPS HIOP address, installs the service and tray app, and opens the one-time enrollment flow.

Building the installer requires NSIS (`makensis.exe`). The script uses it from `PATH`, an electron-builder NSIS cache, or the `-NsisPath` argument. The installer file version is read from `AgentConfiguration.Version`.

## Install and enroll

Download and double-click `HIOP-Agent-Windows.exe` on the company Windows computer. Enter the hotel's HTTPS HIOP address and approve the Windows administrator prompt. The installer creates the Windows service, applies restrictive ACLs to the credential/queue directory, and starts the visible tray app. In HIOP, create a one-time code for the intended property, then enter it in the tray enrollment window.

The ZIP package remains available for IT administrators who need to deploy or inspect its component files manually.

Running `Install HIOP Agent.cmd` from a newer package updates the binaries without replacing the enrolled credential or offline observation queue. `Remove HIOP Agent.cmd` prompts for confirmation, removes the local credential/queue and service, and leaves the HIOP registration available for audit history; revoke the registration in HIOP when the computer should no longer be authorized.

## Unified inventory behavior

Agent discovery observations enter HIOP Discovery Intelligence. When a scan's range includes an active address on the agent computer, the Windows agent reports local manufacturer, model, BIOS serial, operating system/version, processor, memory, and network adapters. It also associates MAC addresses from the local ARP table with reachable network targets; those ARP-derived MACs remain unverified discovery evidence and are not used alone to link inventory. The agent's own directly observed adapter MAC and serial can support a unique same-property match, with a unique hostname as a cautious fallback. Matched devices get network status/history refreshed, and configured identity rules can synchronize department and device type without overwriting manually maintained values. IP-only and ambiguous matches are not linked. Unmatched or conflicting discoveries remain in Discovery for administrator review before they are added to managed inventory. Spreadsheet imports and reviewed discoveries use the same managed device inventory.
