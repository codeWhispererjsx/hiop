# Discovery architecture foundation

Epic 1A introduces persistence and extension points for a future Discovery module. It does not perform network access, schedule work, expose API routes, render frontend pages, review records, or create inventory devices.

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

## Extension points

`DiscoveryRepository` and `DiscoveryRunRepository` provide only add/get/list/delete persistence operations and do not commit transactions. `DiscoveryService` declares future orchestration methods which currently raise `NotImplementedError`. Transaction ownership, scanning, matching, review, approval, audit, notifications, scheduling, and inventory mutation are deferred.

## Configuration

Discovery defaults are stored under the `discovery.*` namespace and discovery is disabled by default. These keys are backend configuration only and are not exposed through a Discovery UI in Epic 1A.

## Migration

Revision `c87d380fc50a` follows the v1 operational-index head `a71c8d9e4f20`. It creates `discovery_runs` before `discovered_devices` and drops the tables in reverse order. PostgreSQL is required for the UUID and partial-index contract.
