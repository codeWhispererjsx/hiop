# Enterprise Problem Management

Epic 6 adds the human-controlled ITIL lifecycle `New → Under Investigation → Root Cause Identified → Known Error → Change Required → Resolved → Closed`.

Problems use immutable UUIDs and generated `PRB-YYYYMMDD-NNNNN` numbers. Records capture category, priority, severity, impact, business and technical impact, ownership, team, property, department, service, review dates, revisions, and closure. Lifecycle transitions are sequential. Root Cause Identified requires a validated cause; Known Error requires a KEDB record; Closed requires an approved post-resolution review.

The module relates problems explicitly to incidents, changes, CIs, assets, knowledge, runbooks, SOPs, vendors, contracts, maintenance, services, and automation. Relationships are stored as reviewed edges and rendered as bounded graphs.

Correlation groups incidents by an existing correlation key or the deterministic tuple property/service/type. Threshold evaluation creates review suggestions only. It never creates a Problem, root cause, workaround, or resolution automatically.

Permissions follow existing HIOP roles: viewers read; technicians investigate and maintain records; administrators approve, publish, retire, verify, and run correlation detection. Every mutation writes to the audit trail.
