# Network Topology and Neighbor Evidence

Epic 5A adds the relational graph foundation. Epic 5B adds administrator-triggered, bounded LLDP/CDP collection and stages normalized observations, provisional nodes, provisional links, and explainable evidence. It does not perform final inference, automatically confirm links, create inventory devices, schedule collection, or expose arbitrary walks.

## Architecture

A `Topology` is a named graph with optional location or network-zone scope. `TopologyNode` uses at most one authoritative identity reference; virtual/manual nodes are permitted. `TopologyLink` connects two nodes and can reference SNMP interfaces. Evidence is bounded and stored separately.

Segments model CIDR/VLAN membership. Dependencies are directional and reject self-dependencies and cycles. Positions and groups remain separate from graph identity. Snapshots copy normalized state, while topology changes have explicit pending, confirmed, and ignored review states.

The service layer enforces identity consistency, topology boundaries, duplicate/self-link rules, dependency cycles, and traversal limits. Repositories contain persistence and pagination only.

## Sources, trust, and bootstrap

Supported sources are manual, inventory, discovery, SNMP, imported, inferred, and hybrid. Bootstrap uses approved inventory devices only and creates nodes only; it never fabricates links. Confidence is stored from 0–100 and manual review remains authoritative.

## API and permissions

The `/api/v1/topology` endpoints provide topology state, nodes, links, graph reads, bounded neighbors/components/path/impact analysis, segments, dependencies, layouts, snapshots, changes, statistics, orphans, and dry-run/confirmed bootstrap. Reads require authenticated admin/technician access; mutations require admin access.

## Security and performance

- No endpoint runs arbitrary graph code or network commands.
- Cross-topology references, contradictory identities, self-links, self-dependencies, invalid VLAN/CIDR/IP values, and dependency cycles are rejected.
- Metadata, pagination, graph output, and traversals are bounded.
- Audit and WebSocket events contain identifiers/counts rather than full infrastructure exports.
- Indexes cover graph, source, status, location, snapshot, and review paths.

## Operations

Run `alembic upgrade head` before enabling these APIs. Keep graph limits conservative, take snapshots before large restructuring, and back up topology tables together.

## LLDP/CDP collection architecture

The collection service uses the existing encrypted-credential `SecureSNMPClient`, authorized/ignored network ranges, SNMP operation locks, bounded bulk walks, safe errors, audit records, and summarized WebSocket events. SNMPv1 automatically uses ordinary WALK rather than BULK-WALK. `auto` mode selects LLDP and adds CDP only for an explicitly detected Cisco profile; administrators may select LLDP, CDP, or both.

Approved LLDP-MIB roots cover local chassis/system/port identity and remote chassis, port, system name/description, capabilities, and management address. Approved Cisco CDP cache roots cover address, version, device ID, device port, platform, capabilities, native VLAN, duplex, and local ifIndex. These constants are centralized in `topology_neighbor_parser.py`; callers cannot submit an OID.

## Observations, identity, and port resolution

`TopologyNeighborCollectionRun` records topology-specific lifecycle and bounded counts. `TopologyNeighborObservation` upserts the source target/protocol/local-port/remote-identity tuple and retains normalized evidence without raw PDUs. `TopologyNeighborCandidate` holds remote matching, confidence breakdown, conflicts, and review state.

Remote identity prefers normalized chassis ID, then management address, linked targets/devices, and finally conservative name/port evidence. System name alone remains weak. Local ports resolve by ifIndex, then a unique exact ifName/ifDescr/ifAlias. Ambiguous or missing ports remain unresolved and reduce confidence. Remote ports may remain unresolved.

## Candidate nodes, links, and confidence

Unmatched neighbors create topology-only provisional nodes; they never create `Device` rows. Links are physical, unconfirmed, and evidence-backed. Reverse observations are consolidated into the same relationship and add a bidirectional score bonus. Single-sided observations remain lower-confidence.

The explainable 0–100 score includes chassis ID, management address, system name, port evidence, resolved local interface, existing target linkage, and bidirectional evidence. Conflicts subtract points. Confirmed manual links have precedence and are never silently replaced.

## Conflicts, aging, dry runs, and operations

Complete successful runs increment unseen observation grace counters; partial or failed runs do not age observations. Observations become stale before missing. A returned observation is restored with a topology change record. Confirmed manual links are never removed by aging.

Admins can collect one target or a bounded list, list/cancel runs, inspect results/observations/candidates, review matches, and confirm/reject/suppress provisional links. Technicians retain read-only access. Dry runs parse and summarize approved protocol data but do not persist observations, nodes, links, aging, or topology changes.

Troubleshooting should begin with approved Discovery ranges, the existing SNMP target test, device LLDP/CDP configuration, and synchronized SNMP interfaces. Partial runs preserve old evidence. No raw PDU, arbitrary OID, credential, or full low-level error is exposed.

## Known limitations and next epic

Epic 5B has no bridge/MAC tables, STP, final inference, interactive map, scheduled refresh, alerts, traps, or automatic device mutation. Management-address extraction depends on agent encoding. Multi-context reconciliation remains conservative. Impact analysis is structural, not proof of physical dependency. The recommended next epic is Epic 5C: reviewed inference using neighbor evidence plus separately approved bridge/STP sources.
