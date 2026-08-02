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

- Alembic upgraded through `4e5f6a7b8c92`.
- Backend: 93 tests passed.
- Frontend: 17 tests passed; lint and production build passed.
- Browser: login rendered at `http://localhost:5173/login` with no console errors.

## Known limitations

- A signed-in browser acceptance pass requires a valid administrator account supplied by the deployment.
- CPU, memory, disk, and interface metrics require reachable devices with configured SNMP or host credentials.
- LLDP/CDP relationships depend on supported equipment and read-only SNMP access.
