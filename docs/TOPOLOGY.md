# Network Topology Foundation

Epic 5A adds a relational, administrator-managed graph foundation for HIOP. It represents devices, discovery records, SNMP targets, interfaces, segments, dependencies, evidence, layouts, snapshots, and reviewed changes without performing LLDP/CDP collection, automatic inference, scheduled refresh, topology alerting, or live network queries.

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

## Known limitations and next epic

Epic 5A has no interactive map, LLDP/CDP collection, inference, scheduled refresh, alerts, traps, or automatic device mutation. Impact analysis is structural, not proof of physical dependency. The recommended next epic is reviewed topology discovery/inference using approved SNMP neighbor evidence.
