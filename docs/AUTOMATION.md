# Automation engine

Epic 3A provides property-scoped workflow definitions, immutable versions, an
approved action catalogue, bounded structured conditions, deterministic
step/dependency plans, dry runs, approvals, and persisted execution lifecycle.
Definitions contain structured data only: no `eval`, executable plugins, shell
commands, arbitrary URLs, SQL, or dynamic module imports are supported.

Approved live runs execute only fixed in-process safe handlers (`noop` and
`record_event`). Unknown handlers, arbitrary code, and unapproved external side
effects are rejected. Versions use canonical JSON checksums, separate approval
when required, explicit enable/disable controls, idempotent runs, bounded retry
and timeout handling, verification summaries, cancellation, and fixed
compensation handlers.

## Scheduled and internal-event orchestration

Epic 3B implements scheduled and trusted internal-event orchestration on the same
approved, version-pinned execution engine. Events are restricted to a fixed
catalogue with bounded, secret-rejecting payloads and property scope. Trigger
subscriptions support allowlisted structured filters, conditions, safe input
mapping, correlation/deduplication windows, cooldowns, per-window run limits,
bounded delays, approval gates, and maintenance/blackout behavior. External
webhooks and arbitrary event types are not exposed.

Schedules support bounded recurring intervals and one-time execution. They are
disabled by default, pin an exact approved workflow version, use deterministic
APScheduler job IDs, prevent overlapping runs, and honor maximum-run,
maintenance, blackout, and approval policies. Startup reconciliation creates,
updates, or removes jobs from persisted state without duplication. Stale
pending/running runs are recovered as failed, and shutdown uses the shared
scheduler lifecycle.

Daily, weekly, and monthly schedules use validated IANA timezones and structured
calendar fields rather than raw cron strings. Start/end windows, jitter, bounded
monthly dates, and exact workflow-version references are persisted. Editing a
trigger creates a checksum-backed revision and disables it for explicit review.

## Event safeguards

The internal catalogue includes controlled alert, ticket, device, Discovery,
directory, SNMP, topology, analytics, hospitality-service, configuration,
compliance, and maintenance events. The authenticated Admin event endpoint is an
internal integration and testing surface, not a public webhook. Replay-safe
event IDs, SHA-256 deduplication keys, correlation windows, cooldowns, and storm
limits prevent repeated execution.

Failed filters, inactive workflows, maintenance windows, blackouts, and run
limits produce stored suppression reasons. Delayed executions use bounded
one-time jobs. Approval-required triggers and schedules create waiting runs and
human approval requests rather than executing automatically. Approved runs then
use the same retry, timeout, verification, cancellation, and compensation
processing as manual runs.

Internal domain services can publish through the transactional outbox. A stable
single-instance job processes bounded batches, retries with bounded backoff, and
moves repeatedly failing records to a reviewable dead-letter state. Admins can
retry or ignore dead letters; neither action bypasses current validation,
approval, or idempotency controls.

Correlation groups collect a bounded number of events with the same
subscription/property/correlation key and trigger only after the configured
threshold. Evidence keeps contributing event IDs without claiming root cause.
A registered recovery event cancels a still-delayed matching trigger, records
the cancellation, and never cancels an already-running workflow.

Retention preview and confirmed cleanup remove only old published outbox rows in
bounded batches. Trigger-linked event evidence, dead letters, workflow runs,
approvals, and audit history remain protected. Summary reporting exposes
schedules, subscriptions, events, trigger/suppression counts, and dead letters.

## Frontend and operations

The protected `/automation` workspace lists property-visible workflows,
versions, runs, pending approvals, subscriptions, schedules, and scheduler
health. Admins can create disabled-by-default schedules and approval-gated
triggers through the typed client. Readers receive property-scoped records.
WebSocket payloads contain identifiers, state, and counts instead of workflow
inputs or outputs; grouped notifications use existing notification settings.

The UI never accepts arbitrary action code, scripts, URLs, SQL, credentials,
raw executable expressions, public webhook URLs, or unreviewed destructive
actions.

## Incident orchestration integration

Operational playbooks pin approved versions and reference only allowlisted
automation actions. Incident runs create human tasks, checklists, approvals,
decisions, evidence requirements, and verification gates. High-risk
recommendations require administrator approval and never execute configuration
restore or arbitrary device actions. Recovery stays blocked until human
verification, and closure remains governed by the incident record. See
`docs/INCIDENT_MANAGEMENT.md`.
