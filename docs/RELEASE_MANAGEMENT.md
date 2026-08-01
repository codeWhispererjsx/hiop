# Release Management

Enterprise releases use stable `REL-YYYY-NNNNNN` identifiers and support major, minor, patch, and emergency types. Releases can contain packages, immutable version metadata, artifacts, deployment waves, release notes, validation outcomes, and rollback plans. Deployments are property-aware and may link to approved changes and maintenance windows.

The `/changes/releases` workspace and `/api/v1/changes/releases` APIs provide reviewed release records. HIOP tracks deployment and verification; it does not autonomously deploy software or infrastructure changes.
