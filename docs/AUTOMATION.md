# Automation engine foundation

Epic 3A introduces property-scoped workflow definitions, immutable version
metadata, an approved action catalogue, structured condition evaluation, dry-run
records, and manual-run lifecycle storage. Workflow definitions contain bounded
structured data only: no `eval`, executable plugins, shell commands, arbitrary
URLs, or dynamic module imports are supported.

Automatic schedules, event triggers, autonomous remediation, and infrastructure
changes are disabled. The dry-run API explicitly reports that execution is not
enabled until approved handlers and the existing reviewed configuration workflows
are verified.

Epic 3B adds an internal-event and schedule foundation. Events are restricted to
an allowlisted catalogue with bounded safe payloads and property scope. Trigger
subscriptions store cooldown and deduplication controls. Schedules are disabled
by default and reference exact workflow versions; external webhooks, broker
consumers, and autonomous workflow execution remain disabled.
