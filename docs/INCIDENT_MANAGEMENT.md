# Incident management

HIOP v3 Epic 3C provides a property-scoped, human-controlled incident command
system. The incident is the authoritative operational record; automation runs
may support it, but never replace its state, people, decisions, evidence,
communications, recovery verification, or closure history.

## Architecture and lifecycle

Approved internal events or a manual declaration create an incident. Similar
open incidents are shown before creation and a correlation key prevents
duplicate declarations. Sources remain independent; linking an alert or ticket
never silently resolves it.

The controlled lifecycle is `detected → declared → acknowledged → investigating
→ contained → mitigating → monitoring → recovered → resolved → closed`.
Cancellation, reviewed duplicate/merge handling, and permission-protected
reopening are explicit branches. Arbitrary state mutation is rejected. Severity
and priority remain separate. Guest, revenue, security, operational, and
life-safety impact retain `unknown`; HIOP never fabricates impact claims.

## Participants, tasks, checklists, and decisions

Incident roles include commander, technical lead, communications lead, scribe,
service owner, property administrators, engineers, security representatives,
approvers, and observers. Every participant must have property access. Only one
active commander is allowed.

Tasks have controlled start, block, complete, verify, reassign, overdue, and
cancel states. Required checklist items need a reason and elevated permission to
skip; evidence-required items cannot complete without evidence. Decisions
contain fixed options and rationale, never executable consequences.

## Operational playbooks

Playbooks are property-scoped definitions with immutable approved versions.
Versions use structured JSON, a canonical SHA-256 checksum, bounded size, and
ordered phase steps. Supported steps are human tasks, checklists, approved
automation actions, approvals, decisions, communications, evidence collection,
verification, waits, escalation, and terminal steps. There is no code editor,
shell/script execution, arbitrary URL, external webhook, or dynamic plugin.

Validation checks phases, step types, required roles, evidence and verification,
registered action references, risk approvals, bounded structure, and prohibited
fields. High/critical incidents require a commander. A run materializes step
runs, tasks, and checklist items and waits at human or approval checkpoints.
Approval checkpoints require an explicit approved/rejected outcome. Failed and
timed-out steps may be retried only within the immutable version's retry limit.
The overdue-step scheduler records a safe timeout and stops the run for review;
it never retries silently. An administrator may invoke a versioned compensation
action only when that handler is in the fixed safe-action catalogue.

## Communications, escalation, and SLA

Communications use property-scoped approved templates. Variables are allowlisted
and cannot traverse objects or execute expressions. Epic 3C sends in-app updates
only; external email/SMS is intentionally unavailable. Sent records are
immutable operational history.

Response targets cover acknowledgement, triage, containment, recovery,
resolution, and update frequency. Separate deterministic `incident_*`
APScheduler jobs evaluate targets, overdue tasks, escalation rules,
communication reminders, monitoring, post-incident reviews, follow-ups, and
conservative retention. Escalations are property-scoped, cooldown/repeat
bounded, and non-destructive. Incident and evidence history is never
automatically deleted.

## Evidence and security

Evidence references existing artifacts where possible. Absolute filesystem
paths and traversal are rejected. Evidence carries sensitivity and retention
classification. Viewers cannot read restricted evidence; highly restricted
evidence is excluded from normal bundles unless an administrator exports it.
Exports are redacted and exclude credentials, secrets, raw configuration,
private keys, and excessive protocol data.

Every query and mutation enforces property access. Playbook, template, and
escalation administration requires Admin. Operational task actions allow
authorized technicians. Backend authorization remains authoritative. Timeline
and WebSocket payloads contain identifiers, status, counts, and safe summaries,
not evidence bodies or secrets.

## Human-in-the-loop remediation

Recommendations are deterministic rules referencing only actions in the
approved automation registry. They include rationale, evidence, confidence,
risk, permission, approval, and verification. A human must approve or reject
them; high-risk actions require Admin. Epic 3C does not restore configuration,
reconfigure devices, run shell commands, or perform destructive remediation.

## Verification, recovery, closure, and review

Recovery readiness requires blocking tasks and required checklists complete and
evidence attached. High/critical recovery needs commander or administrator
confirmation. Recovery cannot be declared before verification. Resolution is
blocked while required tasks remain open. Closure requires resolved status,
verified recovery, closure summary/reason, evidence, and commander control for
high/critical incidents.

Cause assessments distinguish confirmed, probable, possible, unknown, and not
investigated. Confirmed cause requires evidence and at least 90% confidence;
probable is never presented as confirmed.

High/critical incidents require a post-incident review. Reviews capture
response, recovery, communication, lessons, and follow-up content.
Corrective/preventive follow-ups retain ownership, due dates, completion, and
verification without deleting the closed incident.

## Frontend and operations

`/incidents` provides property KPIs and a bounded list. `/incidents/new`
provides declaration and duplicate review. `/incidents/:id/command` provides
command, impact, participants, tasks, checklists, evidence, communications,
playbook runs, deterministic remediation, recovery verification, decisions, and
timeline. `/incidents/playbooks` provides the structured builder. The workspace
uses typed APIs, controlled WebSocket refetch, HIOP tokens, responsive cards and
tables, labeled forms, text status, and deliberate empty/error states.

Troubleshooting:

- Activate an approved version before enabling or starting a playbook.
- Assign a commander before a high/critical run.
- Recovery readiness lists open tasks, pending checklists, and evidence count.
- Template preview reports disallowed variables before sending.
- Startup recovers stale playbook runs as timed out.
- Retry a failed step only after reviewing its safe error category. Use
  compensation only when the approved playbook version defines an allowlisted
  compensation action.

## Known limitations

External incident platforms, public webhooks, email/SMS, mobile apps, generative
AI, autonomous remediation, unrestricted device actions, and automatic
configuration restore are excluded. PDF evidence export is not added because
the current stack lacks a safe incident PDF renderer; redacted JSON is
authoritative. No real hotel operational action occurs in automated tests.
