# Incident management foundation

HIOP Epic 3C adds property-scoped operational incidents, source links,
participants, human tasks, and append-only timeline entries. Incident status
transitions are controlled by an explicit state machine; arbitrary status changes
are rejected. The APIs are designed for human-in-the-loop orchestration and do
not perform autonomous remediation, configuration restore, external webhooks, or
third-party incident integrations.
