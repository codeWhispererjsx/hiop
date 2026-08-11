# HIOP Version 3C — VLAN & Network Segmentation Intelligence

## Status

V3C STATUS: Complete

The implementation is a cached, read-only intelligence layer over the existing V2 device identities, V3A topology, and V3B switch-port associations. It exposes no VLAN, port, switch, router, or firewall configuration operation.

## Live database totals

- VLANs discovered: 0
- Subnets identified: 0
- Devices with VLAN information: 0
- Ports with VLAN information: 0
- Trunk ports: 0
- Multi-VLAN relationships: 0
- Stale VLAN relationships: 0
- Unknown VLAN relationships: 0
- Duplicates: 0

The zero totals are truthful: the current database contains no VLAN observations from a linked supported SNMP switch. HIOP does not fabricate demonstration VLANs or infer a subnet from a VLAN ID.

## Database migration

Migration `v3c8d0e2f4a6` is applied at Alembic head. It reuses `network_segments` and `topology_node_segments`, permits a VLAN to exist without an invented CIDR, adds status/gateway/observation timestamps, and adds `vlan_membership_observations` for evidence, confidence, current/stale state, and history. A partial unique index prevents duplicate VLAN IDs inside one topology.

## Services and API

`SegmentationService` and `VLANTableProvider` perform bounded read-only Q-BRIDGE-MIB collection, access/trunk/native/allowed membership interpretation, V3B endpoint/uplink correlation, confidence calculation, historical staling, and V3A graph enrichment. APIs provide VLAN lists/details, devices, interfaces, device VLAN information, subnets, statistics, and explicit administrator refresh. No SNMP SET or infrastructure write path exists.

## User interface

- `/segmentation` provides searchable VLAN/subnet/device/switch/port visibility and current membership details.
- Device details show VLAN, name, subnet, gateway, switch, port, mode, evidence, confidence, last verification, and preserved history.
- Switch details show observed VLANs.
- Existing topology relationship labels and details show VLAN information when evidence is available.
- Unknown and unavailable states remain explicit.

## Test results

- Backend: 169 passed
- Frontend: 36 passed
- Lint: passed
- Production build: passed
- Migration: `v3c8d0e2f4a6 (head)`

## Browser validation

Pending authenticated data validation. The running application redirected the fresh validation tab to sign-in and administrator credentials were not available to this task. The sign-in page rendered successfully. Automated API contracts, production build, migration, and database statistics were validated; positive switch/VLAN/device/trunk UI paths require a supported linked SNMP switch with VLAN evidence.

## Known limitations

- Standard Q-BRIDGE-MIB supplies VLAN and port membership but generally does not supply routed subnet/gateway data; those fields stay unknown unless a supported source explicitly supplies them.
- The live environment currently has no collected VLAN inventory, so positive live correlation and trunk examples cannot be demonstrated.
- Vendor-specific VLAN MIB extensions are not included in V3C.

## Not implemented

V3D, V3E, V3F, advanced monitoring, alerts/events, impact analysis, configuration management, VLAN changes, routing/firewall changes, remediation, CMDB, procurement, vendor/change/release management, multi-property expansion, and AI/AIOps.

## Git

- Commit: not created
- Pushed: No
