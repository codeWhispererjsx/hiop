# HIOP Bug Tracker

## Epic 2E known limitations

- Finalization is synchronous within the API process; session/result persistence makes refresh safe, but process-crash recovery requires an administrator to inspect persisted state.
- Rollback is deliberately all-safe-or-refuse and uses compensation; later inventory edits block it.
- Frontend component-test infrastructure is not configured. Backend contract and service tests cover the finalization boundary.

## Version 1.0.0 release-candidate register

| ID | Module | Severity | Description | Root cause | Resolution | Status |
| --- | --- | --- | --- | --- | --- | --- |
| RC-001 | Release metadata | Medium | Frontend package metadata identified the application as `0.0.0`. | Vite starter metadata was never aligned with backend/deployment versioning. | Updated `package.json` and lock metadata to `1.0.0`; added a checklist version gate. | Fixed |
| RC-002 | Application shell | Medium | Sidebar claimed the entire system was operational and recently synchronized without reading a health source. | Early visual placeholder copy survived feature integration. | Replaced it with the real authenticated WebSocket connection state and honest reconnect messaging. | Fixed |
| RC-003 | Network security | High | A device record outside the approved CIDR could be passed to single-device scan, although range scans were scoped. | Approved-network validation existed only in the range route. | Enforced CIDR membership before every single-device scan and added regression coverage. | Fixed |
| RC-004 | Documentation | Medium | Architecture, API, and database documents described obsolete technologies, roles, fields, and endpoints. | Initial design documents were not reconciled with completed epics. | Rewrote the core technical contract and added role-specific 1.0.0 guides and release documentation. | Fixed |
| RC-005 | Repository hygiene | Low | Starter SVGs, a standalone WebSocket debug page, and stale missing-API notes remained tracked. | Development artifacts were not removed during earlier phases. | Removed verified-unused text assets and consolidated gaps into release/status documentation. | Fixed |
| RC-006 | Release tagging | Medium | `v1.0.0` already points to older commit `1a37fbb`, before security, deployment, and RC work. | A final-version tag was published before the release-candidate branch completed. | Documented the conflict; do not force-move the tag without explicit release-owner authorization. | Decision required |
| RC-007 | Frontend build | Medium | Missing `ImportWizardPage.tsx` and `imports.css` caused Vite import resolution failures. | Import wizard components were staged but the page file and stylesheet were not created. | Created `ImportWizardPage.tsx` and `frontend/src/styles/imports.css`. | Fixed |
| RC-008 | Development environment | Low | `.env.development` referenced port `8000` while the API consistently used port `8001`. | Environment configuration was not aligned with the development server default. | Updated `.env.development` to use port `8001`. | Fixed |
| RC-009 | Version alignment | Medium | Backend `.env.example` and `docs/Architecture.md` referenced `2.0.0-dev` instead of `1.0.0`. | Version strings were not updated during release preparation. | Updated all version references to `1.0.0`. | Fixed |

## Sprint 11.1 stabilization register

| ID | Module | Severity | Description | Root cause | Resolution | Status |
| --- | --- | --- | --- | --- | --- | --- |
| QA-001 | Shared frontend data | High | Details views could retain data from a previously visited route when a request dependency such as an entity ID changed. | `useRequest` accepted dependencies but did not include them in its effect lifecycle. | Added a stable dependency key so dependency changes trigger a fresh request while preserving abort cleanup. | Fixed |
| QA-002 | WebSocket / application shell | High | Normal React renders could tear down and recreate the dashboard WebSocket connection. | The connection effect depended on callback identities supplied by individual pages. | Store live callbacks in refs and keep one connection lifecycle per mounted application shell. | Fixed |
| QA-003 | Users and Audit APIs | Medium | Legacy user and audit handlers overlapped the authoritative feature routers and created inconsistent behavior depending on route registration order. | Older compatibility endpoints remained in `operations/routes.py` after dedicated modules were introduced. | Removed the duplicate handlers; dedicated Users and Audit routers are now the single owners. | Fixed |
| QA-004 | Authentication | Medium | An obsolete staff registration endpoint bypassed the completed administrator user-management workflow. | The early `/auth/register` route remained after admin-only user creation was implemented. | Removed the obsolete endpoint and its unused imports. User creation remains admin-controlled under `/api/v1/users`. | Fixed |
| QA-005 | Scheduler | Low | Scheduler startup and scan failures wrote directly to standard output. | Temporary `print` statements were left in production service code. | Replaced them with structured module logging and exception logging. | Fixed |
| QA-006 | Frontend API contract | Low | The shared endpoint catalog still exposed the removed registration endpoint. | Dead client API metadata remained after the workflow changed. | Removed the unused endpoint entry. | Fixed |
| QA-007 | Local runtime verification | Medium | Browser requests to the original development backend port could be intercepted by an orphaned Windows listener. | The operating system reported a listening socket for a PID absent from the process table. | Development configuration now consistently uses port `8001`; the real API, browser, PostgreSQL workflows, and WebSocket were verified there. Production remains same-origin behind Nginx. | Mitigated/verified |
| QA-008 | Test tooling | Low | Running unscoped `unittest discover` can traverse the local virtual environment and appear to hang. | Discovery was started above the project test directory. | Standardized the verification command on `python -m unittest discover -s tests -v`. | Fixed/documented |
| QA-009 | Frontend build performance | Low | Vite reports that the CSS transform is the slowest build phase. | The application has a large shared stylesheet and Vite reports performance diagnostics for it. | Production output remains valid; stylesheet modularization is deferred because it is technical debt rather than a correctness defect. | Open technical debt |

## Remaining issues at release

| ID | Module | Severity | Description | Impact | Recommendation |
| --- | --- | --- | --- | --- | --- |
| RC-006 | Release tagging | Medium | The `v1.0.0` tag already exists on an older commit before security, deployment, and RC work. | Cannot create a clean `v1.0.0` tag without force-push or using a different version string. | Release owner to decide: force-move tag, or use `v1.0.0-rc1` for this release. |
| QA-009 | Frontend build | Low | CSS transform is the slowest Vite build phase (open technical debt). | Build time impact only. | Defer to post-1.0.0; no correctness or production impact. |

Audit records in this file describe verified defects only. Feature requests and missing future capabilities remain in `PROJECT_STATUS.md`.
## Epic 4B verification notes

- Docker image verification depends on a running Docker Desktop Linux engine.
- Existing Pydantic v1-style config and Starlette TestClient deprecation warnings remain non-blocking.
- Real SNMP agent interoperability is intentionally unverified until an explicitly approved safe fixture or target is supplied.
