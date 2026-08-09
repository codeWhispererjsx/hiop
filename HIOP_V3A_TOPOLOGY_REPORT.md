# HIOP V3A — Network Topology

## Scope

V3A adds a read-only topology experience over the existing V1/V2 inventory. It does
not create a second device registry and does not change network infrastructure.

## Relationship sources

- LLDP and CDP are collected through the existing bounded, read-only SNMP client.
- BRIDGE-MIB MAC-table addresses may associate a known inventory MAC with one
  unambiguous linked network device.
- Unknown identities remain unresolved evidence and never create a Device row.
- IP address alone never creates a relationship.

## Confidence

Relationship creation requires at least 60 points of deterministic evidence.
Existing inventory identity contributes 25 points; chassis ID 35; management
address 20; system name 10; remote port 10; known local interface 10; existing
SNMP target 10; and bidirectional observation 20. Scores are capped at 100.
Each conflict subtracts 10 points up to 30. Conflicting evidence does not create an
automatic relationship. UI bands are Low below 60, Medium from 60–79, and High
from 80–100.

MAC-table associations are Medium confidence (70) only when the MAC resolves to
exactly one existing inventory device and is observed on exactly one linked SNMP
target during the refresh. Ambiguous observations remain unresolved.

## Staleness

Relationships are retained historically. A relationship that has not been verified
for 24 hours is marked stale; it is not deleted. A later matching observation returns
the same relationship to current state.

## API

- `GET /api/v1/topology`
- `POST /api/v1/topology/refresh` (administrator only)
- `GET /api/v1/topology/relationships/{relationship_id}`
- `GET /api/v1/topology/devices/{device_id}/neighbors`
- `GET /api/v1/topology/stats`

## Database

V3A reuses the already-applied topology foundation and neighbor-evidence migrations
(`d0c2bcea6dda` and `e1d3f5a7b902`). No new migration is required. All displayed
nodes must reference existing `devices.id` values.

## Explicit exclusions

No topology editor, VLAN or port configuration, scheduled topology collection,
alerts, impact/dependency analysis, automated remediation, CMDB, procurement,
vendor management, AI, or later V3 work is enabled by V3A.

## Verification — 2026-08-09

- Backend: 155 tests passed.
- Frontend: 28 tests passed.
- Frontend lint: passed.
- Production build: passed.
- Alembic: database and code are both at `9f1a2b3c4d70` (head).
- Current data: 8 inventory devices, 0 configured SNMP targets, 0 topology
  relationships, 0 invalid topology device references, and 0 invalid link references.
- Browser: updated Topology navigation was verified in the running authenticated UI.
  The session expired when opening the protected route, so authenticated refresh and
  detail interaction remain pending. No credentials were invented.
