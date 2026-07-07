# User Interface Design

## Hotel IT Operations Portal (HIOP)

Version: 1.0

Author: Joseph Oko

Status: Draft

Last Updated: 07 July 2026

---

# Overview

The HIOP user interface is designed to provide IT staff with a modern, responsive, and intuitive experience for monitoring and managing the hotel's IT infrastructure.

---

# Design Principles

- Clean and minimal interface
- Fast navigation
- Responsive design
- Dark/Light mode support (Future)
- Role-based navigation
- Real-time dashboard updates

---

# Application Pages

## 1. Login

Purpose

Authenticate users before granting access.

Components

- Username
- Password
- Login Button
- Forgot Password

---

## 2. Dashboard

Purpose

Provides an overview of the hotel's IT infrastructure.

Widgets

- Online Devices
- Offline Devices
- Newly Discovered Devices
- Active Alerts
- Open Maintenance Tickets

Charts

- Devices by Department
- Devices by Type
- Alerts by Severity

Recent Activity

- Device Online
- Device Offline
- Maintenance Completed
- New Device Found

---

## 3. Device Inventory

Purpose

Displays every managed device.

Components

- Search Bar
- Filter Panel
- Device Table
- Pagination

Columns

- Device Name
- IP Address
- MAC Address
- Department
- Device Type
- Status
- Last Seen

Actions

- View
- Edit
- Delete

---

## 4. Device Details

Displays complete information for a selected device.

Sections

- General Information
- Network Information
- Location
- Ping History
- Alerts
- Maintenance History

---

## 5. Network Scanner

Components

- Scan Button
- Stop Scan
- Scan Progress
- Discovery Queue
- Scan History

---

## 6. Alerts

Displays active alerts.

Columns

- Severity
- Device
- Description
- Time
- Status

Actions

- Acknowledge
- Resolve

---

## 7. Maintenance

Displays maintenance tickets.

Columns

- Ticket ID
- Device
- Technician
- Priority
- Status
- Date Opened

Actions

- Create
- Edit
- Close

---

## 8. Reports

Available Reports

- Inventory
- Offline Devices
- Maintenance
- Scan History

Export

- PDF
- Excel
- CSV

---

## 9. User Management

Administrator Only

Functions

- Create User
- Edit User
- Disable User
- Assign Role

---

## 10. Settings

Configure

- Departments
- Device Types
- Locations
- Scan Interval
- Notifications
- Roles

---

# Navigation

Sidebar

- Dashboard
- Devices
- Scanner
- Alerts
- Maintenance
- Reports
- Users
- Settings

Top Bar

- Search
- Notifications
- Profile
- Logout

---

End of Document