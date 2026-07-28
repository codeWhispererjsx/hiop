# Configuration management foundation

Epic 2A provides property-scoped profiles, backup policies, backup-run metadata,
encrypted configuration versions, SHA-256 integrity metadata, and secure manual
uploads. Uploads accept approved text/configuration formats only, reject empty or
oversized files, use the existing application encryption abstraction, and never
return content in ordinary list responses.

Live SSH/API collection, scheduled backups, comparison, restore, deployment, and
compliance evaluation are intentionally deferred to Epic 2B and later.
