# HIOP desktop direction

HIOP now has two clear parts.

The web platform remains the public and commercial side of HIOP. It handles the landing page, registration, account ownership, the Platform Control Center, app downloads, licensing, billing later, support, and release management.

The Windows desktop app becomes the real hotel IT operations product. It should run inside the hotel network and handle discovery, monitoring, SNMP, Active Directory, inventory, departments, locations, reports, audit logs, backup, restore, and day-to-day operations.

## Why this split exists

Hosted browsers cannot directly scan a hotel LAN. A cloud site can only see the internet and its backend. Local discovery needs a process running on the hotel machine or server. A Windows desktop app solves that because it runs inside the same network as the switches, printers, PCs, access points, and servers.

## What stays in the web platform

- Landing page
- Registration and login
- Platform Control Center
- Organization ownership
- Licensing and activation
- Desktop app download
- Billing later, after pilot stability
- Support and release notes
- High-level account administration

## What moves into the desktop app

- Network discovery
- Live monitoring
- Device approval and inventory
- Departments and locations
- SNMP setup and tests
- Active Directory setup and tests
- Local agent work, merged into the app over time
- Reports and exports
- Audit logs
- Backup and restore
- Local system health

## First implementation step

The current React application can now build in desktop mode. Desktop mode uses local app routing and points API traffic at a local backend on `127.0.0.1:8765`.

This is the foundation for packaging HIOP as a Windows app without throwing away the current interface.

## Target customer flow

1. User visits the HIOP website.
2. User registers or logs in.
3. User downloads the Windows app from the Platform Control Center.
4. User installs HIOP Desktop inside the hotel network.
5. User activates the app with the account or license.
6. User creates the organization, property, departments, and locations.
7. User scans the local network.
8. User approves devices into inventory.
9. User monitors and operates HIOP locally.
