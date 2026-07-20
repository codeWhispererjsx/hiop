# Discovery architecture and engine

Epic 1A introduced persistence and extension points. Epic 1B implements a conservative backend discovery engine. It does not schedule work, expose API routes, render frontend pages, review records, or create inventory devices.

## Boundaries

The foundation contains two SQLAlchemy models, three enums, persistence-only repositories, a deliberately unimplemented service contract, configuration defaults, an Alembic revision, and contract tests. Later epics must implement orchestration without placing matching or workflow rules in repositories.

## Persistence model

`discovered_devices` stores the latest consolidated observation of a network identity, its first/last observation times, review metadata, optional links to an approved inventory device, reviewer, and network zone, plus confidence and response metadata.

`discovery_runs` stores run lifecycle and aggregate counters. `triggered_by` optionally links to the initiating user. There is intentionally no scheduler registration and no discovery-to-run child table in this phase.

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

Discovery defaults are stored under the `discovery.*` namespace and discovery is disabled by default. These keys are backend configuration only and are not exposed through a Discovery UI.

## Migration

Revision `c87d380fc50a` follows the v1 operational-index head `a71c8d9e4f20`. It creates `discovery_runs` before `discovered_devices` and drops the tables in reverse order. PostgreSQL is required for the UUID and partial-index contract.
