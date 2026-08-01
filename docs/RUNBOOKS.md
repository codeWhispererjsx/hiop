# Operational Runbooks

Runbooks define reviewed human procedures with objective, prerequisites, duration, safety notes, permissions, rollback steps, success criteria, and validation checklists. Draft versions contain ordered manual, checklist, verification, decision, or communication steps.

Approved versions are immutable and checksum protected. Publishing selects the current version. Execution copies the version's steps into an execution record, validates declared parameters, and advances only through ordered manual completion. Evidence and verification requirements are enforced per step.

Executions can link to incidents, tickets, and approved automation workflow runs. They preserve notes, evidence references, actor, timestamps, and completion state. The implementation does not execute shell commands, arbitrary code, external webhooks, or autonomous remediation.

Use the Knowledge > Runbooks workspace to build a version, submit it for review, approve it, start an execution, and complete its steps. Property access and contributor/publisher permissions are checked by every backend operation.
