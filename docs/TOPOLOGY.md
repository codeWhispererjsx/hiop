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

## Epic 5C inference engine

`TopologyInferenceService` turns reviewed inventory, Discovery, SNMP target/interface, LLDP/CDP, manual-link, segment, and historical evidence into a normalized graph. Runs are bounded by configured node/link limits and have checksums before and after inference. The service never creates or merges official inventory devices.

### Confidence model and evidence fusion

Every physical link receives a fresh 0–100 score and a `TopologyConfidenceHistory` record. Contributions include base neighbor evidence, bidirectional sightings, LLDP/CDP agreement, resolved interface pairs, linked inventory/SNMP targets, historical stability, and confirmed manual authority. Missing evidence and explicit conflicts reduce the score. The current contribution breakdown is also stored in link metadata; existing `TopologyLinkEvidence` rows are retained.

### Canonical links and duplicate nodes

Direction-independent endpoint/interface keys identify duplicate physical links. A confirmed manual link wins; otherwise confirmation and confidence select the canonical link. Provisional duplicates are suppressed, their evidence is moved to the canonical link, timestamps are widened, merge IDs are preserved, and a topology change/audit record is created. Multiple confirmed manual links become a conflict instead of being merged.

Nodes sharing a stable neighbor identity or management IP produce `merge_nodes` review items. Official inventory nodes are never automatically merged. Approval can rewire topology links and hide only the reviewed provisional duplicate; contradictory official device identities are rejected.

### Conflicts and review workflow

The conflict engine records multiple active peers on one interface, one management IP mapped to multiple nodes, duplicate confirmed manual links, and manual/inferred disagreement. Each conflict has severity, evidence, confidence, related entities, and a suggested resolution.

Review items are `pending`, `approved`, `rejected`, or `ignored`. Supported proposals include provisional-node merges, layer assignments, and inferred dependencies. Approval revalidates topology boundaries, identity safeguards, and dependency cycles before applying changes. Resolution is audited and broadcast without sending the full graph.

### Layers, link classification, and dependencies

Layer suggestions use existing manual roles/layers, device type, naming hints, and graph degree to classify core, distribution, access, endpoint, service, external, or unknown nodes. Existing manual layers are never overwritten without review. Links receive explainable uplink, downlink, access, trunk, wireless, or unknown metadata.

Network dependencies follow higher-to-lower trusted layers over active physical links. High-confidence, cycle-safe dependencies are marked `source_type=inferred` and `is_manual=false`; lower-confidence proposals enter review.

### Path reconstruction and comparison

`path-analysis` returns bounded, cycle-safe physical, dependency, layer-aware, or combined path options ordered by hop count. `impact-analysis` combines existing dependency impact with improved orphan/island/missing-uplink analysis. Snapshot comparison reports added/removed nodes and links plus parent and layer changes. Snapshot dependency/segment fidelity is limited to data retained by the Epic 5A snapshot format.

### Epic 5C limitations

Inference has no bridge forwarding database, MAC learning, STP, scheduled execution, live animation, alerts, interactive frontend, or device configuration. Graph-derived dependency and layer results are recommendations, not proof of cabling or service criticality. Real hotel topology execution remains prohibited without explicit approval. The recommended next epic is Epic 5D: an administrator-reviewed interactive topology frontend over these bounded APIs.

## Epic 5D interactive frontend

The authenticated **Network Topology** workspace is available at `/topology`. React Flow is the single graph renderer because it provides TypeScript-native custom nodes/edges, visible-element rendering, zoom/pan, dragging, selection, controls, and a minimap while fitting the existing React/Vite architecture.

The landing page uses real topology, statistics, inference, conflict, and orphan APIs. Administrators can create topologies, preview bootstrap, create snapshots, and open review workflows; technicians receive bounded read-only operational views.

### Map, search, filters, and layouts

- Node cards expose identity, status text, role/layer, management address, provisional confidence, and conflict state. Icon/text accompany color.
- Confirmed links use stronger strokes, inferred links are dashed, and selected paths are highlighted without claiming packet-routing certainty.
- Search and URL-backed filters narrow identity, status, device type, layer, link type, hidden state, confidence, and orphan state.
- Layered, force-directed, grid, radial, and saved-manual layouts are available. Automatic layouts do not overwrite saved positions; layout persistence is explicit and backend-bounded.
- Node/link drawers expose only authorized API data. Link confirmation/suppression/restoration, inference, snapshots, and manual link creation are administrator-only.
- Manual links reject self-links client-side and retain backend interface ownership, topology isolation, duplicate, and cycle safeguards.

### Path, impact, review, and snapshots

Path mode requests bounded physical, dependency, layer-aware, or combined alternatives and provides an ordered accessible summary. Results are modeled evidence, not guaranteed packet routes. Impact mode highlights **potentially affected** downstream nodes and repeats backend confidence warnings.

Conflict and inference pages preserve evidence, projected impact, and graph context before approval, rejection, or ignore. Snapshot graphs are immutable/read-only, have no live overlays, and cannot persist dragging. Snapshot-to-current comparison covers added/removed nodes and links plus layer and parent changes. A bounded tabular change timeline is also available.

### Live updates, performance, accessibility, and themes

Topology events use the existing authenticated WebSocket. Major changes trigger one debounced graph refresh; disconnects retain manual refresh/polling fallback. Large bounded graphs display a limit warning, render visible elements only, and preserve a table fallback.

The toolbar is keyboard accessible, custom nodes are focusable, status is not color-only, analyses have list/table alternatives, drawers become full-width on small screens, and reduced-motion preferences disable edge animation. Existing HIOP theme variables support dark and light modes.

Troubleshooting: verify FastAPI and the `/api/v1` proxy for backend errors; bootstrap/add reviewed nodes for an empty map; reload before retrying a rejected layout write; and remember that “no modeled path” does not prove network unreachability.

Known limitations: advanced building/floor container grouping requires display-name/group data not yet present in the graph schema. Link metric overlays are withheld because the graph does not yet return authoritative directional metric summaries. Non-backend graph filters operate on the already bounded response.
