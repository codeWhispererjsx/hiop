# HIOP 2.0.0-dev user guide

## Discovery

Discovery lists devices observed on administrator-authorized private networks. Hostname, vendor, operating-system and device-type values are hints, and Confidence shows how much supporting evidence was available; it is never a certainty score. Search, filter, sort, paginate, and open a row for retained observation details. Administrators can run Discovery and approve, ignore, or reject pending observations. Approval is the only action that creates an official inventory device; Ignore and Reject never delete discovery history.

## Sign in and navigation

Open the HIOP address supplied by IT and sign in with your organization account. Your session lasts for the configured access-token period and is limited to the current browser tab session. If HIOP returns to Login, sign in again. Sign out before leaving a shared workstation.

The sidebar provides Overview, Devices, Network monitor, Alerts, Service tickets, and role-dependent administration pages. On a small screen, use the menu button. The theme button switches light and dark mode and preserves your preference.

## Dashboard

Overview shows real inventory availability, ticket counts, recent network checks, and active tickets. Use Refresh data when you need a current database snapshot. “Live channel: Connected” means authenticated device-status events can update the interface without a page reload.

## Devices

Devices lists PostgreSQL inventory. Search matches asset tag, hostname, IP, department, and device type. Status and department filters combine with search; changing them resets pagination. Select a row to view inventory fields and operational history.

Administrators can add and edit devices. Required network identifiers must be valid and unique where indicated. Inventory status describes ownership/lifecycle; Online/Offline/Unknown describes network reachability. Retire is a confirmed soft action: the device remains available with a Retired badge and its history is preserved.

## Network scanning

Network monitor shows current status, recent scan records, alerts, and response times. Authorized users can scan one device, all active devices, or an approved range. Controls are disabled while the request runs. Scanning is limited to the configured private network.

An Offline result means the address did not answer the configured ICMP check; it does not by itself prove a hardware failure. Confirm power, cabling, VLAN, firewall, and maintenance status before escalating.

## Alerts

Alerts are generated from recorded network-state transitions. Combine severity, acknowledgement, department, device, date, and search controls. Open an alert to inspect its device, scan context, available ticket, audit entries, and timeline. Authorized users can acknowledge an alert. Version 1.0.0 does not have a separate persisted Resolve action.

## Service tickets

Tickets support real search, combined filters, pagination, details, create, edit, assignment, close, reopen-through-edit, and administrator deletion. Only choose assignees returned by HIOP. Link a device when the incident relates to a real inventory record. Closing should follow operational confirmation, not just alert acknowledgement.

## Reports

Administrators can open Device Inventory, Network Status, Alerts, Tickets, Users, and Audit reports. Date ranges, search, filters, sorting, and pagination use real report data. CSV export honors the active filter set. Print uses the browser print dialog; review the preview before saving or printing.

## Settings and administration

Administrators manage safe runtime settings, organization text, hierarchy, scanner behavior, notifications, appearance, and system health. Passwords, JWT secrets, database credentials, and SMTP secrets are never editable or displayed. A successful toast means the API persisted the change; restart-required or unsupported capabilities are labelled honestly.

## Common workflow

1. Confirm the device and latest scan in Devices or Network monitor.
2. Review the related alert and acknowledge ownership.
3. Open or create a related service ticket.
4. Assign an eligible technician and record a clear description.
5. Resolve the physical/network cause and scan again.
6. Close the ticket when service is confirmed.
7. Use Audit and Reports to verify the operational record.

## Troubleshooting

- “Cannot reach backend”: report the time and URL to IT; do not repeatedly submit forms.
- Returned to login: the token is absent, invalid, expired, or the account is inactive.
- Reconnecting: live updates are temporarily unavailable; saved API data still loads if the backend is healthy.
- No records: clear active filters. If the empty state remains, the database has no matching rows.
- Scan rejected: the device/range may be outside the approved CIDR or your role may not permit scanning.

Never place passwords, tokens, private keys, or database credentials in device, ticket, alert, or audit text.
