# HIOP Active Directory Integration Foundation (v2 — Epic 3A)

## Purpose and scope

Epic 3A establishes a backend-only architecture for future Microsoft Active Directory integration. It introduces connection profiles, encrypted write-only credentials, synchronization configuration, directory-object staging, run telemetry, match-candidate persistence, repositories, service boundaries, schemas, and configuration APIs.

It does not make live LDAP connections, query a directory, synchronize users or computers, schedule synchronization, mutate inventory, or add frontend administration pages.

## Planned data flow

1. An administrator creates a disabled-by-default connection profile and sync policy.
2. A future Epic 3B worker retrieves and decrypts the bind secret only for a bounded connection attempt.
3. Directory users, computers, and groups are staged as `ActiveDirectoryObject` records using the stable object GUID.
4. A sync run records counts, duration, safe failures, and dry-run state.
5. Matching produces reviewable user or device candidates.
6. No HIOP user or device changes occur without a later reviewed workflow.

## Connection model

`ActiveDirectoryConnection` supports multiple named domain profiles with server, port, TLS mode, base/search DNs, authentication method, timeout, paging, TLS verification, certificate reference, test state, and creator/updater attribution.

LDAPS and StartTLS are mutually exclusive. Domain names, hosts, distinguished names, ports, timeouts, and page sizes are validated at the API boundary and constrained where practical in PostgreSQL.

## Secret handling

Bind credentials are accepted only on create or secret-rotation requests. Responses expose only `has_bind_secret`; ciphertext and plaintext are never serialized or included in audit descriptions.

Secrets use authenticated Fernet encryption. The key is derived from the dedicated `HIOP_AD_SECRET_KEY`; the existing HIOP `SECRET_KEY` is a compatibility fallback. Missing or incorrect keys fail closed with safe messages.

Changing the encryption key currently requires re-entering each connection secret. Before production rollout, use a versioned multi-key decryptor or an external secrets manager. Do not store credentials, private keys, directory exports, or CA private material in source control.

## Foundation configuration

Environment-driven settings define:

- Integration enablement, default LDAP and LDAPS ports
- Connection and search timeouts
- Default and maximum page size
- Maximum objects per sync and sync concurrency
- Minimum and maximum sync intervals
- Required TLS verification
- Development-only insecure LDAP allowance

`ACTIVE_DIRECTORY_ENABLED` defaults to false. Insecure LDAP is rejected outside development, and production requires TLS verification.

## Staging model

`ActiveDirectoryObject` stages `user`, `computer`, and `group` objects. It preserves the directory GUID, SID, distinguished name, common identities, organizational metadata, safe selected raw attributes, first/last-seen timestamps, sync/review status, and optional HIOP match.

The database prevents duplicate object GUIDs per connection and prevents a staged object from pointing to both a user and a device.

## Sync run lifecycle

`ActiveDirectorySyncRun` reserves `pending`, `running`, `completed`, `partial`, `failed`, and `cancelled` states. Counters and duration are nonnegative. Epic 3A exposes run history only; run execution remains an explicit `NotImplementedError` boundary for Epic 3B.

## Matching model

`ActiveDirectoryMatchCandidate` reserves typed HIOP user/device candidates, a bounded score, match level/status, matching and conflicting fields, evidence, a recommended action, and reviewer metadata. A database check requires exactly the target type declared by the candidate.

No scoring or resolution logic is implemented in Epic 3A.

## Permissions and audit

- Administrators can create/update/disable connections, rotate secrets, run the mock-only test, and change sync configuration.
- Administrators and technicians can read configuration metadata, staged objects, run history, and match candidates.
- Staff users are denied AD routes.
- Unauthenticated requests receive `401`; role violations receive `403`.

Implemented mutations create summarized audit events without credentials.

## Security risks and controls

- LDAP injection: no public arbitrary LDAP-filter API exists.
- SSRF/network access: the Epic 3A client is mock-only and opens no socket.
- Credential leakage: secret schemas are write-only and errors do not include cryptographic internals.
- Weak transport: mutually exclusive TLS modes are validated; production requires TLS verification.
- Excessive ingestion: page, object, concurrency, timeout, and interval limits are configured before live sync exists.
- Raw attributes: future ingestion must allowlist attributes and exclude password, token, and unrelated sensitive data.

## Epic 3B

Epic 3B may add a real LDAP client with certificate validation, bounded allowlisted filters, connection testing, dry-run synchronization, staging, missing-object detection, and candidate generation. It must retain the review boundary and must not silently create or update HIOP records.
