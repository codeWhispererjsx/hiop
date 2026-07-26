# HIOP SNMP integration (Epics 4A–4C)

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

Epic 4A had no installed SNMP library, MIB resolution, engine-ID discovery, live compatibility checks, credential testing, or metric collection.

## Epic 4B client architecture

Epic 4B uses pinned `pysnmp==7.1.27` through an injectable asynchronous transport adapter. `SecureSNMPClient` owns target authorization, short-lived decryption, version/security mapping, response parsing, retry bounds, and cleanup. Routes never construct transport credentials and no shell or subprocess operation is used. Tests inject an in-memory adapter, so verification sends no SNMP packets.

Protocol mapping is exact: v1 uses community MP model 0, v2c uses MP model 1, and v3 uses `UsmUserData` with the configured security level, authentication protocol, privacy protocol, and context. SHA, SHA224, SHA256, SHA384, SHA512, AES128, AES192, and AES256 are mapped only when the installed library exports them. MD5 and DES require the legacy policy. No downgrade is attempted.

## Target authorization and testing

Hostnames resolve through the socket API and every resolved address must be private, inside configured Discovery CIDRs, outside ignored CIDRs, and neither link-local nor multicast. Tests are admin-only and rate-limited. The test retrieves bounded system identity, updates safe target health, records one audit result, and emits summary-only WebSocket/notification events. It never accepts temporary credentials or arbitrary OIDs.

## Approved operations and standard OIDs

The client provides scalar GET, ordered/deduplicated multi-GET, bounded WALK, and bounded BULK-WALK for service-selected OIDs only. There is no public raw GET/WALK route. Standard system OIDs cover sysDescr, sysObjectID, sysUpTime, sysContact, sysName, sysLocation, and sysServices. Interface preview uses bounded IF-MIB identity/status roots and excludes traffic analytics.

WALK operations enforce subtree exit, repeated-OID detection, maximum rows, maximum duration, maximum repetitions, response truncation, and cooperative cancellation. SNMPv1 safely falls back from BULK-WALK to WALK.

## Parsing and persistence

Integer, Counter32, Counter64, Gauge, TimeTicks, OctetString, ObjectIdentifier, IpAddress, Null, noSuchObject, noSuchInstance, and endOfMibView values are normalized. TimeTicks preserve raw ticks and seconds. Unknown types become bounded warning-quality text; oversized text is truncated. Raw packets and unbounded binary values are never stored.

Manual poll types are availability, system, interfaces preview, and custom profile. Runs transition from pending to running and then completed, partial, failed, or cancelled. Approved observations store numeric/text values, units, quality, target, run, OID, and optional interface identity. System polls create or update a pending review candidate and may suggest a profile; they never create inventory.

## Errors, retries, concurrency, and cancellation

Safe categories include host unreachable, timeout, transport error, unauthorized target, missing credential, authentication/privacy failure, unsupported version/protocol, malformed response, missing OID, access denied, too big, walk limit, cancellation, configuration, decryption, and unknown error. Only transient timeout/transport categories are marked retryable; PySNMP applies the configured bounded retry count.

A global semaphore and target/credential locks prevent duplicate target polls, credential rotation during use, tests conflicting with polls, and excessive concurrent operations. Cancellation is checked between WALK batches and preserves already-persisted results. No scheduled polling exists.

## Troubleshooting

- `unauthorized_target`: confirm the resolved address is in Discovery authorized CIDRs and not ignored.
- `decryption_failed`: verify `HIOP_SNMP_SECRET_KEY` matches the key used when the credential was saved.
- `unsupported_protocol`: enable legacy policy only when explicitly required, or select a supported SHA/AES protocol.
- `authentication_failed` or `privacy_failed`: rotate the stored secret and confirm the agent security level.
- `timeout`: check management VLAN/firewall access and bounded timeout/retry settings.

## Epic 4C reviewed onboarding and operational data

Every SNMP discovery candidate remains pending until an administrator acts. Matching is explainable and ranked: explicit target/candidate links are exact; sysName plus management IP, zone, vendor, and type build strong/probable evidence; IP-only and sysName-only evidence remain weak and can never establish identity by themselves. Stored match rows retain matching fields, conflicts, score, level, and recommendation.

Create-new onboarding delegates to the existing Device validator. Asset tag, serial number, MAC, department, location, and other mandatory inventory fields must be supplied—SNMP never invents them. Linking establishes one authoritative target-to-device relation and rejects contradictions. Enrichment is field allow-listed, fill-missing by default, requires explicit fields, records summarized audit evidence, and supports an optimistic `expected_updated_at` freshness check.

Interface inventory uses target plus ifIndex as stable identity. A complete bounded inventory result creates/updates interfaces and increments grace counters for unseen interfaces; partial or truncated results never mark interfaces missing. Records are preserved rather than deleted. Changes record created, updated, restored, missing, status, speed, alias/name, and identity-conflict evidence. A MAC change at the same ifIndex is surfaced as an identity conflict rather than silently merged.

Approved profiles may collect system, interface, and bounded vendor metrics. Canonical keys include `device.uptime_seconds`, `device.response_time_ms`, `interface.in_bps`, `interface.out_bps`, packet/error/discard rates, utilization, `device.cpu_percent`, `device.memory_percent`, `device.temperature_celsius`, `printer.toner_percent`, `ups.battery_charge_percent`, `ups.load_percent`, and `ap.client_count`. Profile transforms remain allow-listed; no public API accepts arbitrary OIDs.

Raw counters remain immutable observations. Rate calculation fetches the prior interface/key sample, validates the time delta, detects credible 32/64-bit wrap, rejects uncertain resets and reboot windows, and emits a separate rate metric with `good`, `wrapped`, `reset`, `stale`, `invalid`, or `unsupported` quality and a bounded reason. Utilization requires a non-zero effective interface speed and flags values above reported capacity rather than normalizing them.

Metric, interface-change, and state-history queries are indexed and paginated. Collection plans and response pages are bounded. Manual retention preview and admin-only cleanup remove expired metrics and empty old poll runs while preserving audit, onboarding, links, interfaces, and state history. No cleanup scheduler is registered.

Operational APIs add candidate detail/match/plan/approve/link/enrich/review, bounded manual collection groups, target/interface metric reads, summaries, interface history, and retention preview/cleanup. Audit and WebSocket messages are operation summaries; no per-sample audit or metric broadcast occurs.

## Limitations after Epic 4C

There is no scheduled polling, alert generation, frontend/dashboard, topology mapping, trap/inform receiver, automatic unreviewed onboarding, persistent rollup table, TCP transport, or MIB-name resolution. Profile OIDs must already be approved configuration. Real hotel-network polling remains prohibited without explicit approval. Epic 4D should add the reviewed frontend and visualization layer, leaving scheduling and alert rules for their designated later phases.

## Epic 4D frontend navigation and monitoring

Authenticated administrators and technicians enter through **SNMP Monitoring** at `/snmp`. The responsive workspace provides overview, targets, credentials, profiles, approved OIDs, candidates, interfaces, poll runs, metric explorer, state changes, retention, and reports. Administrators see mutation controls; technicians receive the backend-authorized read-only experience.

Credential forms dynamically separate community and SNMPv3 fields. Secrets use password controls, confirmation, `autocomplete="new-password"`, component-local state, and the write-only create/rotation APIs. Existing values are never rendered, placed in URLs, logged by the client, or saved to browser storage. SNMPv3 is presented as the production preference.

Target setup filters enabled credentials by SNMP version and explains that saving performs validation but does not poll. Structured testing displays safe validation, authorization, decryption, transport, authentication, identity, and profile stages. Manual collection requires confirmation and accepts only availability, system, interface inventory/performance, device performance, or all-profile groups.

Candidates display system identity, ranked inventory/Discovery evidence, conflicts, required onboarding fields, and explicit review actions. No frontend path automatically approves or creates inventory. Target pages combine health, response time, uptime, supported profile metrics, interfaces, runs, and state history. Interface pages preserve ifIndex identity and show missing/restored history plus quality-aware traffic samples.

Metric charts query bounded APIs, limit rendered samples, display units/quality, provide screen-reader text alternatives, and render deliberate no-data states. Reset, wrapped, stale, invalid, and unsupported samples remain visible. Reboot events explain rate-baseline gaps. WebSocket summaries trigger controlled refetches and a 30-second dashboard poll is the fallback.

Retention is administrator-only and preview-first. Manual cleanup requires browser confirmation and cannot remove audit or onboarding history. SNMP reports currently provide bounded on-screen operational summaries; dedicated CSV/PDF endpoints remain a known limitation.

Troubleshooting:

- If the live channel is disconnected, wait for controlled polling or use refresh; charts are not populated directly from every socket event.
- A target outside configured authorized ranges is rejected by the backend even if the form appears valid.
- A disabled credential/target must be corrected before testing or collection.
- Empty device-specific panels mean the assigned approved profile has not produced those metric keys.
- After a reboot or counter reset, rate metrics remain unavailable until a safe new baseline exists.

## Current limitations after Epic 4D

There is no scheduled SNMP polling, alert-rule generation, topology mapping, trap/inform receiver, unreviewed onboarding, persisted metric rollup table, or real-network acceptance test. SNMP report export and a full client-side onboarding mutation form remain limited to safe plans/typed APIs until their dedicated backend/report workflows are finalized. Real hotel-network polling remains prohibited without explicit approval.
# Epic 4E: scheduled monitoring and alerts

The single HIOP APScheduler creates deterministic per-target/per-group jobs. Startup reconciliation replaces changed
jobs, removes orphans, and recovers stale runs. Bounded jitter, `max_instances=1`, and shared locks prevent poll storms
and overlap. Eligibility requires the integration setting, target, credential, polling flag, and polling configuration
to be enabled; normal address, approved-OID, credential, retry, and concurrency checks still apply.

Maintenance is audited and optionally time-bounded. Collection may continue, but configured rules suppress new events;
maintenance alone never resolves existing events. Alert rules are disabled by default and use fixed comparisons.
Events deduplicate by rule/target/interface/metric, update evidence counters, use multi-sample recovery, and mark
flapping. Evidence excludes secrets, packets, and raw library errors.

One daily cleanup job uses the previewed retention policy. Samples referenced by open alerts and all audit, onboarding,
interface/state, and alert history are protected. Production operators must prefer SNMPv3, review authorized ranges,
schedules, OIDs, jitter, concurrency, thresholds, maintenance, notifications, backups, and retention before enabling
SNMP. Never poll hotel infrastructure without explicit approval.

Traps, topology, device mutation, unreviewed onboarding, and complex on-call scheduling remain out of scope. Scheduling
is inert while `SNMP_ENABLED=false`.
