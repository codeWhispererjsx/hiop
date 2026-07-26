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
    AnalyticsRun, CapacityAssessment, CapacityPolicy, EntityHealthScore, HealthScoreConfiguration,
    ReliabilityMeasurement, SLADefinition, SLAMeasurement,
)
from app.schemas.analytics import (
    AnalyticsRunRequest, CapacityPolicyRead, CapacityPolicyWrite, HealthConfigurationRead,
    HealthConfigurationWrite, MetricDefinitionRead, MetricDefinitionUpdate, MetricDefinitionWrite,
    SLADefinitionRead, SLADefinitionWrite,
)
from app.services.analytics_aggregation_service import AnalyticsAggregationService
from app.services.analytics_run_service import execute_analytics_run
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


@router.get("/summary")
def summary(db: Session = Depends(get_db), _=Depends(reader)):
    latest = db.scalar(select(AnalyticsRun).order_by(AnalyticsRun.started_at.desc())); scores = dict(db.query(EntityHealthScore.status, func.count(EntityHealthScore.id)).group_by(EntityHealthScore.status).all())
    average = db.scalar(select(func.avg(AnalyticsAvailability.availability_percent))); reliability_row = db.scalar(select(ReliabilityMeasurement).order_by(ReliabilityMeasurement.period_end.desc()))
    return {"overall_system_health": db.scalar(select(EntityHealthScore).where(EntityHealthScore.entity_type == "system").order_by(EntityHealthScore.calculated_at.desc())), "health_status_counts": scores, "average_availability": float(average) if average is not None else None, "active_capacity_warnings": db.query(CapacityAssessment).filter(CapacityAssessment.threshold_status.in_(("warning", "critical"))).count(), "sla_breaches": db.query(SLAMeasurement).filter(SLAMeasurement.target_met.is_(False)).count(), "mttr_seconds": getattr(reliability_row, "mttr_seconds", None), "mtbf_seconds": getattr(reliability_row, "mtbf_seconds", None), "metric_coverage": db.scalar(select(func.avg(AnalyticsDataQualityRecord.coverage_percent))), "stale_analytics": not latest or latest.completed_at is None, "last_analytics_run": latest}


@router.get("/entities/{entity_type}/{entity_id}/summary")
def entity_summary(entity_type: str, entity_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    return {"health": entity_health(entity_type, entity_id, db), "availability": entity_availability(entity_type, entity_id, db), "reliability": db.scalar(select(ReliabilityMeasurement).where(ReliabilityMeasurement.entity_type == entity_type, ReliabilityMeasurement.entity_id == entity_id).order_by(ReliabilityMeasurement.period_end.desc())), "capacity": db.scalars(select(CapacityAssessment).where(CapacityAssessment.entity_type == entity_type, CapacityAssessment.entity_id == entity_id).limit(20)).all(), "sla": db.scalars(select(SLAMeasurement).where(SLAMeasurement.entity_type == entity_type, SLAMeasurement.entity_id == entity_id).limit(20)).all(), "data_quality": db.scalars(select(AnalyticsDataQualityRecord).where(AnalyticsDataQualityRecord.entity_type == entity_type, AnalyticsDataQualityRecord.entity_id == entity_id).limit(20)).all()}
