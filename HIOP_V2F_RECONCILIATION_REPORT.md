# HIOP V2F Reconciliation Report

Date: 2026-08-09  
Scope: V1 inventory continuity into V2 discovery intelligence  
Result: **Passed**

## Summary

| Measure | Result |
|---|---:|
| Total existing V1 devices | 8 |
| Preserved | 8 |
| Enriched | 0 |
| Partially enriched | 8 |
| Unresolved | 0 |
| Potential duplicates | 0 |
| Requires review | 0 |
| Errors | 0 |

No Device record was deleted, recreated, merged, or demoted. All eight UUIDs,
approval states, inventory attributes, and relationship targets remained unchanged.
The reconciliation run found that all existing devices were already represented by
V2 discovery records, so it created zero new links.

## Relationship integrity

- Monitoring observations inspected: 667
- Monitoring observations with a missing Device: 0
- Incidents linked to a Device: 1
- Linked incidents with a missing Device: 0
- Audit records present before the V2F audit event: 50
- Unvalidated PostgreSQL foreign keys: 0

The V2F reconciliation itself added one audit event and did not rewrite historical
audit entries.

## Duplicate scan

- Duplicate normalized MAC groups: 0
- Duplicate normalized hostname groups: 0
- Duplicate IP groups: 0
- Ambiguous discovery-to-inventory matches: 0

IP-only observations are never automatically linked. They are reported for review.
MAC is preferred, followed by stable inventory linkage and hostname. Repeated runs
are idempotent.

## Preserved device IDs

| Device UUID | Hostname | IP | Approval |
|---|---|---|---|
| `846f8e08-a9bd-419f-b740-dd310d90f497` | heloshadtsc1821 | 10.50.21.124 | Active |
| `b54c2bd8-77c1-4692-94dc-0c25c5b0c936` | heloshadtfo0001 | 10.50.21.132 | Active |
| `23be35e6-bcb4-47ca-b519-a986689e0c96` | heloshadtac1322 | 10.50.21.111 | Active |
| `1bb506ec-2945-45cd-a696-b329b691a5a7` | heloshaltit1357 | 10.50.21.61 | Active |
| `92c9b15f-c6bd-40a8-aed2-5dbf6ef7ee68` | wskdsd-ekabo | 10.50.21.245 | Active |
| `dc6e6448-f663-4e7b-9258-e968f9887481` | heloshaposlob01 | 10.50.21.225 | Active |
| `94bfc382-2736-4bb2-9ebd-1f30ae34dbaf` | heloshaposbqt01 | 10.50.21.234 | Active |
| `ad31f456-ac36-41df-a49b-4cbbcc46ffd0` | heloshaposeka01 | 10.50.21.218 | Active |

## Safe reconciliation behavior

Administrator APIs:

- `GET /api/v1/discovery-intelligence/reconciliation/report`
- `POST /api/v1/discovery-intelligence/reconciliation/run`

The report includes before/after comparisons. A run may only attach an unlinked
discovery record to one unambiguous existing Device. It cannot update Device
department, location, hostname, type, asset data, UUID, or approval state. Conflicting
automatic values are reported rather than applied.

## Limitations

- The V1 schema does not record field-level provenance for every historical Device
  value. V2F therefore treats populated non-placeholder inventory values as
  authoritative and does not overwrite any Device field.
- All eight devices are partially enriched because live SNMP and Active Directory
  endpoints were not configured. Provider failure does not affect approval or
  monitoring validity.
- Counts are a point-in-time checkpoint; monitoring observations continue to grow.

## Authenticated browser validation

- Signed in with the existing administrator session.
- Manage showed the same 8 approved devices before and after discovery.
- A bounded scan of `10.50.21.0/24` completed successfully and found 81 current devices.
- The approved inventory count remained 8; no duplicate Device was created.
- Device `94bfc382-2736-4bb2-9ebd-1f30ae34dbaf` retained its UUID, hostname,
  IP, MAC, Active approval state, V2 evidence, and historical scan records.
- Incident `INC-20260809-1031BA` remained linked to that same Device UUID.
- Monitor showed all 8 Devices and their persisted history. The final database check
  contained 683 monitoring observations with zero orphans.
