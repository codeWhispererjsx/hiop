# HIOP V1/V2 focused product completion

HIOP exposes only Overview, Discover, Monitor, Manage, Automate, Maintain, and Administration.

## Completed workflow

- Private-network quick scans use deterministic discovery and preserve evidence.
- Discovery results can be reviewed and approved into managed inventory.
- Approval prevents duplicate IP/MAC records and writes an audit event.
- Missing values remain `Unknown`; an absent MAC address is stored as `NULL`.
- Overview combines inventory, availability, pending discovery, incidents, and alerts.
- Monitor provides live reachability, response time, persisted history, and alert context.
- Manage provides searchable, filterable, editable inventory and recoverable retirement.
- Automate is limited to scan/monitor schedules, email notifications, and offline incidents.
- Maintain provides incident creation, device association, resolution, and closure.
- Administration retains users, roles, hierarchy, network ranges, discovery settings, and encrypted discovery credential APIs.

## Discovery intelligence retained for V2

The modular engine retains DNS, NetBIOS, SNMP, credentialed host, service fingerprint,
evidence, confidence, history, duplicate correlation, and relationship-ready topology
collectors. Credentialed stages remain opt-in and no vulnerability scanning is performed.

## Verification

- V2F preserved all 8 existing inventory UUIDs and approval states.
- All 8 inventory devices are linked to V2 discovery intelligence without creating a replacement Device.
- 667 monitoring observations and the existing device-linked incident have zero orphan references.
- Duplicate scan: zero MAC, hostname, or IP duplicate groups; zero ambiguous matches.
- Alembic remains at the single merge head `9f1a2b3c4d70`; V2F requires no migration.
- Full automated and authenticated browser results are recorded in `HIOP_V2F_RECONCILIATION_REPORT.md`.

## Known limitations

- CPU, memory, disk, and interface metrics require reachable devices with configured SNMP or host credentials.
- LLDP/CDP relationships depend on supported equipment and read-only SNMP access.
- Historical V1 Device columns do not all have field-level provenance. V2F preserves populated inventory values and reports conflicts instead of guessing their source.
