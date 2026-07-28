"""Authenticated and bounded advanced analytics foundation APIs."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_db, require_roles
from app.models.analytics import (
    AnalyticsAggregate, AnalyticsAvailability, AnalyticsDataQualityRecord, AnalyticsMetricDefinition,
    AnalyticsRetentionPolicy, AnalyticsRun, AnalyticsScheduleConfiguration,
    CapacityAssessment, CapacityPolicy, EntityHealthScore, HealthScoreConfiguration,
    ReliabilityMeasurement, SLADefinition, SLAMeasurement,
)
from app.schemas.analytics import (
    AnalyticsBackfillRequest, AnalyticsRunRequest, AnalyticsScheduleRead, AnalyticsScheduleWrite,
    CapacityPolicyRead, CapacityPolicyWrite, HealthConfigurationRead, RetentionCleanupRequest,
    HealthConfigurationWrite, MetricDefinitionRead, MetricDefinitionUpdate, MetricDefinitionWrite,
    SLADefinitionRead, SLADefinitionWrite,
)
from app.services.analytics_aggregation_service import AnalyticsAggregationService
from app.services.analytics_run_service import execute_analytics_run
from app.services.analytics_operational_service import AnalyticsOperationalService
from app.services.audit_service import create_audit_log

router = APIRouter(prefix="/analytics", tags=["Analytics"])
admin, reader = require_roles(["admin"]), require_roles(["admin", "technician"])


def _page(query, schema=None, number=1, size=50):
    total = query.count(); rows = query.offset((number - 1) * size).limit(size).all()
    return {"items": [schema.model_validate(row) for row in rows] if schema else rows, "total": total, "page": number, "page_size": size}


def _get(db, model, object_id, label):
    row = db.get(model, object_id)
    if not row: raise HTTPException(404, f"{label} was not found.")
    return row


def _audit(db, actor, action, row, description):
    create_audit_log(db, actor.username, action, row.__class__.__name__, str(row.id), description)
    db.commit(); db.refresh(row); return row


@router.get("/metric-definitions")
def definitions(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), _=Depends(reader)):
    return _page(db.query(AnalyticsMetricDefinition).order_by(AnalyticsMetricDefinition.metric_key), MetricDefinitionRead, page, page_size)


@router.post("/metric-definitions", response_model=MetricDefinitionRead, status_code=201)
def create_definition(payload: MetricDefinitionWrite, db: Session = Depends(get_db), actor=Depends(admin)):
    if db.scalar(select(AnalyticsMetricDefinition).where(AnalyticsMetricDefinition.metric_key == payload.metric_key)): raise HTTPException(409, "Analytics metric key already exists.")
    row = AnalyticsMetricDefinition(**payload.model_dump()); db.add(row); db.flush()
    return _audit(db, actor, "ANALYTICS_METRIC_CREATED", row, f"Created controlled analytics metric '{row.metric_key}'.")


@router.patch("/metric-definitions/{object_id}", response_model=MetricDefinitionRead)
def update_definition(object_id: UUID, payload: MetricDefinitionUpdate, db: Session = Depends(get_db), actor=Depends(admin)):
    row = _get(db, AnalyticsMetricDefinition, object_id, "Analytics metric definition")
    for key, value in payload.model_dump(exclude_unset=True).items(): setattr(row, key, value)
    return _audit(db, actor, "ANALYTICS_METRIC_UPDATED", row, f"Updated analytics metric '{row.metric_key}'.")


@router.get("/aggregates")
def aggregates(metric_definition_id: UUID | None = None, entity_type: str | None = None, entity_id: UUID | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), _=Depends(reader)):
    query = db.query(AnalyticsAggregate)
    if metric_definition_id: query = query.filter_by(metric_definition_id=metric_definition_id)
    if entity_type: query = query.filter_by(entity_type=entity_type)
    if entity_id: query = query.filter_by(entity_id=entity_id)
    return _page(query.order_by(AnalyticsAggregate.bucket_start.desc()), None, page, page_size)


@router.get("/time-series")
def time_series(metric_key: str, entity_type: str, start: datetime, end: datetime, bucket_size: str = "1_hour", aggregation: str = "average", entity_id: UUID | None = None, quality: str | None = None, db: Session = Depends(get_db), _=Depends(reader)):
    AnalyticsAggregationService.validate_range(start, end)
    definition = db.scalar(select(AnalyticsMetricDefinition).where(AnalyticsMetricDefinition.metric_key == metric_key, AnalyticsMetricDefinition.enabled.is_(True)))
    if not definition or definition.entity_type != entity_type: raise HTTPException(404, "Enabled analytics metric mapping was not found for this entity type.")
    query = db.query(AnalyticsAggregate).filter(AnalyticsAggregate.metric_definition_id == definition.id, AnalyticsAggregate.bucket_size == bucket_size, AnalyticsAggregate.bucket_start >= start, AnalyticsAggregate.bucket_end <= end)
    if entity_id: query = query.filter_by(entity_id=entity_id)
    if quality: query = query.filter_by(quality=quality)
    rows = query.order_by(AnalyticsAggregate.bucket_start).limit(settings.analytics_maximum_time_series_points + 1).all()
    if len(rows) > settings.analytics_maximum_time_series_points: raise HTTPException(413, "Time-series result exceeds configured point limit.")
    field = {"average": "average_value", "minimum": "minimum_value", "maximum": "maximum_value", "sum": "sum_value", "latest": "latest_value", "percentile": "percentile_95"}.get(aggregation)
    if not field: raise HTTPException(400, "Unsupported time-series aggregation.")
    return {"metric_key": metric_key, "entity_type": entity_type, "entity_id": entity_id, "unit": definition.unit, "bucket_size": bucket_size, "aggregation": aggregation, "points": [{"timestamp": row.bucket_start, "value": getattr(row, field), "quality": row.quality, "sample_count": row.sample_count} for row in rows], "quality": {name: sum(row.quality == name for row in rows) for name in ("good", "partial", "poor", "insufficient", "unknown")}, "generated_at": datetime.now(timezone.utc)}


@router.get("/availability")
def availability(entity_type: str | None = None, entity_id: UUID | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), _=Depends(reader)):
    query = db.query(AnalyticsAvailability)
    if entity_type: query = query.filter_by(entity_type=entity_type)
    if entity_id: query = query.filter_by(entity_id=entity_id)
    return _page(query.order_by(AnalyticsAvailability.period_end.desc()), None, page, page_size)


@router.get("/entities/{entity_type}/{entity_id}/availability")
def entity_availability(entity_type: str, entity_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    return db.scalar(select(AnalyticsAvailability).where(AnalyticsAvailability.entity_type == entity_type, AnalyticsAvailability.entity_id == entity_id).order_by(AnalyticsAvailability.period_end.desc())) or {}


@router.get("/health")
def health(entity_type: str | None = None, status: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), _=Depends(reader)):
    query = db.query(EntityHealthScore)
    if entity_type: query = query.filter_by(entity_type=entity_type)
    if status: query = query.filter_by(status=status)
    return _page(query.order_by(EntityHealthScore.calculated_at.desc()), None, page, page_size)


@router.get("/entities/{entity_type}/{entity_id}/health")
def entity_health(entity_type: str, entity_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    return db.scalar(select(EntityHealthScore).where(EntityHealthScore.entity_type == entity_type, EntityHealthScore.entity_id == entity_id).order_by(EntityHealthScore.calculated_at.desc())) or {}


@router.get("/entities/{entity_type}/{entity_id}/health-history")
def health_history(entity_type: str, entity_id: UUID, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), _=Depends(reader)):
    return _page(db.query(EntityHealthScore).filter_by(entity_type=entity_type, entity_id=entity_id).order_by(EntityHealthScore.calculated_at.desc()), None, page, page_size)


def _crud_routes():
    return


@router.get("/health-configurations")
def health_configurations(db: Session = Depends(get_db), _=Depends(reader)): return _page(db.query(HealthScoreConfiguration).order_by(HealthScoreConfiguration.name), HealthConfigurationRead, 1, 100)


@router.post("/health-configurations", response_model=HealthConfigurationRead, status_code=201)
def create_health_configuration(payload: HealthConfigurationWrite, db: Session = Depends(get_db), actor=Depends(admin)):
    row = HealthScoreConfiguration(**payload.model_dump(), created_by=actor.id, updated_by=actor.id); db.add(row); db.flush()
    return _audit(db, actor, "ANALYTICS_HEALTH_CONFIGURATION_CREATED", row, f"Created health configuration '{row.name}'.")


@router.patch("/health-configurations/{object_id}", response_model=HealthConfigurationRead)
def update_health_configuration(object_id: UUID, payload: HealthConfigurationWrite, db: Session = Depends(get_db), actor=Depends(admin)):
    row = _get(db, HealthScoreConfiguration, object_id, "Health configuration")
    for key, value in payload.model_dump().items(): setattr(row, key, value)
    row.updated_by = actor.id
    return _audit(db, actor, "ANALYTICS_HEALTH_CONFIGURATION_UPDATED", row, f"Updated health configuration '{row.name}'.")


@router.get("/capacity")
def capacity(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), _=Depends(reader)): return _page(db.query(CapacityAssessment).order_by(CapacityAssessment.period_end.desc()), None, page, page_size)


@router.get("/capacity-policies")
def capacity_policies(db: Session = Depends(get_db), _=Depends(reader)): return _page(db.query(CapacityPolicy).order_by(CapacityPolicy.name), CapacityPolicyRead, 1, 100)


@router.post("/capacity-policies", response_model=CapacityPolicyRead, status_code=201)
def create_capacity_policy(payload: CapacityPolicyWrite, db: Session = Depends(get_db), actor=Depends(admin)):
    row = CapacityPolicy(**payload.model_dump(), created_by=actor.id, updated_by=actor.id); db.add(row); db.flush()
    return _audit(db, actor, "ANALYTICS_CAPACITY_POLICY_CREATED", row, f"Created disabled capacity policy '{row.name}'.")


@router.patch("/capacity-policies/{object_id}", response_model=CapacityPolicyRead)
def update_capacity_policy(object_id: UUID, payload: CapacityPolicyWrite, db: Session = Depends(get_db), actor=Depends(admin)):
    row = _get(db, CapacityPolicy, object_id, "Capacity policy")
    for key, value in payload.model_dump().items(): setattr(row, key, value)
    row.updated_by = actor.id
    return _audit(db, actor, "ANALYTICS_CAPACITY_POLICY_UPDATED", row, f"Updated capacity policy '{row.name}'.")


@router.get("/SLA-definitions")
def sla_definitions(db: Session = Depends(get_db), _=Depends(reader)): return _page(db.query(SLADefinition).order_by(SLADefinition.name), SLADefinitionRead, 1, 100)


@router.post("/SLA-definitions", response_model=SLADefinitionRead, status_code=201)
def create_sla(payload: SLADefinitionWrite, db: Session = Depends(get_db), actor=Depends(admin)):
    row = SLADefinition(**payload.model_dump(), created_by=actor.id, updated_by=actor.id); db.add(row); db.flush()
    return _audit(db, actor, "ANALYTICS_SLA_CREATED", row, f"Created disabled SLA '{row.name}'.")


@router.patch("/SLA-definitions/{object_id}", response_model=SLADefinitionRead)
def update_sla(object_id: UUID, payload: SLADefinitionWrite, db: Session = Depends(get_db), actor=Depends(admin)):
    row = _get(db, SLADefinition, object_id, "SLA definition")
    for key, value in payload.model_dump().items(): setattr(row, key, value)
    row.updated_by = actor.id
    return _audit(db, actor, "ANALYTICS_SLA_UPDATED", row, f"Updated SLA '{row.name}'.")


@router.get("/SLA-measurements")
def sla_measurements(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), _=Depends(reader)): return _page(db.query(SLAMeasurement).order_by(SLAMeasurement.period_end.desc()), None, page, page_size)


@router.get("/reliability")
def reliability(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), _=Depends(reader)): return _page(db.query(ReliabilityMeasurement).order_by(ReliabilityMeasurement.period_end.desc()), None, page, page_size)


@router.post("/run", status_code=202)
def run_analytics(payload: AnalyticsRunRequest, tasks: BackgroundTasks, db: Session = Depends(get_db), actor=Depends(admin)):
    if not settings.analytics_enabled: raise HTTPException(409, "Analytics is disabled.")
    AnalyticsAggregationService.validate_range(payload.period_start, payload.period_end)
    recent = db.query(AnalyticsRun).filter(
        AnalyticsRun.triggered_by == actor.id,
        AnalyticsRun.started_at >= datetime.now(timezone.utc) - timedelta(hours=1),
    ).count()
    if recent >= settings.analytics_manual_run_rate_limit_per_hour:
        raise HTTPException(429, "Manual analytics run rate limit exceeded.")
    if db.scalar(select(AnalyticsRun).where(AnalyticsRun.status.in_(("pending", "running")), AnalyticsRun.scope_type == payload.scope_type, AnalyticsRun.scope_id == payload.scope_id)): raise HTTPException(409, "An analytics run is already active for this scope.")
    row = AnalyticsRun(**payload.model_dump(exclude={"entity_ids", "maximum_entities", "recalculate_existing_buckets"}), entities_requested=len(payload.entity_ids), trigger_type="manual", triggered_by=actor.id)
    db.add(row); db.flush(); create_audit_log(db, actor.username, "ANALYTICS_DRY_RUN_REQUESTED" if payload.dry_run else "ANALYTICS_RUN_REQUESTED", "AnalyticsRun", str(row.id), f"Requested bounded {payload.run_type} analytics run.")
    db.commit(); db.refresh(row); tasks.add_task(execute_analytics_run, row.id)
    return {"run_id": row.id, "status": row.status, "dry_run": row.dry_run}


@router.get("/runs")
def runs(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), _=Depends(reader)): return _page(db.query(AnalyticsRun).order_by(AnalyticsRun.started_at.desc()), None, page, page_size)


@router.get("/runs/{run_id}")
def run_detail(run_id: UUID, db: Session = Depends(get_db), _=Depends(reader)): return _get(db, AnalyticsRun, run_id, "Analytics run")


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: UUID, db: Session = Depends(get_db), actor=Depends(admin)):
    row = _get(db, AnalyticsRun, run_id, "Analytics run")
    if row.status not in {"pending", "running"}: raise HTTPException(409, "Only active analytics runs can be cancelled.")
    row.cancellation_requested = True
    if row.status == "pending": row.status = "cancelled"; row.completed_at = datetime.now(timezone.utc)
    return _audit(db, actor, "ANALYTICS_RUN_CANCELLED", row, "Requested cooperative analytics run cancellation.")


@router.post("/runs/{run_id}/retry", status_code=202)
def retry_run(run_id: UUID, tasks: BackgroundTasks, db: Session = Depends(get_db), actor=Depends(admin)):
    source = _get(db, AnalyticsRun, run_id, "Analytics run")
    if source.status not in {"failed", "partial"}: raise HTTPException(409, "Only failed or partial runs can be retried.")
    if source.retry_count >= 3: raise HTTPException(409, "Analytics retry limit reached.")
    row = AnalyticsRun(
        run_type=source.run_type, scope_type=source.scope_type, scope_id=source.scope_id,
        period_start=source.period_start, period_end=source.period_end, dry_run=source.dry_run,
        trigger_type="retry", triggered_by=actor.id, retry_count=source.retry_count + 1,
        bucket_sizes=source.bucket_sizes, result_summary={"retried_from": str(source.id)},
    )
    db.add(row); db.flush(); create_audit_log(db, actor.username, "ANALYTICS_RUN_RETRIED", "AnalyticsRun", str(row.id), "Retried a bounded analytics run.")
    db.commit(); db.refresh(row); tasks.add_task(execute_analytics_run, row.id)
    return {"run_id": row.id, "status": row.status}


@router.get("/runs/{run_id}/progress")
def run_progress(run_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    row = _get(db, AnalyticsRun, run_id, "Analytics run")
    return {"run_id": row.id, "status": row.status, "batches_total": row.batches_total, "batches_completed": row.batches_completed, "records_created": row.records_created, "records_updated": row.records_updated, "records_skipped": row.records_skipped, "errors_count": row.errors_count, "cancellation_requested": row.cancellation_requested}


@router.get("/runs/{run_id}/errors")
def run_errors(run_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    row = _get(db, AnalyticsRun, run_id, "Analytics run")
    return {"run_id": row.id, "error_category": (row.result_summary or {}).get("error_category"), "error_summary": row.error_summary, "errors_count": row.errors_count}


@router.post("/backfill/preview")
def backfill_preview(payload: AnalyticsBackfillRequest, db: Session = Depends(get_db), actor=Depends(admin)):
    result = AnalyticsOperationalService(db).preview_backfill(payload)
    create_audit_log(db, actor.username, "ANALYTICS_BACKFILL_PREVIEWED", "AnalyticsRun", None, "Previewed a bounded analytics backfill.")
    db.commit(); return result


@router.post("/backfill", status_code=202)
def backfill(payload: AnalyticsBackfillRequest, tasks: BackgroundTasks, db: Session = Depends(get_db), actor=Depends(admin)):
    preview = AnalyticsOperationalService(db).preview_backfill(payload)
    if db.scalar(select(AnalyticsRun).where(AnalyticsRun.status.in_(("pending", "running")), AnalyticsRun.trigger_type == "backfill")):
        raise HTTPException(409, "An analytics backfill is already active.")
    row = AnalyticsRun(
        run_type="aggregate" if "aggregate" in payload.analytics_types else payload.analytics_types[0],
        scope_type=payload.entity_type, period_start=payload.period_start, period_end=payload.period_end,
        entities_requested=len(payload.entity_ids), dry_run=payload.dry_run, trigger_type="backfill",
        triggered_by=actor.id, bucket_sizes=payload.bucket_sizes,
        result_summary={"analytics_types": payload.analytics_types, "entity_ids": [str(value) for value in payload.entity_ids], "recalculate": payload.recalculate},
    )
    db.add(row); db.flush(); create_audit_log(db, actor.username, "ANALYTICS_BACKFILL_STARTED", "AnalyticsRun", str(row.id), "Started a bounded analytics backfill.")
    db.commit(); db.refresh(row); tasks.add_task(execute_analytics_run, row.id)
    return {"run_id": row.id, "estimated_entities": preview["entities_affected"], "estimated_buckets": preview["estimated_buckets"], "warnings": preview["warnings"], "status": row.status}


@router.get("/schedule", response_model=AnalyticsScheduleRead)
def schedule(db: Session = Depends(get_db), _=Depends(admin)):
    row = AnalyticsOperationalService(db).schedule(); db.commit(); db.refresh(row); return row


@router.put("/schedule", response_model=AnalyticsScheduleRead)
def update_schedule(payload: AnalyticsScheduleWrite, db: Session = Depends(get_db), actor=Depends(admin)):
    row = AnalyticsOperationalService(db).schedule()
    for key, value in payload.model_dump().items(): setattr(row, key, value)
    db.commit()
    from app.services.scheduler_service import update_analytics_jobs
    update_analytics_jobs(db)
    return _audit(db, actor, "ANALYTICS_SCHEDULE_UPDATED", row, "Updated analytics schedule configuration.")


@router.post("/schedule/pause")
def pause_schedule(db: Session = Depends(get_db), actor=Depends(admin)):
    from app.services.scheduler_service import pause_analytics_jobs
    removed = pause_analytics_jobs(db)
    create_audit_log(db, actor.username, "ANALYTICS_JOBS_PAUSED", "AnalyticsScheduleConfiguration", None, "Paused scheduled analytics jobs."); db.commit()
    return {"paused": True, "jobs_removed": removed}


@router.post("/schedule/resume")
def resume_schedule(db: Session = Depends(get_db), actor=Depends(admin)):
    from app.services.scheduler_service import resume_analytics_jobs
    registered = resume_analytics_jobs(db)
    create_audit_log(db, actor.username, "ANALYTICS_JOBS_RESUMED", "AnalyticsScheduleConfiguration", None, "Resumed scheduled analytics jobs."); db.commit()
    return {"paused": False, "jobs_registered": registered}


@router.get("/scheduler-status")
def scheduler_status(db: Session = Depends(get_db), _=Depends(reader)):
    from app.services.scheduler_service import ANALYTICS_JOB_PREFIX, scheduler
    config = AnalyticsOperationalService(db).schedule()
    jobs = [{"id": job.id, "next_run_time": job.next_run_time} for job in scheduler.get_jobs() if job.id.startswith(ANALYTICS_JOB_PREFIX)]
    active = db.query(AnalyticsRun).filter(AnalyticsRun.status.in_(("pending", "running", "retry_pending"))).count()
    latest = db.scalar(select(AnalyticsRun).where(AnalyticsRun.status == "completed").order_by(AnalyticsRun.completed_at.desc()))
    return {"enabled": config.enabled, "paused": config.paused, "registered_jobs": jobs, "active_runs": active, "last_successful_run": latest, "last_reconciled_at": config.last_reconciled_at}


@router.get("/trends")
def trends(metric_key: str, entity_type: str, start: datetime, end: datetime, bucket_size: str = "1_hour", aggregation: str = "average", entity_id: UUID | None = None, compare_previous_period: bool = False, db: Session = Depends(get_db), _=Depends(reader)):
    AnalyticsAggregationService.validate_range(start, end)
    definition = db.scalar(select(AnalyticsMetricDefinition).where(AnalyticsMetricDefinition.metric_key == metric_key, AnalyticsMetricDefinition.entity_type == entity_type, AnalyticsMetricDefinition.enabled.is_(True)))
    if not definition: raise HTTPException(404, "Enabled analytics metric mapping was not found.")
    result = AnalyticsOperationalService(db).trends(definition, entity_id, start, end, bucket_size, aggregation)
    if compare_previous_period:
        duration = end - start
        previous = AnalyticsOperationalService(db).trends(definition, entity_id, start - duration, start, bucket_size, aggregation)
        current_value, previous_value = result["summary"]["average"], previous["summary"]["average"]
        result["comparison"] = {"previous_summary": previous["summary"], "absolute_difference": current_value - previous_value if current_value is not None and previous_value is not None else None, "change_percent": ((current_value - previous_value) / abs(previous_value) * 100) if current_value is not None and previous_value not in (None, 0) else None}
    return result


@router.get("/data-quality")
def data_quality(metric_key: str | None = None, quality: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), _=Depends(reader)):
    query = db.query(AnalyticsDataQualityRecord)
    if metric_key: query = query.filter_by(metric_key=metric_key)
    if quality: query = query.filter_by(quality_status=quality)
    return _page(query.order_by(AnalyticsDataQualityRecord.period_end.desc()), None, page, page_size)


@router.get("/entities/{entity_type}/{entity_id}/data-quality")
def entity_data_quality(entity_type: str, entity_id: UUID, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), _=Depends(reader)):
    return _page(db.query(AnalyticsDataQualityRecord).filter_by(entity_type=entity_type, entity_id=entity_id).order_by(AnalyticsDataQualityRecord.period_end.desc()), None, page, page_size)


@router.get("/capacity-summary")
def capacity_summary(db: Session = Depends(get_db), _=Depends(reader)):
    counts = dict(db.query(CapacityAssessment.threshold_status, func.count(CapacityAssessment.id)).group_by(CapacityAssessment.threshold_status).all())
    latest = db.scalar(select(func.max(CapacityAssessment.calculated_at)))
    return {"normal_count": counts.get("normal", 0), "warning_count": counts.get("warning", 0), "critical_count": counts.get("critical", 0), "last_calculation": latest}


@router.get("/SLA-summary")
def sla_summary(db: Session = Depends(get_db), _=Depends(reader)):
    total = db.query(SLAMeasurement).count(); met = db.query(SLAMeasurement).filter(SLAMeasurement.target_met.is_(True)).count()
    return {"definitions_measured": db.query(SLAMeasurement.sla_definition_id).distinct().count(), "targets_met": met, "targets_breached": db.query(SLAMeasurement).filter(SLAMeasurement.target_met.is_(False)).count(), "average_availability": db.scalar(select(func.avg(SLAMeasurement.measured_availability_percent))), "last_measurement": db.scalar(select(func.max(SLAMeasurement.calculated_at))), "measurement_count": total}


@router.get("/reliability-summary")
def reliability_summary(db: Session = Depends(get_db), _=Depends(reader)):
    return {"mttr": db.scalar(select(func.avg(ReliabilityMeasurement.mttr_seconds))), "mtbf": db.scalar(select(func.avg(ReliabilityMeasurement.mtbf_seconds))), "mean_acknowledgment_time": db.scalar(select(func.avg(ReliabilityMeasurement.mean_time_to_acknowledge_seconds))), "failure_count": db.scalar(select(func.sum(ReliabilityMeasurement.failure_count))) or 0, "total_downtime": db.scalar(select(func.sum(ReliabilityMeasurement.total_downtime_seconds))) or 0}


@router.get("/retention/preview")
def retention_preview(db: Session = Depends(get_db), actor=Depends(admin)):
    result = AnalyticsOperationalService(db).retention_preview()
    create_audit_log(db, actor.username, "ANALYTICS_CLEANUP_PREVIEWED", "AnalyticsRetentionPolicy", None, "Previewed analytics retention cleanup."); db.commit()
    return result


@router.post("/retention/cleanup")
def retention_cleanup(payload: RetentionCleanupRequest, db: Session = Depends(get_db), actor=Depends(admin)):
    result = AnalyticsOperationalService(db).retention_preview() if payload.dry_run else AnalyticsOperationalService(db).cleanup(settings.analytics_aggregation_batch_size)
    create_audit_log(db, actor.username, "ANALYTICS_CLEANUP_EXECUTED", "AnalyticsRetentionPolicy", None, f"Analytics retention cleanup completed; dry_run={payload.dry_run}."); db.commit()
    return result


@router.get("/summary")
def summary(db: Session = Depends(get_db), _=Depends(reader)):
    latest = db.scalar(select(AnalyticsRun).order_by(AnalyticsRun.started_at.desc())); scores = dict(db.query(EntityHealthScore.status, func.count(EntityHealthScore.id)).group_by(EntityHealthScore.status).all())
    average = db.scalar(select(func.avg(AnalyticsAvailability.availability_percent))); reliability_row = db.scalar(select(ReliabilityMeasurement).order_by(ReliabilityMeasurement.period_end.desc()))
    return {"overall_system_health": db.scalar(select(EntityHealthScore).where(EntityHealthScore.entity_type == "system").order_by(EntityHealthScore.calculated_at.desc())), "health_status_counts": scores, "average_availability": float(average) if average is not None else None, "active_capacity_warnings": db.query(CapacityAssessment).filter(CapacityAssessment.threshold_status.in_(("warning", "critical"))).count(), "sla_breaches": db.query(SLAMeasurement).filter(SLAMeasurement.target_met.is_(False)).count(), "mttr_seconds": getattr(reliability_row, "mttr_seconds", None), "mtbf_seconds": getattr(reliability_row, "mtbf_seconds", None), "metric_coverage": db.scalar(select(func.avg(AnalyticsDataQualityRecord.coverage_percent))), "stale_analytics": not latest or latest.completed_at is None, "last_analytics_run": latest}


@router.get("/entities/{entity_type}/{entity_id}/summary")
def entity_summary(entity_type: str, entity_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    return {"health": entity_health(entity_type, entity_id, db), "availability": entity_availability(entity_type, entity_id, db), "reliability": db.scalar(select(ReliabilityMeasurement).where(ReliabilityMeasurement.entity_type == entity_type, ReliabilityMeasurement.entity_id == entity_id).order_by(ReliabilityMeasurement.period_end.desc())), "capacity": db.scalars(select(CapacityAssessment).where(CapacityAssessment.entity_type == entity_type, CapacityAssessment.entity_id == entity_id).limit(20)).all(), "sla": db.scalars(select(SLAMeasurement).where(SLAMeasurement.entity_type == entity_type, SLAMeasurement.entity_id == entity_id).limit(20)).all(), "data_quality": db.scalars(select(AnalyticsDataQualityRecord).where(AnalyticsDataQualityRecord.entity_type == entity_type, AnalyticsDataQualityRecord.entity_id == entity_id).limit(20)).all()}
