# HIOP Active Directory Integration (v2 — Epic 3C)

## Epic 3D matching and reconciliation

Epic 3D matches staged directory users to HIOP users, computers to inventory and Discovery records, department values to existing departments, and explicitly configured directory groups to role suggestions. It never grants a role, creates a record, disables an account, retires a device, or changes identifiers without administrator review.

### Explainable scoring

Candidate scores are bounded from 0–100 and retain matching fields, conflict penalties, and individual signal weights. Default levels are exact (95–100), strong (80–94), probable (60–79), weak (35–59), and none. Exact email, UPN, username, DNS hostname, existing links, and Discovery MAC evidence rank highest. IP-only, similar hostname, and display-name-only evidence remain review-only. Candidate generation uses exact filtered queries before bounded fuzzy pools and keeps at most five candidates.

### Conflicts and stale data

Conflicting email, username, hostname, MAC, existing link, or candidate state is never silently accepted. Candidates snapshot the directory `whenChanged` and target `updated_at` values; resolution rejects stale decisions. Dedicated one-to-one record links prevent a directory object from linking to multiple HIOP records or one HIOP record from linking to multiple directory objects in one connection.

### User reconciliation

Existing users may be linked, or enriched only through explicitly approved fill-missing fields. Local role and active status are preserved. Disabled/missing directory users produce review dispositions only.

HIOP currently requires a local password and has no invitation workflow. Consequently, `create_new_user` records a `pending_manual_setup` result with required username/email/role but does not create a User, accept an AD password, generate a default password, or enable domain authentication. Admin role suggestions require separate privileged-role confirmation.

### Device and Discovery reconciliation

Existing devices can be linked or fill-missing enriched while asset tag, MAC, serial, location, monitoring history, tickets, alerts, scans, and audit data remain intact. Device creation requires the complete normal `DeviceCreate` inventory payload and hierarchy validation; no asset tag, serial, MAC, IP, or location is invented. Discovery links are accepted only when the Discovery record is already consistently linked to inventory.

Disabled/missing directory computers only create retirement-review dispositions.

### Department, OU, and group mappings

Department aliases point to existing departments. OU rules are ordered, use constrained non-executable patterns, and may reference existing department/building/floor/room/network-zone records. Group-role mappings are explicit suggestions; Admin mappings must require additional confirmation. No hierarchy or role record is created silently.

### Review APIs and batching

Matching, candidate review, reconciliation plans, resolution, mapping mutation, and bulk review are administrator-only. Technicians retain the existing limited read policy. Bulk linking accepts only conflict-free exact candidates and returns per-object failures. Reconciliation results persist action, target, before/after values, reviewer, status, and safe errors.

The `ad-reconciliation` report summarizes onboarding/link/enrichment dispositions. WebSocket and audit events contain IDs, actions, scores/counts, and statuses—not full directory objects.

## Scope

Epic 3C adds administrator-triggered synchronization into directory staging. It builds on the secure Epic 3B LDAP client and never creates or updates HIOP users or devices.

This phase does not reconcile staging with HIOP records, score matches, schedule work, or add frontend pages.

## Synchronization, staging, and change detection

`POST /api/v1/active-directory/connections/{id}/sync` creates a persistent run, enforces a per-connection active-run guard, binds through the encrypted-secret client, queries enabled object types, and stages approved attributes in configured batches. Run transitions are `pending -> running -> completed|partial|failed|cancelled`. Configuration changes, disable, and secret rotation are blocked during active synchronization.

Full sync performs missing detection only after complete, non-truncated, non-dry queries. Incremental sync uses a fixed `whenChanged` filter from the last successful checkpoint plus a configurable overlap window; stable identity deduplicates overlap results. Checkpoints advance only after wholly successful non-dry runs. Timestamp-based incremental sync is conservative and is not claimed to be as lossless as AD DirSync controls.

Dry runs query and compare while avoiding staging mutations, history, missing detection, and checkpoint changes. Projected counts remain attached to the run.

Identity priority is GUID, SID, then a normalized-DN digest fallback. Canonical comparison normalizes case where appropriate, nulls, DNs, UTC timestamps, and multivalue ordering. Created, updated, moved, renamed, enabled, disabled, missing, and restored changes are stored as bounded field-level history without replacing review decisions or match links.

Batch commits preserve progress and successful work. Sanitized per-object/query errors remain paginated on the run. Cancellation is cooperative at batch boundaries. Aggregate audit, WebSocket, and email notifications avoid broadcasting directory object contents.

Staging endpoints add run detail/cancel/errors/summary/dry-run results plus object detail and change history. Administrators control sync and full detail; technician reads redact email and raw attributes.

## LDAP modes

- LDAPS uses TLS from connection start, normally on port 636.
- StartTLS opens LDAP and upgrades the connection before binding, normally on port 389.
- Plain LDAP is accepted only when the backend is in development and `AD_ALLOW_INSECURE_LDAP=true`.

LDAPS and StartTLS are mutually exclusive. Production rejects disabled certificate verification and plain LDAP. Anonymous bind is supported only when explicitly configured without bind credentials.

## Host and SSRF policy

The configured host cannot contain a URL scheme, embedded credentials, whitespace, or malformed hostname content. By default, hostnames must align with the configured AD DNS domain and IP literals must be private, loopback, or link-local. Exceptional hosts require `AD_APPROVED_HOSTS`; arbitrary public hosts require the protected `AD_ALLOW_PUBLIC_HOSTS` policy.

No API accepts a URL or raw network destination.

## TLS and certificates

TLS uses certificate and hostname verification through Python and ldap3. A custom public CA bundle may be referenced by path; HIOP never stores a CA private key or returns certificate content. The client uses a modern TLS client context and never silently disables validation.

Safe client errors distinguish TLS handshake failure from certificate validation failure. Detailed logs contain only the connection ID, operation, duration/status, and safe category.

## Credentials and bind lifecycle

The bind secret remains encrypted at rest with authenticated Fernet encryption. The service decrypts it immediately before bind, drops the local plaintext reference after the bind call, closes the LDAP connection in `finally`, and clears the ldap3 password reference where possible.

Credentials are not serialized, audited, broadcast, or included in exception messages. Changing the encryption key still requires re-entering saved secrets; a versioned keyring or external vault is recommended for production.

## RootDSE discovery

The client requests only:

- `defaultNamingContext`
- `rootDomainNamingContext`
- `configurationNamingContext`
- `schemaNamingContext`
- `supportedLDAPVersion`
- `supportedSASLMechanisms`
- `dnsHostName`
- `serverName`

The response reports whether LDAP v3 is supported and whether expected AD naming contexts are present. APIs return only this safe subset.

## Search-base validation

Base and specialized user/computer/group DNs must:

- Have valid DN syntax
- Remain within the configured base DN
- Exist according to a bounded base-scope LDAP search

Empty specialized bases fall back to `base_dn`. A configured base that differs from RootDSE is reported as a warning; missing or escaping search bases fail the operation.

## Filter safety

Clients cannot submit raw LDAP filters or attribute names. HIOP uses fixed templates:

- Users: person/user objects excluding computers
- Computers: computer category/class
- Groups: group category/class

Search terms are limited to 64 characters, raw wildcards are rejected, and values are escaped with ldap3’s RFC-compatible filter escaping. Search attributes come from a small internal allowlist.

## Query engines

User previews return identifiers, account/display/email/department/title fields, selected group DNs, enabled state, timestamps, description, and organizational unit.

Computer previews return identifiers, normalized DNS hostname, OS/version, description, managed-by DN, enabled state, timestamps, and organizational unit.

Group previews return identifiers, name, description, converted group scope/security type, timestamps, and organizational unit. Membership is excluded by default. When explicitly requested, both the number of groups and members returned per group are bounded and truncation is visible.

Password, credential, token, and unrelated personal attributes are never requested.

## Attribute conversion

Converters safely handle binary GUID and SID values, Windows FILETIME, generalized timestamps, user-account-control flags, group-type flags, multivalued fields, missing attributes, and malformed values. Conversion failures attach a bounded parse warning to that object rather than terminating the page.

All emitted datetimes are UTC-aware.

## Paging and limits

The client uses the Active Directory paged-results control and opaque paging cookies. It enforces:

- Configured and maximum page size
- Maximum objects per preview
- Connection and search timeouts
- Maximum full-membership groups and members
- Maximum retry count
- Repeated-cookie and page-loop detection

Only transient reachability/timeouts are retried, with a small bounded backoff. Invalid credentials, access denial, certificate errors, invalid DNs, and configuration errors are not retried.

## Connection test

`POST /api/v1/active-directory/connections/{id}/test` is administrator-only and rate-limited. It validates connection/TLS, bind, RootDSE, base/search DNs, and one-record permission checks for users, computers, and groups.

The structured response contains stage status, safe messages, warnings, error category, timestamp, and total duration. It updates last-test, last-success/failure, failure-count, and server-domain health metadata and creates summarized audit records.

## Preview APIs

- `GET /api/v1/active-directory/connections/{id}/root-dse`
- `GET /api/v1/active-directory/connections/{id}/preview/users`
- `GET /api/v1/active-directory/connections/{id}/preview/computers`
- `GET /api/v1/active-directory/connections/{id}/preview/groups`

They are administrator-only, bounded, non-persistent, and reject disabled connections. Query parameters provide only a limited search term, enabled state where relevant, result limit, and optional bounded group membership.

## Safe error categories

`host_unreachable`, `timeout`, `tls_failed`, `certificate_invalid`, `bind_failed`, `access_denied`, `base_dn_not_found`, `search_base_invalid`, `query_failed`, `page_limit_exceeded`, `malformed_response`, `configuration_error`, and `unknown_error`.

Raw exceptions and directory entries are not returned.

## Development testing

Automated tests use injected mock clients and in-memory fake ldap3 connection/entry behavior. They never resolve or connect to a hotel domain. Test coverage includes modes, TLS policy, host policy, filter injection, conversions, paging, limits, safe errors, health updates, rate limiting, and authorization contracts.

## Production requirements

- Configure a dedicated `HIOP_AD_SECRET_KEY`.
- Use LDAPS or StartTLS with certificate verification.
- Configure an internal domain-aligned host or explicit approved-host list.
- Provide only a public CA bundle when private PKI is used.
- Grant the bind account the minimum read permissions.
- Review logs and rate-limit behavior before enabling tests.
- Keep `AD_ALLOW_INSECURE_LDAP=false` and `AD_ALLOW_PUBLIC_HOSTS=false`.

## Troubleshooting

- `host_unreachable`: verify DNS, route, firewall, host policy, and port.
- `certificate_invalid`: verify hostname/SAN, trust chain, expiry, and CA reference.
- `bind_failed`: rotate the saved secret and verify the bind identity.
- `base_dn_not_found`: compare configured bases with safe RootDSE metadata.
- `access_denied`: grant only the missing read permission.
- `page_limit_exceeded`: narrow the preview or lower page/result limits.

## Known limitations and Epic 3D

Connection rate limits are process-local. Certificate expiry is reserved in health metadata but remains unset unless safely available from the TLS stack. Group member range retrieval is bounded after response parsing rather than using AD ranged attributes.

Manual execution is inline because HIOP has no durable background-job executor. Cancellation takes effect at a batch boundary. Timestamp incremental sync uses overlap rather than AD DirSync control. No AD frontend exists.

Epic 3D should add reviewed user/device reconciliation and match scoring. It must not silently create or update HIOP records.
