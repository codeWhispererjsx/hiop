# HIOP
## Hotel IT Operations Portal

Version: 1.0

Author: Joseph Oko

Status: Draft

Last Updated: July 2026

---

# 1. Introduction

## 1.1 Purpose

The Hotel IT Operations Portal (HIOP) is a centralized platform designed to help the IT department manage, monitor, and maintain hotel technology infrastructure.

The system provides real-time visibility into network-connected devices, asset inventory, network health, alerts, and maintenance activities.

---

## 1.2 Problem Statement

The current IT environment relies heavily on manual processes for:

- Device tracking
- Network monitoring
- Asset inventory
- Maintenance records
- Infrastructure visibility

These manual processes increase response time, reduce operational efficiency, and make troubleshooting difficult.

HIOP aims to provide a single source of truth for all IT operations.

---

## 1.3 Objectives

The system shall:

- Discover devices on the network
- Maintain an inventory of IT assets
- Monitor device availability
- Generate alerts for outages
- Record maintenance activities
- Provide operational reports
- Improve IT response time

---

# 2. Scope

## In Scope

- Device Inventory
- Network Discovery
- Device Monitoring
- Alerts
- Reporting
- User Management
- Asset Tracking

## Out of Scope (Version 1)

- Automatic device configuration
- Remote device shutdown
- Network configuration changes
- Firmware updates
- Active Directory integration

---

# 3. Users

## IT Administrator

Responsibilities:

- Manage users
- Configure settings
- View reports
- Monitor infrastructure

## IT Technician

Responsibilities:

- Resolve alerts
- Update device records
- Manage maintenance tickets

## IT Manager

Responsibilities:

- Review reports
- Track operational metrics
- Monitor infrastructure health

---

# 4. Functional Requirements

## FR-001 Device Discovery

The system shall discover devices within configured network ranges.

---

## FR-002 Device Inventory

The system shall maintain an inventory of discovered devices.

---

## FR-003 Device Monitoring

The system shall periodically check device availability.

---

## FR-004 Alert Management

The system shall generate alerts when devices become unavailable.

---

## FR-005 Dashboard

The system shall display:

- Total devices
- Online devices
- Offline devices
- Active alerts
- Recent activity

---

## FR-006 Reporting

The system shall generate operational reports.

---

## FR-007 User Authentication

The system shall require user authentication.

---

## FR-008 Maintenance Tracking

The system shall record maintenance activities linked to devices.

---

# 5. Non-Functional Requirements

## Performance

- Dashboard loads within 3 seconds
- Device scans complete within acceptable time limits

## Reliability

- System uptime target: 99%

## Security

- Authentication required
- Role-based access control
- Audit logging

## Scalability

- Support 1000+ devices

## Maintainability

- Modular architecture
- Documented APIs
- Version-controlled source code

---

# 6. Assumptions

- Devices are reachable through the hotel network.
- IT staff have authorization to perform monitoring.
- The organization maintains an internal network infrastructure.

---

# 7. Future Enhancements

- QR Asset Tracking
- Mobile Application
- SMS Notifications
- Email Alerts
- Active Directory Integration
- Floor Map Visualization
- Network Topology Mapping

---

# 8. Success Criteria

The project will be considered successful if:

- Device discovery functions correctly.
- Device monitoring operates continuously.
- Alerts are generated accurately.
- Inventory records remain accurate.
- IT staff can use the platform effectively.

---

End of Document