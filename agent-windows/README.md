# HIOP Windows Agent

The agent is a .NET 10 Windows service and a system-tray application. The service uses HIOP's existing one-time enrollment, heartbeat, and allowlisted discovery/monitoring job APIs. Machine credentials are protected with Windows DPAPI and stored in the service-only ProgramData directory. The tray app lets an on-site user enroll the computer and view connection status.

The agent does not accept arbitrary command execution. HIOP administrators can queue only restart, shutdown, lock, enable/disable Remote Desktop, and Windows Update scan actions for a Windows device uniquely linked to its enrolled agent. Restart and shutdown are scheduled 60 seconds ahead; locking requires the interactive HIOP Agent tray app to be running in a signed-in Windows session. The LocalService agent delegates the fixed administrative actions to a separate LocalSystem broker over a named pipe restricted to the HIOP agent service SID and local administrators; the broker rejects every non-allowlisted request. Each request and reported outcome is audited. The current native RDP menu launches the operator's Microsoft Remote Desktop client directly; an agent-brokered RDP session is not implemented.

The backend migration that adds agent-to-device binding and endpoint telemetry must be applied before these controls are available. Run a discovery scan that includes the enrolled computer so HIOP can safely link its directly observed Windows identity to the managed device. The backend will only queue a power/session action when exactly one linked agent is online. Heartbeats report endpoint resource telemetry; the server stores five-minute samples for the seven-day uptime graph. Health reports and the customizable maintenance rules are available under Reports → System Maintenance.

Non-loopback server URLs must use HTTPS with a certificate trusted by the endpoint PCs. Configure the hotel server's HTTPS endpoint and internal certificate trust before enrolling agents from other computers; a download over plain HTTP will not make remote enrollment work.

## Build and test

Run from the repository root:

```powershell
dotnet test .\agent-windows\Hiop.Agent.slnx
.\agent-windows\scripts\build-agent.ps1
```

The build script publishes self-contained x64 service and tray executables and creates `backend\app\distributions\hiop-agent-windows.zip`.

## Install and enroll

Download and extract the Windows agent package from HIOP, then run `Install HIOP Agent.cmd` as an administrator. The installer creates the Windows service, applies restrictive ACLs to the credential/queue directory, and starts the visible tray app. In HIOP, create a one-time code for the intended property, then use **Connect or enroll...** from the HIOP Agent tray icon.

Running `Install HIOP Agent.cmd` from a newer package updates the binaries without replacing the enrolled credential or offline observation queue. `Remove HIOP Agent.cmd` prompts for confirmation, removes the local credential/queue and service, and leaves the HIOP registration available for audit history; revoke the registration in HIOP when the computer should no longer be authorized.

## Unified inventory behavior

Agent discovery observations enter HIOP Discovery Intelligence. When a scan's range includes an active address on the agent computer, the Windows agent reports local manufacturer, model, BIOS serial, operating system/version, processor, memory, and network adapters. It also associates MAC addresses from the local ARP table with reachable network targets; those ARP-derived MACs remain unverified discovery evidence and are not used alone to link inventory. The agent's own directly observed adapter MAC and serial can support a unique same-property match, with a unique hostname as a cautious fallback. Matched devices get network status/history refreshed, and configured identity rules can synchronize department and device type without overwriting manually maintained values. IP-only and ambiguous matches are not linked. Unmatched or conflicting discoveries remain in Discovery for administrator review before they are added to managed inventory. Spreadsheet imports and reviewed discoveries use the same managed device inventory.
