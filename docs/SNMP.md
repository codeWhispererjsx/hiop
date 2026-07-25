# HIOP SNMP integration foundation (Epic 4A)

## Purpose and boundary

Epic 4A adds the secure persistence, validation, authorization, and configuration API foundation for future SNMP discovery and monitoring. It does **not** include a functioning SNMP transport, target tests, GET/WALK operations, polling, scheduling, metrics dashboards, alerts, topology mapping, frontend administration, or automatic inventory creation.

No hotel-network device was contacted while implementing or testing this foundation.

## Architecture

`SNMPCredential` contains encrypted connection material and owns one or more `SNMPTarget` records. A target may reference an inventory `Device`, a staged `DiscoveredDevice`, a `NetworkZone`, and a room-based location without requiring inventory promotion. Each target has at most one inactive-by-default `SNMPPollingConfiguration`, plus future poll runs, metrics, interfaces, and reviewed discovery candidates.

`SNMPDeviceProfile` describes non-executable vendor/device classification data. `SNMPOIDDefinition` associates validated numeric OIDs and approved transforms with a profile. Repositories are persistence-only; services own validation, auditing, encryption, and lifecycle rules. `SNMPClient` is an abstract interface and `DisabledSNMPClient` fails closed for every operation.

## Supported protocol preparation

- SNMPv1 and SNMPv2c community profiles
- SNMPv3 `noAuthNoPriv`, `authNoPriv`, and `authPriv`
- Authentication: MD5 (legacy-gated), SHA, SHA224, SHA256, SHA384, SHA512
- Privacy: DES (legacy-gated), AES128, AES192, AES256
- UDP transport and port 161 defaults

Production configuration rejects enabling SNMPv1. Legacy algorithms are represented for later compatibility work but are disabled by policy by default.

## Credential security

Community strings, authentication secrets, and privacy secrets are encrypted with Fernet authenticated encryption through HIOP's shared integration-secret service. `HIOP_SNMP_SECRET_KEY` is preferred; the application secret is the fallback. Secrets are accepted only by create/rotation schemas, are never serialized, and are represented to readers only as `has_*` booleans.

Decryption is reserved for a future short-lived client operation. Audit records contain IDs, names, and safe operation descriptions only. There is no plaintext fallback.

Version validation is strict:

- v1/v2c require a community and reject v3 fields.
- v3 requires a username and rejects communities.
- `noAuthNoPriv` rejects auth/privacy material.
- `authNoPriv` requires an auth protocol/secret and rejects privacy material.
- `authPriv` requires auth and privacy protocols/secrets.

## Targets and network safeguards

Targets use literal IP addresses, a bounded port/timeout/retry policy, UDP transport, and a unique endpoint/port/transport/context tuple. Creation and address changes must fall within configured Discovery authorized CIDRs and must not use public addresses. Credentials and all optional cross-record references are validated before persistence. There are no arbitrary probe, GET, WALK, or target-test endpoints.

## Profiles and OIDs

Profiles classify switch, router, firewall, access point, wireless controller, printer, UPS, server-management, environmental sensor, IP-phone, and generic SNMP devices. Profile JSON rejects executable keys. OIDs must be dotted numeric identifiers. Transforms are allow-listed: identity, scale, timeticks-to-seconds, enum mapping, and bytes-to-bits.

## Polling and observation foundations

Polling configurations default to disabled and contain bounded intervals, OID/interface limits, and opt-in collection categories. Poll runs define pending/running/completed/partial/failed/cancelled lifecycle storage only. Metrics store one bounded numeric or text value with quality and observation time; raw SNMP responses are not retained. Interfaces use a target/index uniqueness constraint and first/last-seen timestamps so future disappearance does not require deletion.

## Discovery candidates and permissions

Candidates store safe system identity, classification evidence, confidence, matching references, and review state. They never create inventory automatically.

- Administrators may create and update credentials, targets, profiles, OIDs, and polling configuration.
- Administrators and technicians may read safe configuration and empty/future observation foundations.
- Unauthenticated requests receive 401; unauthorized mutations receive 403.

## Configuration APIs

Configuration routes are under `/api/v1/snmp`: credentials and secret rotation, targets, profiles, OID definitions, target polling configuration, and paginated read foundations for poll runs, metrics, interfaces, and candidates. No live-operation route is registered.

## Operations and production recommendations

Keep `SNMP_ENABLED=false` until a later epic provides reviewed transport. Use a dedicated high-entropy `HIOP_SNMP_SECRET_KEY`, SNMPv3 `authPriv`, SHA-2, AES, least-privilege read-only agent accounts, restricted management VLANs, and authorized CIDRs. Do not place secrets in `.env` files committed to source control.

## Known limitations and planned Epic 4B

Epic 4A has no installed SNMP library, MIB resolution, engine-ID discovery, live compatibility checks, credential testing, metric collection, retry execution, scheduler integration, notifications, alerts, dashboards, topology, or onboarding. Epic 4B should add a bounded mocked-first transport and explicit test workflow only after approval; production polling remains a separate reviewed phase.
