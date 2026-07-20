# Discovery architecture and engine

Epic 1A introduced persistence and extension points; Epics 1B–1E complete a conservative, integrated Discovery module. Discovery can run manually or through one bounded scheduler job, exposes secured APIs and a real-data frontend, and creates inventory only after explicit administrator approval.

## Boundaries

The foundation contains two SQLAlchemy models, three enums, persistence-only repositories, a deliberately unimplemented service contract, configuration defaults, an Alembic revision, and contract tests. Later epics must implement orchestration without placing matching or workflow rules in repositories.

## Persistence model

`discovered_devices` stores the latest consolidated observation of a network identity, its first/last observation times, review metadata, optional links to an approved inventory device, reviewer, and network zone, plus confidence and response metadata.

`discovery_runs` stores run lifecycle and aggregate counters. `triggered_by` optionally links to the initiating user. Observations are consolidated into device history; there is intentionally no per-host run child table.

State is constrained by application enums and database checks:

- Discovery status: `online`, `offline`, `unknown`
- Review status: `pending`, `approved`, `ignored`, `rejected`
- Run status: `pending`, `running`, `completed`, `partial`, `failed`

## Identity and duplicate protection

Matching priority is encoded as four PostgreSQL partial unique indexes:

1. Case-insensitive MAC when present.
2. Approved inventory device when linked.
3. IP plus case-insensitive hostname when MAC and approval links are absent.
4. IP alone when MAC, approval link, and hostname are absent.

Future matching code must evaluate candidates in this same order. The repository layer must remain unaware of that policy.

## Discovery engine

`DiscoveryService` validates that every requested IPv4 CIDR is private, contained by an authorized range, below the configured host limit, and filtered by private ignore ranges. It uses bounded concurrent ICMP probes, reads the operating system's existing ARP/neighbor cache without generating ARP traffic, performs bounded PTR resolution, applies an offline OUI vendor hint, and stores deliberately conservative device and operating-system guesses.

Fingerprint outputs are hints, never assertions. Device guesses are limited to workstation, printer, switch, router, server, access point, IP phone, POS, camera, mobile, and unknown, with confidence capped below certainty.

Repository query methods support the service's matching order but contain no matching policy. The service consolidates observations by MAC, approved-device link, IP plus hostname, then IP. Existing inventory uses the same priority and may be linked; no inventory record is created or modified. Database partial unique indexes remain the final duplicate-prevention boundary.

Run rows provide discovery history and aggregate counters. Consolidated device rows retain first seen, last seen, and times seen. Statistics report device states, pending review, inventory matches, run totals, and the latest run.

## API and approval workflow

Epic 1C exposes authenticated list, detail, and statistics APIs. Running Discovery, approving, ignoring, rejecting, CSV export, and all bulk actions require an administrator. No frontend is included.

Approval validates a complete inventory record, rejects an existing inventory link or unique asset/serial/MAC conflict, creates the official device, links the discovery, records reviewer and timestamp, and writes audit records in one transaction. Ignore and reject retain the discovery and observation history; rejection may append a reason to notes. Bulk actions are atomic.

Successful mutations emit authenticated WebSocket events and use the configured email-notification channel on a best-effort basis after commit. Reporting prefixes spreadsheet-formula characters before CSV output.

## Configuration

Discovery defaults are stored under the `discovery.*` namespace and discovery is disabled by default. Administrators can manage validated authorized CIDRs, ignored CIDRs, interval, timeout, concurrency, host cap, lookup toggles, and notification threshold in Settings. Saving settings atomically audits the change and replaces or removes the single `automatic_discovery` scheduler job.

## Integration and operational boundaries

Scheduled runs process configured authorized ranges sequentially. APScheduler uses a stable job ID, `replace_existing`, `max_instances=1`, and coalescing, preventing duplicate registrations and overlap inside the supported single-worker deployment. Run completion/failure and review actions publish authenticated WebSocket events. Email uses the existing deployment-only SMTP credentials and notification policy; successful-run email is gated by the configured new-device threshold.

Discovery appears as a date-scoped, searchable, sortable, paginated and CSV-exportable report. Review and run activity is immutable audit data. Indexed status, review status, hostname, IP, subnet, last-seen time, unique MAC, inventory link, IP/hostname, and IP-only identities support common reads and duplicate prevention.

Safety is enforced again at execution time: IPv4 only, private ranges only, requested subnet containment, ignored ranges, maximum usable hosts, bounded workers/timeouts, passive neighbor-cache reading, ICMP, and bounded reverse DNS. There is no port scan, service enumeration, credential attempt, arbitrary command, public-internet scanning, or automatic inventory creation.

## Migration

Revision `c87d380fc50a` follows the v1 operational-index head `a71c8d9e4f20`. It creates `discovery_runs` before `discovered_devices` and drops the tables in reverse order. PostgreSQL is required for the UUID and partial-index contract.
