# HIOP 2.0.0-dev architecture

## Intelligent inventory import foundation

Epic 2A adds a backend-only staging bounded context beside official inventory and Discovery. `ImportSession` owns staged `ImportedDevice` rows; repositories provide persistence only; an unimplemented `ImportService` reserves orchestration; and abstract field validators reserve future normalization contracts.

No API, parser, matcher, approval flow, inventory merge, scheduler, or frontend is registered. See `IMPORT_ARCHITECTURE.md`.

## HIOP v2 Discovery foundation

Discovery is backend-only in Epic 1A. SQLAlchemy models and Alembic reserve persistence and tiered identity constraints; persistence-only repositories isolate database access; and an unimplemented service contract reserves later orchestration boundaries.

This phase registers no route, scheduler job, scanner, approval flow, inventory mutation, or frontend page. The detailed model, identity order, configuration namespace, and extension points are documented in `DISCOVERY.md`.

---

## Hotel IT Operations Portal (HIOP)

Version: 1.0

---

# Overview

HIOP follows a modern three-tier architecture consisting of:

- Presentation Layer
- Application Layer
- Data Layer

This architecture separates user interface, business logic, and data storage to improve scalability, maintainability, and security.

---

# High-Level Architecture

```

                Users
                   │
                   ▼
        React Frontend (TypeScript)
                   │
           HTTPS / REST API
                   │
                   ▼
        FastAPI Backend (Python)
        ┌──────────┼──────────┐
        │          │          │
        ▼          ▼          ▼
 Authentication  Scanner   Business Logic
        │          │
        └──────────┼──────────┘
                   │
                   ▼
           PostgreSQL Database
                   │
                   ▼
           Hotel Network Devices

```

---

# System Components

## Frontend

Technology

- React
- TypeScript
- Tailwind CSS

Responsibilities

- Dashboard
- Device Inventory
- Alerts
- Reports
- Maintenance
- User Management

---

## Backend

Technology

- FastAPI

Responsibilities

- Business Logic
- Authentication
- Device Management
- API Endpoints
- Scanner Control
- Alert Engine

---

## Database

Technology

- PostgreSQL

Responsibilities

- Store Users
- Store Devices
- Store Alerts
- Store Maintenance
- Store Scan History

---

## Network Scanner

Technology

- Python
- Nmap
- Ping

Responsibilities

- Discover Devices
- Ping Devices
- Detect Offline Devices
- Detect New Devices
- Collect Device Information

---

# Authentication Flow

1. User enters username and password.
2. FastAPI validates credentials.
3. JWT token is generated.
4. Token is returned to React.
5. React includes the token in future requests.

---

# Device Discovery Flow

1. Administrator starts a scan.
2. Scanner scans configured subnet.
3. Devices are discovered.
4. Device information is collected.
5. Database is updated.
6. Dashboard refreshes automatically.

---

# Device Monitoring Flow

1. Background scheduler starts.
2. Ping service checks all managed devices.
3. Device status is updated.
4. Alerts are generated if required.
5. Dashboard reflects the latest status.

---

# Security

- JWT Authentication
- Role-Based Access Control
- Password Hashing
- HTTPS
- Audit Logging

---

# Scalability

The architecture supports:

- Multiple network subnets
- 1000+ managed devices
- Multiple IT users
- Scheduled background tasks
- Future mobile application

---

# Future Expansion

The architecture allows future integration with:

- Opera PMS
- Active Directory
- SNMP-enabled devices
- Email notifications
- SMS alerts
- WhatsApp notifications
- Floor maps
- Network topology visualization

---

End of Document