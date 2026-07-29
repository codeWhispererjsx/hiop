# Automation engine

Epic 3A provides property-scoped workflow definitions, immutable version
metadata, an approved action catalogue, structured condition evaluation, dry-run
records, and manual-run lifecycle storage. Workflow definitions contain bounded
structured data only: no `eval`, executable plugins, shell commands, arbitrary
URLs, or dynamic module imports are supported.

Automatic schedules, event triggers, autonomous remediation, and infrastructure
changes remain constrained. The dry-run API validates graph structure, action
references, and bounded execution paths. Approved live runs execute only explicit
in-process safe handlers (`noop` and `record_event`); unknown handlers, shell
commands, arbitrary code, and unapproved external side effects are rejected.

Workflow versions use canonical JSON checksums, separate approval when required,
explicit enable/disable controls, idempotent manual runs, run detail/cancellation,
and summarized audit records. Scheduled and event-triggered orchestration remains
the responsibility of Epic 3B.

Epic 3B adds an internal-event and schedule foundation. Events are restricted to
an allowlisted catalogue with bounded safe payloads and property scope. Trigger
subscriptions store cooldown and deduplication controls. Schedules are disabled
by default and reference exact workflow versions; external webhooks, broker
consumers, and autonomous workflow execution remain disabled.

## Execution lifecycle

Administrators create a draft workflow and immutable version, add bounded steps
and same-version dependencies, validate the graph, obtain a separate approval
where required, and explicitly enable it. Execution plans use deterministic
topological ordering and reject cycles, self-dependencies, unknown steps, disabled
dependencies, excessive graph sizes, and unknown handlers.

Manual runs support dry-run simulation, idempotency keys, stored step runs,
bounded retries, per-step timeouts, cancellation, approval checkpoints,
verification summaries, and fixed compensation handlers. A requester cannot
approve their own version or execution checkpoint. WebSocket events contain IDs,
states, and counts rather than workflow inputs or outputs. Email notifications
respect the existing notification settings.

## Frontend

The protected `/automation` workspace lists property-visible workflows, immutable
versions, recent runs, and pending approvals, and provides a safe workflow-creation
foundation backed by the typed API client. It does not expose arbitrary action
code, scripts, URLs, SQL, credentials, or raw executable expressions.
