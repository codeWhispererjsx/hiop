# HIOP v1.0 Performance Report

## Executive summary

Epic 12 optimized existing execution paths without adding features or changing the visual design. The largest measured improvement is route-level code splitting: the shared initial JavaScript bundle decreased from 379.87 kB (109.51 kB gzip) to 244.79 kB (78.15 kB gzip), approximately 35.6% smaller uncompressed and 28.6% smaller compressed. Individual feature pages now load on demand.

## Optimizations performed

### React and browser work

- Converted all application pages to lazy route imports behind one shared `Suspense` loading state.
- Preserved the single application-shell WebSocket lifecycle established during stabilization; lazy route changes do not create a second subscription.
- Added deferred search values to Devices, Tickets, and Alerts so input updates remain responsive while larger client-side result sets are filtered.
- Retained existing `useMemo` indexes, filtered datasets, and paginated slices rather than adding redundant memoization.
- Added request-version protection to `useRequest`; late responses no longer update an unmounted view or overwrite a newer request.

### API and resource usage

- Added in-flight GET coalescing keyed by authenticated user and request path. Concurrent consumers share the same promise, while completed results are not held as a potentially stale cache.
- Requests with an `AbortSignal` remain independently cancellable.
- Mutation requests are never coalesced, preserving submission and authorization behavior.
- Existing WebSocket retry timers and toast timers retain explicit cleanup.

### Backend queries

- Dashboard device metrics now use one conditional aggregate instead of three count queries.
- Dashboard ticket metrics now use one conditional aggregate instead of three count queries.
- Including last-scan time, the dashboard service decreased from seven database round trips to three.
- Audit summary metrics now use one conditional aggregate instead of six separate count queries.
- The Audit "today" condition now uses a timestamp range boundary rather than applying `date()` to every stored timestamp, allowing the timestamp index to participate.

### PostgreSQL indexes

Alembic revision `a71c8d9e4f20` adds indexes for verified access patterns:

- `devices.hostname`
- `devices.ip_address`
- `tickets.status`
- `alerts (acknowledged, created_at)`
- `audit_logs.created_at`
- `network_scans.scanned_at`
- `network_scans (device_id, scanned_at)`

No duplicate indexes were added for `devices.asset_tag` or `users.email`; their existing unique constraints already provide indexed lookup in PostgreSQL.

## Verification and measured impact

| Area | Before | After | Impact |
| --- | ---: | ---: | --- |
| Shared initial JavaScript | 379.87 kB | 244.79 kB | 35.6% reduction |
| Shared initial JavaScript (gzip) | 109.51 kB | 78.15 kB | 28.6% reduction |
| Dashboard DB round trips | 7 | 3 | 57% reduction |
| Audit summary queries | 6 | 1 | 83% reduction |
| Route page loading | All pages eager | Per-route chunks | Lower initial parse/evaluation work |
| Concurrent identical GETs | One request per consumer | One shared in-flight request | Duplicate network work eliminated |

Frontend ESLint and the production build pass. All 10 backend contract tests pass. Alembic reports `a71c8d9e4f20` as the current head. Authenticated browser checks passed for Dashboard, Devices, Network, Alerts, Tickets, Users, Audit, Reports, Settings, and Locations & Structure after restarting the optimized backend.

## Remaining bottlenecks and opportunities

- The application still has a 91.60 kB shared dashboard stylesheet loaded with authenticated pages. Splitting it by design-system layer and feature should be benchmarked before changing the established cascade.
- Devices, Alerts, and Tickets currently load complete collections because their established APIs and client filters require them. Server pagination and server search would be the next scaling step when record counts materially grow, but that would be an API feature change and is outside this optimization-only epic.
- Audit filter options require three distinct-value queries per response. A separately cached metadata endpoint could reduce work at very large audit volumes, but would change the API contract.
- Report generation builds relationship maps in memory. This avoids N+1 queries and is appropriate for current volumes; large deployments should move exports to streamed/background jobs.
- No persistent browser response cache was introduced because operational and authorization data must remain current. Future caching should use endpoint-specific invalidation rather than a global TTL.
- Table virtualization is not justified for existing ten-row paginated views. Reassess only if page sizes increase substantially.
- Production measurement should add browser Core Web Vitals, API latency percentiles, PostgreSQL `EXPLAIN ANALYZE` sampling, and connection-pool metrics using representative production volumes.
