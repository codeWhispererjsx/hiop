# HIOP 2.0.0-dev database

PostgreSQL is the only supported production database. SQLAlchemy models define the runtime mapping and Alembic is the sole schema-change mechanism. The current head is `e8a9b0c1d2e3`.

Epic 3A adds `active_directory_connections`, `active_directory_sync_configurations`, `active_directory_objects`, `active_directory_sync_runs`, and `active_directory_match_candidates` for directory integration staging and telemetry.

## Core tables

| Table | Purpose and important fields |
| --- | --- |
| `users` | String UUID ID, unique username/email, bcrypt hash, role, active flag, timestamps |
| `devices` | UUID ID, unique asset tag/serial/MAC, inventory and network states, network identifiers, hierarchy foreign keys, timestamps |
| `network_scans` | Device FK, IP, Online/Offline result, response time, scan timestamp |
| `alerts` | Device FK, prior/current network state, message, acknowledgement, timestamp |
| `tickets` | Reporter/assignee user FKs, optional device FK, title, description, priority, state, timestamps |
| `audit_logs` | Actor label, action, entity type/ID, safe description, immutable timestamp |
| `system_settings` | Explicit non-secret runtime configuration key/value pairs |
| `properties`, `buildings`, `floors`, `rooms`, `departments`, `network_zones` | Active/inactive hierarchy catalog and parent relationships |
| `discovered_devices` | Consolidated passive Discovery observations, identity metadata, constrained status/review state, and optional inventory/reviewer/zone links |
| `discovery_runs` | Future Discovery run lifecycle, trigger metadata, counters, duration, and error summary |
| `import_sessions` | Inventory-import lifecycle, uploader, processing timestamps, counters, safe file metadata, column mapping, and worksheet selection |
| `imported_devices` | Session-owned staged candidates, source row, raw/normalized JSON, structured errors/warnings, identifiers, and validation state |
| `import_match_candidates` | Ranked typed targets across inventory, Discovery, and staging with scores, evidence, conflicts, recommendations, and review history |
| `import_location_suggestions` | Auditable department, building, floor, room, and network-zone suggestions with confidence and review state |
| `active_directory_connections` | Domain connection profiles, LDAP settings, encrypted bind secrets, test statuses |
| `active_directory_sync_configurations` | Per-connection synchronization rules, auto-creation flags, conflict policies |
| `active_directory_objects` | Staged directory objects (users, computers, groups) with GUIDs, attributes, and match links |
| `active_directory_sync_runs` | Sync run telemetry, object counters, dry-run flags, duration, and error summaries |
| `active_directory_match_candidates` | Match candidate records linking directory objects to HIOP users/devices with scores and evidence |


Device retirement and hierarchy/user deactivation are soft lifecycle changes. Ticket deletion is a real deletion and therefore remains administrator-only. Device-linked ticket references use `ON DELETE SET NULL`; hierarchy references also preserve device rows.

## Integrity and indexes

- Database uniqueness protects device asset tags, serial numbers, MAC addresses, usernames, emails, hierarchy names, and non-null network-zone CIDRs.
- Foreign keys connect scans/alerts/tickets to devices and tickets to users.
- Operational indexes cover hostname, device IP, ticket status, active-alert chronology, audit chronology, scan chronology, per-device scan chronology, and hierarchy relationships.
- Discovery partial unique indexes prevent duplicates using MAC, approved inventory device, IP plus hostname, then IP-only identity tiers. Checks constrain state values, counters, confidence, and response/duration values.
- Import checks constrain session and row states and keep counters non-negative and processed rows within the declared total. A unique session/source-row boundary supports idempotent staging while duplicate asset tags, MACs, serials, and network identities remain reviewable. Lookup indexes cover session, identifiers, hostname, IP, and validation state.
- Matching candidates require exactly one typed target, bound scores, unique source/target pairs, and indexed session/rank/review lookups. Location suggestions are unique per staged row and reference existing hierarchy records without creating them.
- Pydantic validates enums, IP/MAC syntax, pagination bounds, credentials, and request lengths before persistence.

## Migrations

Never use `Base.metadata.create_all()` as a production migration strategy. From `backend`:

```powershell
alembic current
alembic heads
alembic upgrade head
```

Take and verify a PostgreSQL backup before an upgrade. Apply migrations as a one-shot release step before starting the application. Do not run concurrent migration containers.

## Backup and recovery

Use the guarded scripts in `ops/` or standard `pg_dump`/`pg_restore`; keep encrypted backups off-host and outside source control. Recovery must restore into an isolated database first, apply the expected application version, run health and acceptance checks, and only then switch traffic. Full commands and drills are in `OPERATIONS.md`.

## Compatibility debt

`devices.status`, `devices.department`, and `devices.location` remain compatibility fields while clients migrate to separate lifecycle/network fields and normalized hierarchy IDs. Their future removal requires a planned migration and downstream compatibility review.
