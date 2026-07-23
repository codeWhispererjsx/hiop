# HIOP Active Directory Integration Foundation (v2 — Epic 3A)

## Purpose and Scope

HIOP Epic 3A establishes the secure backend architecture and data models for integrating HIOP with Microsoft Active Directory (AD). 

Epic 3A is **architecture and foundation only**. It introduces the database models, secret encryption abstraction, repository layer, service skeletons, REST API configuration endpoints, and validation schemas.

### Excluded from Epic 3A (Deferred to Epic 3B)
- Live network connections to real domain controllers
- Live LDAP/LDAPS directory queries
- Automatic user or device creation in HIOP
- Scheduled directory synchronization
- Frontend administration pages
- Plaintext password storage or logging

---

## Connection Model

Active Directory connections are represented by `ActiveDirectoryConnection` and configured per domain.

Key attributes:
- `name`: Unique connection profile name.
- `domain_name`: Fully Qualified Domain Name (e.g. `hotel.internal`).
- `server_host` & `server_port`: Primary LDAP/LDAPS host and port (default `389` or `636`).
- `use_ssl` / `use_start_tls`: Transport encryption flags.
- `base_dn`: Root Distinguished Name (e.g. `DC=hotel,DC=internal`).
- `user_search_base`, `computer_search_base`, `group_search_base`: Optional OU boundaries.
- `bind_username`: Service account distinguished name or UPN.
- `encrypted_bind_secret`: Encrypted at rest (never serialized or returned in responses).
- `authentication_method`: `simple`, `ldaps`, `start_tls`, `anonymous`, `kerberos`.

---

## Secret Handling & Encryption

Bind credentials are write-only and encrypted at rest using AES-256 / Fernet derived from environment keys (`HIOP_AD_SECRET_KEY` or `SECRET_KEY`).

- **Write-Only**: API responses provide only a boolean flag `has_bind_secret: true/false`.
- **Zero Leakage**: Plaintext secrets are never returned in JSON payloads, serialized Pydantic responses, or audit log descriptions.
- **Fail-Safe**: Secret operations fail safely if encryption keys are missing or invalid.

---

## Staging & Sync Architecture

### Staging Model (`ActiveDirectoryObject`)
Imported directory objects are staged prior to matching or review:
- **Object Types**: `user`, `computer`, `group`.
- **Identifiers**: `object_guid` (stable directory GUID), `object_sid`, `distinguished_name`, `sam_account_name`, `dns_hostname`.
- **Sync & Review Status**: `discovered`, `unchanged`, `changed`, `missing`, `error` / `pending`, `matched`, `approved`, `ignored`, `conflict`.

### Sync Run Lifecycle (`ActiveDirectorySyncRun`)
Tracks synchronization run metadata:
- **Run Statuses**: `pending`, `running`, `completed`, `partial`, `failed`, `cancelled`.
- **Metrics**: Count of users seen, computers seen, groups seen, created/updated/missing objects, duration, and error summary.

### Candidate Matching Model (`ActiveDirectoryMatchCandidate`)
Links staged directory objects to existing HIOP `User` or `Device` records with confidence scores, evidence breakdown, match levels (`exact`, `high`, `medium`, `low`, `none`), and recommended actions (`link`, `create`, `enrich`, `review`, `ignore`).

---

## Security & Permissions

- **Configuration Mutations**: Administrator role (`admin`) required for POST/PATCH/DELETE/Secret rotation routes.
- **Operational Read Access**: Authenticated users (`admin`, `technician`, `staff`) may view connection listings and sync history per role policy.
- **Unauthenticated Access**: Rejected with `401 Unauthorized`.
- **Unauthorized Mutations**: Rejected with `403 Forbidden`.

---

## Planned Epic 3B Deliverables

1. Live LDAP/LDAPS connection manager and TLS certificate verification.
2. Background sync runner integrated with APScheduler.
3. Automated and manual directory object matching workflows.
4. Interactive frontend Active Directory administration dashboard.
