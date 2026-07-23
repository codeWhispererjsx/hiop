# HIOP User Guide

## Hotel IT Operations Portal — Version 1.0.0

---

## Table of Contents

1. [Introduction](#introduction)
2. [Getting Started](#getting-started)
3. [Dashboard](#dashboard)
4. [Device Management](#device-management)
5. [Network Operations Center](#network-operations-center)
6. [Alerts](#alerts)
7. [Tickets](#tickets)
8. [Reports](#reports)
9. [Settings](#settings)
10. [Common Workflows](#common-workflows)
11. [Troubleshooting](#troubleshooting)

---

## Introduction

HIOP (Hotel IT Operations Portal) is an internal operations application for managing hotel IT infrastructure. It provides real-time device monitoring, alerting, ticketing, and reporting capabilities.

### Key Concepts

- **Devices**: IT assets such as servers, switches, access points, and workstations
- **Network Status**: Real-time connectivity state (Online, Offline, Unknown)
- **Inventory Status**: Lifecycle state (Active, Inactive, Retired)
- **Alerts**: Notifications triggered by device status changes
- **Tickets**: Operational issues tracked through resolution

### User Roles

| Role | Capabilities |
|------|-------------|
| **Administrator** | Full access: manage devices, users, settings, hierarchy, imports, and all operations |
| **Technician** | Operational access: view devices, run scans, manage tickets, view alerts and reports |
| **Staff** | Read-only access: view dashboard, devices, alerts, and tickets |

---

## Getting Started

### Logging In

1. Open HIOP in your browser (URL provided by your IT department)
2. Enter your **email address** and **password**
3. Click **Sign in**

> If you cannot log in, contact your system administrator.

### First Look

After logging in, you will see the **Dashboard** — the central monitoring view showing:

- Device status summary (online/offline counts)
- Recent activity feed
- Network scan status
- Quick-access charts

---

## Dashboard

The Dashboard provides an at-a-glance view of your IT environment.

### Status Cards

- **Total Devices**: All devices in inventory
- **Online**: Devices currently responding to network checks
- **Offline**: Devices not responding
- **Unknown**: Devices with undetermined status

### Activity Feed

Shows recent events including:
- Device status changes
- Alert creations
- Ticket updates
- Network scan results

### Network Status

Displays the last network scan time and results summary.

---

## Device Management

### Viewing Devices

1. Click **Devices** in the sidebar
2. Browse the device table showing:
   - Hostname
   - Asset tag
   - Device type
   - Department
   - Network status
   - Inventory status

### Searching and Filtering

- Use the **search field** to find devices by hostname, asset tag, IP, or MAC
- Filter by **status**, **department**, or **device type**
- Sort columns by clicking column headers

### Viewing Device Details

Click any device to open its detail page showing:
- Full device information
- Network scan history
- Related alerts
- Associated tickets
- Audit log

### Adding a Device (Administrators)

1. Click **Devices** in the sidebar
2. Click **Add device**
3. Fill in required fields (Asset tag, Hostname)
4. Complete optional fields (IP, MAC, Department, Location, etc.)
5. Click **Save**

### Editing a Device

1. Open the device detail page
2. Click **Edit**
3. Update the desired fields
4. Click **Save**

### Retiring a Device

1. Open the device detail page
2. Click **Retire**
3. Confirm the action
4. The device status changes to Retired (scans, alerts, and history are preserved)

---

## Network Operations Center

### Running a Network Scan

1. Click **Network** in the sidebar
2. Enter an IP address or select a device
3. Click **Scan**
4. View results showing response time and status

### Scan All Devices

Click **Scan all** to scan every active device in inventory. Results update in real time.

### Scan History

View past scan results including timestamps, response times, and status changes.

---

## Alerts

Alerts are created automatically when a device changes status (e.g., goes offline).

### Viewing Alerts

1. Click **Alerts** in the sidebar
2. Browse the alert table showing:
   - Timestamp
   - Device name
   - Previous and current status
   - Alert message
   - State (Active or Acknowledged)

### Filtering Alerts

Use the toolbar to filter by:
- **Severity**: Critical (Offline) or Informational
- **State**: Active or Acknowledged
- **Department**
- **Device**
- **Date**

### Acknowledging an Alert

1. Click **Acknowledge** on an active alert
2. The alert state changes to Acknowledged
3. Acknowledged alerts are visually dimmed

### Viewing Alert Details

Click the alert message to open the detail panel showing:
- Full device information
- Status transition details
- Timeline of events

---

## Tickets

Tickets track operational issues from reporting through resolution.

### Viewing Tickets

1. Click **Tickets** in the sidebar
2. Browse the ticket table showing:
   - Title
   - Priority
   - Status
   - Assigned technician
   - Created date

### Creating a Ticket

1. Click **Tickets** in the sidebar
2. Click **New ticket**
3. Enter:
   - **Title** (required)
   - **Description** (required)
   - **Priority** (Low, Medium, High)
   - **Device** (optional — link to affected device)
4. Click **Create**

### Assigning a Ticket

1. Open the ticket detail page
2. Click **Assign**
3. Select a technician from the list
4. The ticket status updates to In Progress

### Closing a Ticket

1. Open the ticket detail page
2. Click **Close**
3. The ticket status changes to Closed

### Deleting a Ticket (Administrators)

1. Open the ticket detail page
2. Click **Delete**
3. Confirm the deletion

---

## Reports

### Viewing Reports

1. Click **Reports** in the sidebar
2. Select a report type:
   - Devices
   - Network
   - Alerts
   - Tickets
   - Users
   - Audit
   - Discovery

### Customizing Reports

- Set a **date range** using the date picker
- Use **filters** to narrow results
- Sort by clicking column headers

### Exporting Reports

Click **Export CSV** to download the current report data.

---

## Settings (Administrators)

### General Settings

- Application name and branding
- Timezone and date format
- Default page size and landing page

### Organization Settings

- Organization name and property details
- Contact information

### Network Settings

- Approved network CIDR for scanning
- Scan interval and timeout
- Automatic alerting and ticketing

### Notification Settings

- Email notification preferences
- Recipient configuration

### Discovery Settings

- Discovery enable/disable
- CIDR ranges and ignore ranges
- Scan interval and concurrency

---

## Common Workflows

### Workflow 1: Respond to an Offline Device

1. **Dashboard** shows a device went offline
2. Click **Alerts** to view the critical alert
3. Click **Tickets** to see if a ticket was auto-created
4. Assign the ticket to a technician
5. Investigate and resolve the issue
6. Close the ticket
7. The alert is acknowledged

### Workflow 2: Add and Scan New Equipment

1. Click **Devices** → **Add device**
2. Enter device details and save
3. Click **Network** → enter the device IP
4. Click **Scan** to verify connectivity
5. View scan results in device history

### Workflow 3: Generate a Monthly Report

1. Click **Reports**
2. Select **Devices** report
3. Set the date range to the past month
4. Click **Export CSV**
5. Open the downloaded file in your spreadsheet application

---

## Troubleshooting

### Cannot Log In

- Verify your email and password are correct
- Contact your administrator to reset your password
- Check that your account is active

### Page Shows "Loading" Indefinitely

- Check your network connection
- The backend server may be restarting — wait a moment and refresh
- Contact your administrator if the issue persists

### Scan Returns No Response

- Verify the device IP address is correct
- Ensure the device is powered on and connected to the network
- Check that the IP is within the approved network range

### Report Shows No Data

- Expand the date range
- Check that filters are not excluding all results
- Verify data exists for the selected report type

---

## Support

For additional assistance, contact your system administrator or refer to the Administrator Guide.

## Inventory imports (2.0.0-dev)

Open **Inventory Import** from the sidebar to review recent sessions or resume unfinished work. Administrators can start a CSV or XLSX import; technicians can inspect sessions allowed by their role.

The wizard stages data before any inventory change:

1. Upload the file and, for Excel workbooks, explicitly choose the worksheet.
2. Review suggested column mappings. Asset tag and hostname are required, duplicate targets are blocked, and unknown columns may be ignored.
3. Run validation and inspect original values, normalized values, errors, warnings, and duplicate references. Staged rows are read-only; correct the source file and restart when necessary.
4. Run matching, compare candidates and evidence, and accept, reject, defer, or prepare a create-new decision. Conflicting identifiers are always shown.
5. Review location suggestions and either accept, reject, or override them with existing hierarchy records.
6. Resolve or defer conflicts, then review the summary and readiness checklist.

Leaving the wizard is safe. Use **Continue** on the imports page to reload backend-persisted progress. “Ready for Final Import” is a review state only; final device creation and merging are pending Epic 2E.
