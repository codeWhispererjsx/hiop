# Enterprise Configuration Management Database

Epic 5 introduces HIOP's authoritative, property-aware Configuration Item (CI) register. It links to existing assets and discovery records without replacing or mutating those source domains. CIs use stable `CI-YYYY-NNNNNNN` numbers, seeded hospitality taxonomy, lifecycle history, typed attributes, identifiers, aliases, reviewed relationships, reconciliation candidates, dependency snapshots, and deterministic health snapshots.

## Workflow

Administrators and technicians may create scoped CIs. Lifecycle transitions are restricted to `planned → ordered → installed → operational ↔ maintenance → retired → archived`; archive is also available for an abandoned planned CI. Every transition is audited. Retired CIs are retained and archived rather than deleted.

The `/cmdb` workspace provides dashboard, explorer, creation, relationships, dependency graph, impact analysis, reconciliation, health, attribute management, search, and reports. The REST surface is `/api/v1/cmdb` and is backend-authorized.

## Security and authority

HIOP never creates a relationship from discovery evidence. Reconciliation creates review records; an administrator must explicitly link or create a CI. Bulk operations are bounded to 100 records and return per-CI results. Property access applies to every CI and derived view. Exports are bounded and CSV-formula safe.

## Operations

Seven stable jobs perform stale-verification marking, relationship validation, health calculation, duplicate/orphan assessment, discovery candidate refresh, and grouped warranty reminders. No job retires, archives, links, or creates a CI. See `CI_RELATIONSHIPS.md`, `IMPACT_ANALYSIS.md`, `DISCOVERY_RECONCILIATION.md`, and `CMDB_HEALTH.md`.

## Known limitations

Legacy discovery records lack direct property context and therefore enter only the corporate review queue. Vendor/cloud/service connectors remain explicit future adapters. Dependency views represent CMDB relationships, not observed packet routing or guaranteed outage behavior.
