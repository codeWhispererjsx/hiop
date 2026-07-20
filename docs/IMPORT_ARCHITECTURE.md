# Intelligent inventory import architecture

Epic 2A establishes persistence and extension boundaries for enterprise inventory imports. It intentionally provides no upload API, file parser, matching engine, review workflow, inventory mutation, scheduler, or frontend.

## Import lifecycle

The planned lifecycle is:

1. An authenticated administrator uploads an allow-listed file in a later epic.
2. HIOP creates an `uploaded` import session using a server-generated storage name while retaining a display-only original filename.
3. File and column validation moves the session through `validating`.
4. Parsed rows are staged as `ImportedDevice` records with their original values in `raw_data`.
5. Row validation classifies records as `pending`, `valid`, `warning`, `duplicate`, or `invalid`.
6. A future matching engine compares valid staged rows with inventory and Discovery without mutating either source.
7. Administrator review decides whether to create, merge, skip, or reject records in a later phase.
8. Processing counters and a bounded safe error summary finalize the session as `completed`, `partial`, or `failed`.

Epic 2A implements only the database states and interfaces required to support that lifecycle.

## Data model

`import_sessions` is the aggregate root. It stores safe server and original filenames, import/file types, uploader, lifecycle timestamps, constrained status, non-negative counters, a bounded operational error summary, and audit timestamps.

`imported_devices` stores normalized candidate fields without linking or merging them into official inventory. It includes asset and network identifiers, textual hierarchy candidates, vendor/product metadata, inventory state, PostgreSQL JSONB raw source data, constrained validation state, and timestamps.

One session owns many staged devices through a UUID foreign key with database cascade semantics. The uploader uses the existing string user identifier and becomes null if the user is removed. Session, status, chronology, asset tag, hostname, IP, and MAC indexes support future review queries. Case-insensitive partial unique indexes prevent repeated non-null asset tags and MAC addresses within one session.

## Layer boundaries

- SQLAlchemy models define persistence and integrity only.
- `ImportSessionRepository` and `ImportedDeviceRepository` contain basic persistence queries and no workflow decisions.
- `ImportService` reserves orchestration methods and raises `NotImplementedError` in Epic 2A.
- `ImportFieldValidator` and the eight named validator classes reserve a uniform validation result contract without validation implementations.
- No API router is registered and no frontend or scheduler dependency exists.

## Planned matching engine

Future matching must be deterministic, explainable, and confidence-scored. Candidate priority should consider exact inventory identifiers first (asset tag, serial number, normalized MAC), then Discovery links and network identity, then weaker hostname/location evidence. Every proposed match must retain its evidence and must not imply certainty. Ambiguous candidates must remain reviewable rather than being merged automatically.

The matching engine must preserve the separate meanings of official `Device`, observed `DiscoveredDevice`, and staged `ImportedDevice`. A staged row is never inventory until an authorized transactional workflow explicitly creates or merges it.

## Security considerations

- Upload and review endpoints will be administrator-only when introduced.
- Future storage must use generated filenames outside web-accessible paths; original names are display metadata only.
- Size and extension checks are necessary but insufficient: parsers must also enforce MIME/signature, decompression, row, column, cell-length, and formula limits.
- Excel formulas, macros, external links, embedded objects, and CSV formula prefixes must be treated as untrusted input.
- `raw_data` must never contain uploaded file bytes, credentials, tokens, secrets, or unbounded values.
- Errors and audit descriptions must avoid row dumps and sensitive source contents.
- Parsing must not execute macros, shell commands, formulas, external fetches, or embedded relationships.
- Matching and approval must use transactions, database uniqueness, role checks, audit records, and idempotency controls.

## Configuration foundation

The non-secret settings namespace reserves:

- `import.maximum_import_file_size` — default 10 MiB
- `import.supported_formats` — default `csv,xlsx`
- `import.duplicate_matching_enabled` — default enabled for the future matcher
- `import.import_batch_size` — default 500 rows

These values are backend-only in Epic 2A and do not enable importing.
