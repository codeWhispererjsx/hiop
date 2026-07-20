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

These values were backend-only in Epic 2A. Epic 2B uses them to bound upload and parsing work.

## Epic 2B supported formats and upload lifecycle

Device inventory imports accept UTF-8 CSV (including BOM, comma or semicolon delimiters) and Office Open XML `.xlsx`. Legacy `.xls`, macro-enabled workbooks, PDFs, images, executables, generic ZIP archives, unsupported Office formats, empty files, corrupt/password-protected workbooks, and extension/content mismatches are rejected.

CSV uses Python's standard library. XLSX uses pinned `openpyxl 3.1.5` with pinned `et-xmlfile 2.0.0`; pandas is intentionally not added.

An administrator uploads multipart file content. HIOP reads at most the configured size plus one byte, validates extension, declared content type, and file signature, then writes it under a generated UUID name in the operating system temporary directory. The original basename is metadata only and no server path is returned. Valid upload creates an audited `uploaded` session and returns a bounded mapping/row preview. Temporary files are removed after validation, failure, or cancellation.

Validation moves a session through `validating` and `processing`, stages rows in configured batches, and finalizes as `completed`, `partial`, or `failed`. A session already validating or processing rejects concurrent work. Row failures do not create official inventory and do not necessarily abort other rows.

## Column aliases and mapping

Headers are Unicode-normalized, trimmed, case-folded, and whitespace-normalized. Maintained aliases cover asset tag, hostname, IP, MAC, department, building, floor, room/location, network zone, vendor, brand, model, serial number, inventory status, and notes. Asset tag and hostname are required for a processable device row; other fields remain optional and are never invented.

Upload detection returns raw headers, suggested source-to-canonical mappings, unknown columns, missing required fields, ambiguous targets, worksheet names, and a limited preview. Multiple source columns targeting one canonical field are ambiguous and block processing. The mapping API validates source headers, canonical targets, uniqueness, required fields, and worksheet selection before saving audited session metadata.

## Row validation and duplicate detection

Rows preserve JSON `raw_data`, normalized canonical values, source row number, structured errors, structured warnings, and validation status. Text is NFKC-normalized, trimmed, whitespace-normalized, length-bounded, and checked for control characters. Hostnames are lower-cased and structurally checked; IPv4 and 48-bit MAC values use canonical formats; asset tags use the HIOP-safe identifier character set; inventory status aliases normalize to Active, Inactive, or Retired. Formulas are never evaluated and become warnings with null staged values.

Within one file, deterministic duplicate evidence is checked in this order: MAC, asset tag, serial number, IP plus hostname, then the exact normalized row. Both records remain staged and the later row records the related source row. No comparison with Device or Discovery occurs in Epic 2B.

## File and parser security

- Maximum bytes, rows, worksheets, columns, cell length, ZIP members, and expanded XLSX bytes are bounded.
- XLSX is opened read-only with formulas visible but not evaluated and external links disabled.
- VBA projects are rejected and no macros, formulas, shell commands, or external relationships execute.
- CSV uses Python's strict parser and UTF-8 only; binary signatures and NUL bytes are rejected.
- Errors expose stable safe messages, never filesystem paths, stack traces, uploaded contents, or library internals.
- Error CSV neutralizes spreadsheet-formula prefixes.

## Epic 2B API

- `POST /api/v1/imports/device-inventory/upload`
- `GET /api/v1/imports/{session_id}`
- `GET /api/v1/imports/{session_id}/columns`
- `POST /api/v1/imports/{session_id}/mapping`
- `POST /api/v1/imports/{session_id}/validate`
- `GET /api/v1/imports/{session_id}/rows`
- `GET /api/v1/imports/{session_id}/errors`
- `GET /api/v1/imports/{session_id}/errors/export`
- `POST /api/v1/imports/{session_id}/cancel`

Admins own mutations. Admins and technicians may read session, mapping, staged rows, and validation errors. There is no destructive delete endpoint.

## Error codes and limitations

Row codes include `required`, `control_character`, `too_long`, `invalid_asset_tag`, `invalid_hostname`, `invalid_ipv4`, `invalid_mac`, `invalid_inventory_status`, `formula_ignored`, `column_count`, and `duplicate_in_file`. Request errors distinguish unsupported/mismatched/empty/oversized files, malformed CSV, corrupt or unsafe workbooks, missing/ambiguous mappings, missing worksheets, active processing, and unknown sessions.

Epic 2B does not implement Discovery matching, inventory matching, hierarchy inference, inventory create/merge, approval, frontend wizard, background workers, or automatic import scheduling.
