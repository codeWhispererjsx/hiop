# HIOP 2.0.0-dev database

## Epic 3A automation execution

Migrations `c9d0e1f2a3b4` and `f2a3b4c5d6e7` add workflow definitions and
versions, the controlled action catalogue, dry runs, workflow runs, immutable
version steps, same-version dependencies, step runs, and human approval requests.
Unique workflow/step keys and a database self-dependency constraint reinforce the
service-level cycle and ownership validation. Migration `f3a4b5c6d7e9` seeds
only the two fixed safe handlers (`noop` and `record_event`).

## Epic 3B automation orchestration

Migration `f4b5c6d7e8f9` expands the additive automation event, trigger, and
schedule tables with structured filter/condition/input-mapping storage,
correlation and storm controls, delay and approval policies, maintenance and
blackout windows, safe event metadata, processing timestamps, and schedule run
status. Trigger execution rows preserve deduplication and suppression history.
No existing workflow, version, or run records are rewritten.

Migration `f5c6d7e8f9a0` completes orchestration persistence with transactional
event outbox, correlation-group, and immutable trigger-revision tables. It adds
recovery/correlation controls to subscriptions and structured calendar,
timezone, start/end, jitter, and blackout controls to schedules. Status/time
indexes support bounded outbox, dead-letter, correlation-expiry, revision, and
scheduler queries.

## Epic 6B analytics persistence

Migration `c8e6b4d2a701` adds schedule configuration, processing checkpoints, retention policies, and run progress/checkpoint fields without changing operational source records.

## Topology foundation

Migration `d0c2bcea6dda` adds topology definitions, nodes, links/evidence, segments/memberships, dependencies, snapshots, changes, positions, and groups. It is additive.

Migration `a7c3e5f90124` adds AD checkpoints, run progress/results/cancellation, missing markers, field-level change history, and sanitized sync errors. Missing staged objects are retained.

Migration `b8d4f6a10235` expands AD candidates for Discovery, Department, and role suggestions; adds source/target versions; and creates record-link, department-map, OU-map, group-role-map, and reconciliation-result tables. Link uniqueness is enforced in PostgreSQL.

PostgreSQL is the only supported production database. SQLAlchemy models define the runtime mapping and Alembic is the sole schema-change mechanism. The current head is `b8d4f6a10235`.

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
## SNMP foundation

Epic 4A adds nine additive PostgreSQL tables: `snmp_credentials`, `snmp_targets`, `snmp_device_profiles`, `snmp_oid_definitions`, `snmp_polling_configurations`, `snmp_poll_runs`, `snmp_metrics`, `snmp_interfaces`, and `snmp_discovery_candidates`. Secrets are ciphertext-only. Endpoint/context and target/interface identities are unique, observation queries are indexed by target/key/time, and all inventory/discovery/hierarchy links use non-destructive `SET NULL` behavior where appropriate.
# SNMP Epic 4C additions

Migration `e3a7c9d5b102` adds `snmp_match_candidates`, `snmp_device_links`, `snmp_interface_changes`, and `snmp_state_changes`. It extends interfaces with missing/grace/connector state and metrics with a bounded quality reason plus an interface/key/time index. All changes are additive and downgrade removes only Epic 4C structures.
## SNMP Epic 4E

Migration `f5e4d3c2b1a0` adds schedules, jitter, maintenance/recovery metadata, interface monitoring policy, and indexed
`snmp_alert_rules`/`snmp_alert_events`. It is additive and includes a downgrade.
## Epic 5B neighbor evidence

Migration `e1d3f5a7b902_add_topology_neighbor_discovery.py` adds `topology_neighbor_collection_runs`, deduplicated `topology_neighbor_observations`, and reviewed `topology_neighbor_candidates`. Indexes cover topology/status/time, target/protocol, remote identity, management address, and review queues. The additive downgrade removes only these three Epic 5B tables.

## Epic 5C inference and review

Migration `f2e4a6c8d013_add_topology_inference.py` adds:

- `topology_inference_runs` for bounded execution, counts, summaries, and graph checksums.
- `topology_conflicts` for severity, evidence, suggested resolution, and lifecycle.
- `topology_review_items` for proposed changes, impact, confidence, and administrator resolution.
- `topology_confidence_history` for per-link score history and contribution breakdown.

All changes are additive. Owning topology deletion cascades inference-only rows; optional run/reviewer references use `SET NULL`. Graph and inventory tables are not destructively altered by the migration.

## Epic 5E topology operations migration

Migration `fa6d8e1c4b20` adds `topology_schedule_configurations`, `topology_operational_runs`, `topology_alert_rules`, and `topology_alert_events`. It also adds protected/baseline flags to topology snapshots. Schedule topology IDs are unique; operational status/time and alert topology/open/time lookups are indexed. Downgrade removes only these additive objects and columns.

## Epic 6A analytics schema

Migration `b7d9e2f4a601` adds 12 tables: metric definitions, aggregates, availability, health scores/configurations, capacity policies/assessments, SLA definitions/measurements, reliability measurements, runs, and data quality. Metric/entity/bucket and entity/period uniqueness constraints provide idempotency. Entity UUIDs intentionally have no cascading source foreign key so historical analytics survive inventory retirement. Downgrade drops only analytics tables in dependency-safe order.
# Hospitality foundation (v3)

Migration `f3a4b5c6d7e8` creates `organizations`, extends `properties` with organization and hospitality attributes, and adds nullable `devices.property_id`. Existing records remain functional without an organization/property assignment. Archive operations are status updates, not destructive deletes.
## Incident management tables

Migration `f6d7e8f9a0b1` expands `operational_incidents` and its source,
participant, task, and timeline tables without deleting data. It adds
operational playbooks/versions/steps, playbook and step runs, checklists,
evidence, decisions, communications/templates, escalation rules/history,
response targets, impact assessments, remediation recommendations, cause
assessments, post-incident reviews, and follow-up actions. Property, status,
severity, due-time, source, and chronology indexes bound operational queries.
# Epic 3D schema

Migration `a8b9c0d1e2f3` adds the knowledge article, revision, approval, category, tag, attachment, comment, rating, favorite and view tables; runbook version/execution tables; SOP/review/acknowledgement tables; service catalog/support/dependency tables; document version/approval/link tables; troubleshooting/known-issue tables; checklist template/execution tables; relationship validation and search-stat tables. Changes are additive, UUID based, property aware, indexed, and reversible.
