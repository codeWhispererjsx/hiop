# Advanced Analytics Processing

## Epic 6C deterministic forecasting

Forecasting uses persisted `AnalyticsAggregate` rows only. Raw SNMP samples and external services are never queried by the forecast engine.

```text
Historical aggregates
  -> history and quality validation
  -> deterministic trend/growth calculation
  -> projection method
  -> residual bounds and confidence
  -> auditable forecast and later actual-value evaluation
```

Supported methods are:

- Linear regression: least-squares slope/intercept with fit residual and R-squared stability.
- Moving average: equal-weight recent-window level projection.
- Weighted moving average: linearly increasing weights favoring recent buckets.
- Simple exponential smoothing: configurable alpha with no seasonal or learned model.
- Growth percentage: compound per-bucket growth derived from the first and last valid values.

Every stored forecast records the method, historical and forecast periods, prediction points, projected value, deterministic lower/upper bounds, per-bucket growth, direction, confidence, risk, sample count, quality, calculation version, and assumptions.

Growth rates are normalized into hourly, daily, weekly, and monthly percentages from the selected aggregate bucket. Seasonal comparison is descriptive only and is returned when two complete supported periods exist; it does not alter the projection silently.

Confidence ranges from 0 to 100 and combines sample count, proportion of good aggregate buckets, method stability, and coefficient of variation. It is not a probability or guarantee. Forecasts are rejected when the metric is unsupported, history is missing, the method lacks its required samples, fewer than half of usable buckets are good, or historical variance is excessive.

Risk is a deterministic interpretation of the projected value against reviewed metric thresholds, scaled by forecast confidence. It creates no alert and makes no business recommendation.

Forecast evaluation compares a completed forecast with the first eligible aggregate at or after its forecast horizon. It stores actual value, signed error, and absolute percentage-based accuracy. A missing actual remains explicitly unevaluated.

Forecast APIs:

- `GET /analytics/forecasts`
- `GET /analytics/entities/{entity_type}/{entity_id}/forecast`
- `POST /analytics/forecast/run` (Admin)
- `GET /analytics/forecast/history`
- `POST /analytics/forecasts/{id}/evaluate` (Admin)
- `GET /analytics/forecast-summary`
- `GET /analytics/forecast-report`

Troubleshooting: use hourly or daily aggregates with at least the method minimum sample count, verify aggregate quality, and shorten the historical period if unrelated operating regimes create excessive variance. Forecasting remains deterministic statistics—not AI, machine learning, anomaly detection, remediation, or an alert source.

## Epic 6B scheduled processing

Epic 6B adds one reconciled APScheduler job per analytics responsibility: aggregation, availability, health score, capacity, SLA, reliability, data quality, and retention cleanup. Job IDs are deterministic (`analytics_<type>`), jobs coalesce missed executions, use jitter, permit one instance, and remain isolated from SNMP, topology, AD, Discovery, and network-scan jobs. Analytics scheduling remains disabled until an administrator enables the singleton schedule.

Startup reconciliation removes obsolete jobs, recreates enabled jobs without duplication, and safely fails stale active runs. Pause removes analytics jobs without altering other scheduler work; resume rebuilds only configured analytics jobs.

## Incremental processing, backfill, and retention

`AnalyticsCheckpoint` tracks the completed timestamp for a metric, entity scope, bucket size, and calculation type. Scheduled aggregation starts at the checkpoint minus the late-data overlap and updates canonical buckets. Weighted rollups preserve sample counts, minimum, maximum, sum, latest, and quality.

Backfill preview and execution require bounded types, entity scope, timezone-aware range, bucket sizes, and limits. Only one backfill is active at a time; cancellation is cooperative and progress is persisted. Trend APIs return bounded series, summaries, units, quality, and optional equal-length previous-period comparison.

`AnalyticsRetentionPolicy` controls retention by record type and optional bucket. Preview reports eligible counts and cutoffs. Confirmed cleanup deletes in batches while preserving audit and operational source data.

## Purpose and architecture

Epic 6A adds an explainable PostgreSQL analytics domain over existing HIOP operational evidence. It does not introduce a second database, duplicate raw monitoring data, schedule analytics, forecast values, detect anomalies, or use AI.

```text
Operational data
  → controlled source mapping
  → normalized numeric samples/status timelines
  → idempotent time buckets and data quality
  → availability, health, capacity, SLA, and reliability measurements
  → bounded APIs and future dashboards
```

The source adapter boundary in `AnalyticsAggregationService` permits a future time-series backend without changing analytics definitions or derived-domain contracts.

## Source data and controlled mappings

Only fixed application mappings may load source values. No API accepts SQL, expressions, executable transforms, arbitrary tables, or raw OIDs.

Initial approved mappings include SNMP response time, uptime, CPU, memory, and interface utilization, plus network-scan response time. Future mappings may safely add device status history, topology state, alert duration, and ticket resolution evidence.

Default status precedence for availability is:

1. Confirmed monitoring status.
2. SNMP availability.
3. Network scan status.
4. Inventory status.
5. Unknown.

Unknown time is stored separately and never counted as available. Approved SNMP/topology maintenance windows may be excluded when configured.

## Metric definitions and aggregation

`AnalyticsMetricDefinition` describes a controlled source, entity, unit, numeric type, aggregation, direction, and optional bounds. `AnalyticsAggregate` stores one canonical metric/entity/bucket using a unique constraint. Supported bucket sizes are 5 minutes, 15 minutes, 1 hour, 1 day, 1 week, and 1 month.

Each aggregate contains count, minimum, maximum, average, sum, latest, P50, P95, P99, quality, source first/last timestamps, and calculation time. Recalculation updates the canonical bucket. Late samples are incorporated on recalculation rather than creating duplicates. Queries enforce UTC-aware ranges, configured maximum days, pagination, and maximum returned points.

## Availability and maintenance

Availability builds ordered, non-overlapping intervals. Available, unavailable, maintenance, and unknown seconds are preserved. Availability percentage uses measurable time only:

```text
available / (available + unavailable) × 100
```

If no measurable evidence exists, availability is unknown rather than 100%. Outage count increments on transitions into a confirmed unavailable interval and longest-outage duration is retained.

## Explainable health scores

Health scores contain availability, performance, reliability, alert, capacity, topology, and data-quality components. Administrator configurations assign non-negative weights that are normalized across components with evidence. Missing components lower coverage; they are not scored as failures. If coverage is below the configured minimum, status is `unknown` even when available components score highly.

Statuses are `excellent`, `healthy`, `warning`, `degraded`, `critical`, and `unknown`. Each score stores contributing factors, normalized weights, calculation version, calculation time, and validity time. These are deterministic rules, not AI.

## Capacity indicators

Capacity policies bind an approved metric key to warning/critical thresholds, minimum duration, evaluation window, sample count, and scope. Policies are disabled by default. Assessments store current, average, peak, P95, breach duration, sample count, quality, threshold status, and a safe explanation. The foundation makes no forecast or automatic recommendation.

## SLA measurements

SLA definitions cover availability, response time, and incident-resolution targets for reviewed scopes. Definitions are disabled by default and do not implement billing or penalties. Measurements record the inputs, incident counts, resolved counts, target outcome, quality, and explicit breach/unknown reasons. Unknown required evidence produces an unknown outcome rather than a false pass.

## MTTR, MTBF, and reliability assumptions

A failure is a confirmed unavailable interval supported by monitoring evidence. Recovery closes an unavailable interval. MTTR is total completed outage duration divided by resolved outages. MTBF is measured uptime divided by confirmed failures. With no failures or insufficient observation time, MTTR/MTBF remain null. Unresolved incidents do not contribute a completed MTTR duration. Acknowledgement/detection means are populated only when source timestamps support them.

## Manual runs

`POST /api/v1/analytics/run` accepts a bounded run type, scope, timezone-aware period, optional entity IDs, dry-run flag, and maximum entities. Dry run is the default and persists no derived values. Active duplicate scope runs are rejected and cancellation is cooperative. Execution uses the existing FastAPI background-task facility; Epic 6A registers no APScheduler job.

WebSocket events contain only run IDs, types, states, and summarized counts. Audit records are per configuration/run action, never per aggregate row.

## APIs

- Metric definitions: `GET/POST /analytics/metric-definitions`, `PATCH /analytics/metric-definitions/{id}`
- Aggregates/time series: `GET /analytics/aggregates`, `GET /analytics/time-series`
- Availability: `GET /analytics/availability`, entity availability
- Health: list, current entity health, entity history, configuration CRUD
- Capacity: assessments and policy CRUD
- SLA: definition CRUD and measurement list
- Reliability: measurement list
- Runs: create, list, detail, cancel
- Summary: system and entity summaries

Mutation requires Admin. Read access permits Admin and Technician. Backend authorization remains authoritative.

## Security, performance, and retention

All query ranges, pages, points, entities, samples, metric keys, scopes, thresholds, and manual runs are bounded. Derived rows contain no credentials or arbitrary raw payloads. Entity references intentionally avoid cascading deletion so historical measurements survive source retirement.

Indexes cover metric/time, entity/time, policy/time, health/time, run status/time, and data-quality time. Retention settings exist for future manual/automated cleanup, but Epic 6A schedules no retention job.

## Known limitations and Epic 6B

Initial persisted execution is focused on approved numeric aggregation; availability, health, capacity, SLA, and reliability services provide deterministic calculation foundations and require explicit source/entity orchestration in later work. There is no analytics dashboard, forecasting, machine learning, anomaly detection, recommendation engine, real hotel benchmark, billing, or scheduled analytics. Epic 6B should build reviewed analytics workflows and visualization over these bounded contracts.
