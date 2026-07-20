# HIOP 2.0.0-dev database

## HIOP v2 Discovery persistence

Alembic revision `c87d380fc50a` adds `discovered_devices` and `discovery_runs`. Discovery rows use UUID primary keys, constrained status/review/run enums, nonnegative counters and timings, bounded confidence, and nullable foreign keys to devices, users, and network zones.

Duplicate protection follows matching priority through PostgreSQL partial unique indexes: case-insensitive MAC, approved device, IP plus case-insensitive hostname, then IP-only. Repositories do not own matching rules or transactions.

## HIOP v2 inventory import persistence

Alembic head `7f4e2c1a9d30` adds `import_sessions` and `imported_devices`. A UUID session owns staged rows through `ON DELETE CASCADE`; uploader history uses the existing string user key with `ON DELETE SET NULL`. PostgreSQL JSONB preserves bounded source fields without creating inventory relationships.

Checks constrain session and validation states, non-negative counters, and processed rows within the declared total. Lookup indexes cover session, asset tag, hostname, IP, MAC, status, and chronology. Case-insensitive partial unique indexes prevent repeated non-null asset tags and MAC addresses inside one session.

See `DISCOVERY.md` for the complete architectural contract.

---

## Hotel IT Operations Portal (HIOP)

Version: 1.0

---

# Purpose

The HIOP database stores all operational information required to manage, monitor, and maintain the hotel's IT infrastructure.

The database is designed to be:

- Scalable
- Normalized
- Maintainable
- Secure
- Suitable for enterprise environments

---

# Design Principles

The database follows these principles:

- Avoid duplicate data.
- Use UUIDs for primary keys.
- Maintain referential integrity using foreign keys.
- Separate lookup tables from transactional tables.
- Store historical records whenever possible.

---

# Core Entities

The database consists of the following core entities:

1. Users
2. Roles
3. Departments
4. Locations
5. Device Types
6. Devices
7. Network Scans
8. Ping History
9. Alerts
10. Maintenance Tickets
11. Audit Logs

---

# Roles

Purpose

Defines user permission levels.

Fields

- id (UUID)
- name
- description
- created_at

Example Roles

- Administrator
- IT Manager
- Technician
- Read Only

---

# Users

Purpose

Stores users who can log into HIOP.

Fields

- id (UUID)
- first_name
- last_name
- username
- email
- password_hash
- role_id
- is_active
- created_at
- updated_at

Relationships

- Many Users belong to one Role.

---

# Device Types

Purpose

Defines categories of devices.

Examples

- Desktop
- Laptop
- Printer
- Server
- Access Point
- Switch
- Router
- IP Phone
- POS Terminal

---

# Departments

Examples

- Reception
- Housekeeping
- Kitchen
- Finance
- IT
- Security
- Banquet

---

# Locations

Purpose

Stores the physical location of devices.

Fields

- id
- building
- floor
- room
- rack
- switch_name
- switch_port

---

# Devices

Purpose

Stores every managed asset.

Fields

- id
- hostname
- device_name
- ip_address
- mac_address
- serial_number
- manufacturer
- model
- operating_system
- device_type_id
- department_id
- location_id
- status
- first_seen
- last_seen
- created_at

---

# Network Scans

Purpose

Records every scan.

Fields

- id
- started_at
- completed_at
- subnet
- devices_found
- duration
- status

---

# Ping History

Purpose

Stores historical ping results.

Fields

- id
- device_id
- latency
- status
- checked_at

---

# Alerts

Purpose

Stores all generated alerts.

Examples

- Device Offline
- High Latency
- New Device
- Duplicate IP

Fields

- id
- device_id
- severity
- title
- description
- status
- created_at

---

# Maintenance Tickets

Purpose

Tracks maintenance work.

Fields

- id
- device_id
- assigned_to
- issue
- priority
- status
- opened_at
- closed_at

---

# Audit Logs

Purpose

Tracks all important user actions.

Fields

- id
- user_id
- action
- entity
- timestamp

Roles
  │
  ▼
Users
  │
  ▼
Maintenance Tickets

Device Types
        │
Departments
        │
Locations
        │
        ▼
      Devices
     /   |    \
    ▼    ▼     ▼
 Alerts Ping History Maintenance
        |
        ▼
   Network Scans