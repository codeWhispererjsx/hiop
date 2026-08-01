# Enterprise Change Management

HIOP Epic 4 adds a property-aware, deterministic request-for-change (RFC) system. It is additive to the earlier configuration-restore change records and does not execute arbitrary code or make autonomous production changes.

## Lifecycle and controls

RFCs use the controlled lifecycle `draft → submitted → technical_review → cab_review → approved → scheduled → in_progress → implemented → verified → closed`, with explicit cancellation and failure paths. Submission requires business and technical justification plus implementation, test, validation, communication, and backout plans. Technical approval is required before CAB review. All required approvals must be accepted before approval, and a scheduled RFC must have a valid interval inside its approved maintenance window when one is selected.

Execution is created only from a scheduled RFC. Ordered tasks become manual checkpoints, evidence is recorded separately, verification is required before closure, and rollback is a distinct request/approval/execution flow. Status transitions, approvals, revisions, evidence, communications, and rollback actions are audited.

## Permissions and property scope

- Admin/Superadmin: approve, manage CAB, approve windows, and authorize rollback.
- Technician: create and update scoped RFCs and perform permitted operator actions.
- Viewer: read-only access to records in authorized properties.

The backend is authoritative. Corporate records with no property can be read according to role policy; property-bound records require property access.

## APIs and UI

The REST surface is under `/api/v1/changes`. It includes RFCs, lifecycle actions, approvals, tasks, revisions, attachments, comments, risk, relationships, execution, rollback, CAB, maintenance, releases, communication, audit, dashboards, and bounded formula-safe report exports. The frontend workspace is `/changes` with RFC builder/detail, approval, CAB, risk, maintenance, execution, release, timeline, report, and audit sections.

## Operational safeguards

Attachments are bounded and filenames are normalized. Risk factors are fixed integers from 0–5. Public action execution, automatic approvals, arbitrary scripts, and AI decisions do not exist. WebSocket events contain identifiers and summaries, not attachment content or secrets. Eight stable shared-scheduler jobs handle reminders, stale drafts, conflicts, release reminders, risk refresh, and internal calendar reconciliation.

## Known limitations

Email delivery depends on configured HIOP notification transport. External calendar, project, vendor, contract, and deployment-system adapters remain integration points; their relationships are represented without automatic external mutation. Binary attachment storage uses the deployment's configured storage policy.
