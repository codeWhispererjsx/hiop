# Configuration management foundation

Epic 2A provides property-scoped profiles, backup policies, backup-run metadata,
encrypted configuration versions, SHA-256 integrity metadata, and secure manual
uploads. Uploads accept approved text/configuration formats only, reject empty or
oversized files, use the existing application encryption abstraction, and never
return content in ordinary list responses.

Live SSH/API collection, scheduled backups, comparison, restore, deployment, and
compliance evaluation are intentionally deferred to Epic 2B and later.

Epic 2B adds the collector registry and known-host/test-run foundations. The
included mock collector is deliberately non-networking: it validates workflow
stages without contacting devices. Host keys remain pending until an administrator
trusts them; unknown or changed keys must never be silently accepted. Real SSH,
HTTPS, SCP, and SFTP collectors require a separately approved implementation and
lab verification.
