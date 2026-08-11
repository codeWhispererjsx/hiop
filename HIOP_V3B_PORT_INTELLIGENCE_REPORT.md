# HIOP V3B — Switch & Port Intelligence

## Scope

V3B extends the existing V3A topology and V2 identity model with cached, read-only interface and bridge MAC-table observations. It does not create devices, a second graph, VLAN management, monitoring, alerts, impact analysis, CMDB behavior, or infrastructure configuration.

## Data model

- Existing `snmp_interfaces` records remain authoritative for interface identity, description, administrative/operational status, speed, MAC, and observation times.
- `snmp_interfaces.duplex` records duplex when a supported read-only source provides it.
- `port_device_associations` stores current and historical interface/MAC/device associations with existing device foreign keys, evidence, confidence, first/last observation, current state, and stale time.
- Existing `topology_links.source_interface_id` / `target_interface_id` are populated when a port association has sufficient evidence.

## Services and APIs

`PortIntelligenceService` performs bounded BRIDGE-MIB collection, bridge-port to interface-index mapping, V2 MAC identity correlation, LLDP/CDP uplink recognition, explainable confidence, idempotent association updates, move/stale handling, and cached response assembly.

Read APIs:

- `GET /api/v1/port-intelligence/devices/{device_id}/connection`
- `GET /api/v1/port-intelligence/switches/{device_id}/interfaces`
- `GET /api/v1/port-intelligence/interfaces/{interface_id}`
- `GET /api/v1/port-intelligence/stats`

Administrator-triggered, infrastructure-read-only refresh:

- `POST /api/v1/port-intelligence/switches/{device_id}/refresh`

No network write API or SNMP SET operation exists.

## User interface

- Existing device details show switch, port, separate interface description, admin/operational state, speed, duplex, verification time, evidence, confidence, and preserved stale-history count.
- Existing switch device details show a searchable/filterable interface table and truthful known, multiple, uplink, and unknown endpoint states.
- Existing V3A topology edges and relationship details display the port when available.

## Verification

- Backend: 164 passed.
- Frontend: 33 passed.
- ESLint: passed.
- TypeScript/Vite production build: passed.

Browser validation depends on configured linked SNMP targets and available interface/MAC-table evidence. Unknown or unsupported data remains explicitly unknown.
