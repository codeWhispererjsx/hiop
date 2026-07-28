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
