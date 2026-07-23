# HIOP Active Directory Integration (v2 — Epic 3B)

## Scope

Epic 3B adds secure, bounded directory communication to the Epic 3A persistence foundation. Administrators can test a saved connection, inspect safe RootDSE metadata, and preview users, computers, and groups without persisting directory results.

This phase does not synchronize or stage objects, mutate HIOP users or devices, score matches, schedule work, or add frontend pages.

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

## Known limitations and Epic 3C

Connection rate limits are process-local. Certificate expiry is reserved in health metadata but remains unset unless safely available from the TLS stack. Group member range retrieval is bounded after response parsing rather than using AD ranged attributes.

Epic 3C may add administrator-triggered dry-run synchronization into staging and missing-object detection. It must not automatically create or update HIOP users or devices.
