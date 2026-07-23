# HIOP Enterprise Security Report

## Epic 3A Active Directory integration controls

Active Directory connection configuration and bind secret management are restricted to administrators. Bind secrets are write-only, encrypted at rest with authenticated Fernet encryption, and never returned in API responses, serialized schemas, or audit log entries. Administrators and technicians have read-only access; staff are denied. Configuration validates domains, hosts, ports, timeouts, search bases, and mutually exclusive TLS modes. Live network execution remains disabled.

## Epic 2E import controls

Finalization, disposition changes, retry, and rollback require the administrator role. Database row locks, plan versions, unique per-row results, terminal-state checks, and idempotency keys prevent concurrent or duplicate execution. Identifier and hierarchy validation repeat immediately before mutation.

Snapshots contain only bounded inventory values required for compensation. They exclude credentials, tokens, uploaded files, and unrelated records. Rollback refuses later state changes and never deletes audit or import history. Events expose only identifiers, counters, actions, and safe error codes.

## Scope and outcome

Epic 13 reviewed the complete HIOP frontend and backend authentication flow, role enforcement, input schemas, SQL access, browser rendering, CORS, exports, WebSockets, secrets configuration, password handling, logging, database sessions, and dependencies. The pass did not add business functionality or redesign the application.

## Findings and remediation

| ID | Severity | Area | Finding | Fix applied | Status |
| --- | --- | --- | --- | --- | --- |
| SEC-001 | High | WebSocket | `/ws/dashboard` accepted anonymous subscriptions to operational events. | The handshake now requires a valid JWT belonging to an active user. The browser supplies it through an agreed WebSocket subprotocol rather than the URL, and rejected clients receive close code `4401`. | Fixed |
| SEC-002 | High | Authentication | Login had no brute-force control. | Added a thread-safe failed-attempt limiter: ten failed attempts per client in five minutes, generic `429` response, and `Retry-After`. Successful authentication clears that client's failures. | Fixed |
| SEC-003 | Medium | JWT | Access tokens had a fixed 24-hour lifetime and only an expiry claim. | Lifetime is now configurable through `ACCESS_TOKEN_EXPIRE_MINUTES`, defaults to 60 minutes, and is constrained to 5–1440 minutes. Tokens include issuer, issued-at, expiry, and unique token ID; validation requires the HIOP issuer. | Fixed |
| SEC-004 | Medium | Secrets | Production could start with an undersized signing secret. | Non-debug startup now rejects signing secrets shorter than 32 characters. Secret values remain environment-only and are never returned to clients. | Fixed |
| SEC-005 | Medium | Browser session | JWTs persisted indefinitely in `localStorage`, increasing exposure after the browser session ended. | Tokens now use `sessionStorage`, persist across refresh within the tab, are cleared on logout/401/expiry, and legacy local tokens are migrated then removed. | Fixed |
| SEC-006 | Medium | Input validation | Device, ticket, scan-history, and password inputs accepted overly broad or unbounded values. | Added field lengths, enum restrictions, whitespace normalization, IPv4/IPv6 parsing, MAC normalization, CIDR parsing, scan-history bounds, and password complexity for creation/reset. Login passwords are capped to limit hashing abuse. | Fixed |
| SEC-007 | Medium | Authorization | Alert acknowledgement and generic ticket update allowed any authenticated legacy role. | Both mutations now require admin or technician. Existing admin-only device retirement, user management, audit, reports, settings, and hierarchy mutation enforcement remains on the backend. | Fixed |
| SEC-008 | Medium | Authorization UI | Technicians could see navigation and inventory controls that the backend would reject. | Admin-only navigation is hidden for non-admin roles. Device creation and retirement are shown only to admins; editing remains available to admins and technicians. Backend checks remain authoritative. | Fixed |
| SEC-009 | Medium | Export | User-controlled CSV cells could be interpreted as spreadsheet formulas. | Audit and report exports prefix cells beginning with `=`, `+`, `-`, or `@`, while retaining generated safe filenames. | Fixed |
| SEC-010 | Medium | HTTP hardening | API responses lacked explicit anti-sniffing, framing, referrer, permissions, and cache directives. | Added `nosniff`, `DENY` framing, no-referrer, restrictive permissions policy, API `no-store`, and HSTS for HTTPS requests. | Fixed |
| SEC-011 | Low | CORS | The bearer-token API allowed credentials and all methods/headers despite not using cookies. | Disabled credentialed CORS and restricted methods and headers to the exact application requirements. Origins remain explicitly allowlisted. | Fixed |
| SEC-012 | Low | Authentication errors | Invalid, expired, inactive-user, and malformed tokens returned distinguishable credential errors. | Protected APIs now return a consistent `401 Could not validate credentials` with `WWW-Authenticate: Bearer`. | Fixed |

## Authorization policy reviewed

- All module data endpoints require an active authenticated database user; JWT presence in the browser is not backend authorization.
- Admin-only: user management, audit center, reports, settings changes/system health, hierarchy mutations, device creation and retirement, and ticket deletion.
- Admin or technician: device editing/history audit, network scans, alert acknowledgement, ticket editing/assignment/closure.
- Authenticated operational reads and ticket creation remain available according to the existing product policy.
- Backend dependencies remain the source of truth even when the frontend hides controls.

## Injection, rendering, and file review

- Application queries use SQLAlchemy ORM expressions and bound parameters. No request value is concatenated into runtime SQL.
- Raw SQL exists only in fixed Alembic migrations and the constant `SELECT 1` health check; neither accepts client input.
- React renders ticket descriptions, device fields, alerts, audit descriptions, and report values through escaped JSX. No `dangerouslySetInnerHTML` or direct `innerHTML` usage exists.
- No upload functionality exists. Exports are generated in memory, use server-generated filenames, and now neutralize spreadsheet formulas.
- Database sessions close in dependency `finally` blocks. Mutation services use rollback paths and preserve existing transaction boundaries.

## CSRF assessment

HIOP authenticates API calls with a bearer token explicitly placed in the `Authorization` header. It does not authenticate with ambient cookies, and CORS does not allow credentialed cross-origin requests. Conventional browser CSRF protections are therefore not required for the current architecture. If authentication moves to cookies, `SameSite`, secure/HTTP-only cookies, origin validation, and anti-CSRF tokens must be introduced together.

## Password and secret handling

- Passwords use bcrypt through Passlib; only hashes are stored.
- Create/reset schemas enforce 10–128 characters with uppercase, lowercase, and numeric characters.
- Existing passwords and hashes are never returned or prepopulated.
- Login failures remain generic, and passwords/tokens are not written to logs or audit descriptions.
- `.env` files, private keys, virtual environments, caches, and build output are excluded from Git. Only the non-secret `.env.example` template is tracked.

## Dependency review

- `pip check` reports no broken Python requirements.
- Frontend production dependencies remain limited to React, React DOM, and React Router; no package was added for this epic.
- The npm registry audit could not complete because the local corporate TLS chain presents an untrusted self-signed certificate. TLS verification was not disabled. This must be corrected at the workstation or registry-proxy trust store before relying on `npm audit` results.
- Dependency versions remain pinned. A CI vulnerability scanner should evaluate both lockfiles on every change.

## Verification performed

- Frontend ESLint and TypeScript/Vite production build.
- Backend compilation and 16 unit/contract tests, including JWT claims and rejection, throttling, validation, and CSV sanitization.
- Real FastAPI startup and health on the configured local service.
- Successful administrator login and authenticated `/auth/me`.
- Invalid bearer token returns `401` and a Bearer challenge.
- Untrusted-origin CORS preflight returns `400` without an allow-origin header.
- Security response headers are present.
- Anonymous WebSocket handshake is rejected; a valid JWT handshake negotiates `hiop` and receives the connected event.

## Remaining recommendations

- Replace the in-process login limiter with a shared Redis or reverse-proxy limiter before running multiple API workers. Include both per-IP and per-account controls and operational alerting.
- Add server-side session revocation or a denylist for urgent token invalidation. Current stolen tokens remain usable until their maximum one-hour expiry unless the account is deactivated.
- Add refresh-token rotation, MFA, and recovery-code workflows as separately designed authentication features.
- Configure TLS termination, frontend Content Security Policy, host allowlisting, request-size limits, and proxy log redaction at the production reverse proxy. Ensure `Authorization` and `Sec-WebSocket-Protocol` headers are never logged.
- Move production secrets to an external secrets manager and implement signing-key rotation.
- Fix the registry CA trust chain, then run `npm audit`; add pip-audit or another maintained Python advisory scanner in CI.
- Add automated role-matrix integration tests backed by an isolated test database, including technician denial for every admin mutation.
- Consider immutable, centrally shipped security logs and correlation IDs without storing tokens or request bodies.
