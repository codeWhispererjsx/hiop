"""Additive analytics domain models; operational source data remains authoritative."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class AnalyticsMetricDefinition(TimestampMixin, Base):
    __tablename__ = "analytics_metric_definitions"
    __table_args__ = (UniqueConstraint("metric_key", name="uq_analytics_metric_key"), Index("ix_analytics_metric_source", "source_module", "source_metric_key"))
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    metric_key: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    source_module: Mapped[str] = mapped_column(String(30), nullable=False)
    source_metric_key: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    data_type: Mapped[str] = mapped_column(String(20), default="numeric", server_default="numeric", nullable=False)
    unit: Mapped[str | None] = mapped_column(String(40))
    aggregation_method: Mapped[str] = mapped_column(String(30), nullable=False)
    higher_is_better: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    warning_threshold: Mapped[float | None] = mapped_column(Float)
    critical_threshold: Mapped[float | None] = mapped_column(Float)
    minimum_expected: Mapped[float | None] = mapped_column(Float)
    maximum_expected: Mapped[float | None] = mapped_column(Float)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)


class AnalyticsAggregate(TimestampMixin, Base):
    __tablename__ = "analytics_aggregates"
    __table_args__ = (
        UniqueConstraint("metric_definition_id", "entity_type", "entity_id", "bucket_start", "bucket_size", name="uq_analytics_aggregate_bucket"),
        Index("ix_analytics_aggregate_metric_time", "metric_definition_id", "bucket_start"),
        Index("ix_analytics_aggregate_entity_time", "entity_type", "entity_id", "bucket_start"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    metric_definition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("analytics_metric_definitions.id", ondelete="RESTRICT"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bucket_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bucket_size: Mapped[str] = mapped_column(String(20), nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_value: Mapped[float | None] = mapped_column(Float)
    maximum_value: Mapped[float | None] = mapped_column(Float)
    average_value: Mapped[float | None] = mapped_column(Float)
    sum_value: Mapped[float | None] = mapped_column(Float)
    latest_value: Mapped[float | None] = mapped_column(Float)
    percentile_50: Mapped[float | None] = mapped_column(Float)
    percentile_95: Mapped[float | None] = mapped_column(Float)
    percentile_99: Mapped[float | None] = mapped_column(Float)
    quality: Mapped[str] = mapped_column(String(20), nullable=False)
    source_first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AnalyticsAvailability(TimestampMixin, Base):
    __tablename__ = "analytics_availability"
    __table_args__ = (
        CheckConstraint("availability_percent IS NULL OR (availability_percent >= 0 AND availability_percent <= 100)", name="ck_analytics_availability_percent"),
        UniqueConstraint("entity_type", "entity_id", "period_start", "period_end", "source_type", name="uq_analytics_availability_period"),
        Index("ix_analytics_availability_entity_period", "entity_type", "entity_id", "period_start"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expected_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    available_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    unavailable_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    maintenance_duration_seconds: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    unknown_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    availability_percent: Mapped[float | None] = mapped_column(Float)
    outage_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    longest_outage_seconds: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    source_type: Mapped[str] = mapped_column(String(60), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EntityHealthScore(TimestampMixin, Base):
    __tablename__ = "analytics_health_scores"
    __table_args__ = (CheckConstraint("score >= 0 AND score <= 100", name="ck_analytics_health_score"), Index("ix_analytics_health_entity_time", "entity_type", "entity_id", "calculated_at"))
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    availability_component: Mapped[float | None] = mapped_column(Float)
    performance_component: Mapped[float | None] = mapped_column(Float)
    reliability_component: Mapped[float | None] = mapped_column(Float)
    alert_component: Mapped[float | None] = mapped_column(Float)
    capacity_component: Mapped[float | None] = mapped_column(Float)
    topology_component: Mapped[float | None] = mapped_column(Float)
    data_quality_component: Mapped[float | None] = mapped_column(Float)
    contributing_factors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(20), default="1.0", server_default="1.0", nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class HealthScoreConfiguration(TimestampMixin, Base):
    __tablename__ = "analytics_health_configurations"
    __table_args__ = (CheckConstraint("minimum_data_coverage >= 0 AND minimum_data_coverage <= 100", name="ck_analytics_health_coverage"), Index("ix_analytics_health_config_entity_default", "entity_type", "is_default"))
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    availability_weight: Mapped[float] = mapped_column(Float, default=30, nullable=False)
    performance_weight: Mapped[float] = mapped_column(Float, default=20, nullable=False)
    reliability_weight: Mapped[float] = mapped_column(Float, default=15, nullable=False)
    alert_weight: Mapped[float] = mapped_column(Float, default=10, nullable=False)
    capacity_weight: Mapped[float] = mapped_column(Float, default=10, nullable=False)
    topology_weight: Mapped[float] = mapped_column(Float, default=5, nullable=False)
    data_quality_weight: Mapped[float] = mapped_column(Float, default=10, nullable=False)
    excellent_threshold: Mapped[float] = mapped_column(Float, default=90, nullable=False)
    healthy_threshold: Mapped[float] = mapped_column(Float, default=75, nullable=False)
    warning_threshold: Mapped[float] = mapped_column(Float, default=60, nullable=False)
    degraded_threshold: Mapped[float] = mapped_column(Float, default=40, nullable=False)
    minimum_data_coverage: Mapped[float] = mapped_column(Float, default=50, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    created_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))


class CapacityPolicy(TimestampMixin, Base):
    __tablename__ = "analytics_capacity_policies"
    __table_args__ = (Index("ix_analytics_capacity_policy_metric_enabled", "metric_key", "enabled"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    metric_key: Mapped[str] = mapped_column(String(120), nullable=False)
    warning_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    critical_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    minimum_duration_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    evaluation_window_seconds: Mapped[int] = mapped_column(Integer, default=3600, nullable=False)
    minimum_samples: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    scope_type: Mapped[str] = mapped_column(String(30), default="global", nullable=False)
    scope_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))


class CapacityAssessment(Base):
    __tablename__ = "analytics_capacity_assessments"
    __table_args__ = (UniqueConstraint("policy_id", "entity_type", "entity_id", "period_start", "period_end", name="uq_analytics_capacity_period"), Index("ix_analytics_capacity_entity_period", "entity_type", "entity_id", "period_start"))
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("analytics_capacity_policies.id", ondelete="RESTRICT"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    metric_key: Mapped[str] = mapped_column(String(120), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_value: Mapped[float | None] = mapped_column(Float)
    average_value: Mapped[float | None] = mapped_column(Float)
    peak_value: Mapped[float | None] = mapped_column(Float)
    percentile_95: Mapped[float | None] = mapped_column(Float)
    threshold_status: Mapped[str] = mapped_column(String(20), nullable=False)
    threshold_breach_duration_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    data_quality: Mapped[str] = mapped_column(String(20), nullable=False)
    explanation: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SLADefinition(TimestampMixin, Base):
    __tablename__ = "analytics_sla_definitions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(30), nullable=False)
    scope_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    target_availability_percent: Mapped[float] = mapped_column(Float, nullable=False)
    target_response_time_ms: Mapped[float | None] = mapped_column(Float)
    maximum_incident_resolution_seconds: Mapped[int | None] = mapped_column(Integer)
    measurement_window: Mapped[str] = mapped_column(String(20), default="1_month", nullable=False)
    exclude_maintenance: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    created_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))


class SLAMeasurement(TimestampMixin, Base):
    __tablename__ = "analytics_sla_measurements"
    __table_args__ = (UniqueConstraint("sla_definition_id", "entity_type", "entity_id", "period_start", "period_end", name="uq_analytics_sla_period"), Index("ix_analytics_sla_entity_period", "entity_type", "entity_id", "period_start"))
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sla_definition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("analytics_sla_definitions.id", ondelete="RESTRICT"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    measured_availability_percent: Mapped[float | None] = mapped_column(Float)
    measured_response_time_ms: Mapped[float | None] = mapped_column(Float)
    incident_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    resolved_incident_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    average_resolution_seconds: Mapped[float | None] = mapped_column(Float)
    target_met: Mapped[bool | None] = mapped_column(Boolean)
    breach_reasons: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False)
    data_quality: Mapped[str] = mapped_column(String(20), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ReliabilityMeasurement(TimestampMixin, Base):
    __tablename__ = "analytics_reliability_measurements"
    __table_args__ = (UniqueConstraint("entity_type", "entity_id", "period_start", "period_end", name="uq_analytics_reliability_period"), Index("ix_analytics_reliability_entity_period", "entity_type", "entity_id", "period_start"))
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False)
    outage_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_downtime_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    mtbf_seconds: Mapped[float | None] = mapped_column(Float)
    mttr_seconds: Mapped[float | None] = mapped_column(Float)
    mean_time_to_acknowledge_seconds: Mapped[float | None] = mapped_column(Float)
    mean_time_to_detect_seconds: Mapped[float | None] = mapped_column(Float)
    data_quality: Mapped[str] = mapped_column(String(20), nullable=False)
    assumptions: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AnalyticsRun(TimestampMixin, Base):
    __tablename__ = "analytics_runs"
    __table_args__ = (Index("ix_analytics_runs_status_started", "status", "started_at"), Index("ix_analytics_runs_scope", "scope_type", "scope_id"))
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_type: Mapped[str] = mapped_column(String(30), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(30), nullable=False)
    scope_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    entities_requested: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    entities_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    aggregates_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    health_scores_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    availability_records_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    capacity_assessments_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sla_measurements_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    triggered_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_summary: Mapped[str | None] = mapped_column(String(500))
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cancellation_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    job_id: Mapped[str | None] = mapped_column(String(120))
    schedule_type: Mapped[str | None] = mapped_column(String(30))
    bucket_sizes: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False)
    checkpoint_before: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)
    checkpoint_after: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)
    batches_total: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    batches_completed: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    records_created: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    records_updated: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    records_skipped: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    stale_recovery_status: Mapped[str | None] = mapped_column(String(30))
    result_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)


class AnalyticsDataQualityRecord(Base):
    __tablename__ = "analytics_data_quality"
    __table_args__ = (UniqueConstraint("entity_type", "entity_id", "metric_key", "period_start", "period_end", name="uq_analytics_quality_period"), Index("ix_analytics_quality_entity_period", "entity_type", "entity_id", "period_start"))
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    metric_key: Mapped[str] = mapped_column(String(120), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expected_samples: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_samples: Mapped[int] = mapped_column(Integer, nullable=False)
    coverage_percent: Mapped[float] = mapped_column(Float, nullable=False)
    missing_samples: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    invalid_samples: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stale_samples: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quality_status: Mapped[str] = mapped_column(String(20), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AnalyticsScheduleConfiguration(TimestampMixin, Base):
    __tablename__ = "analytics_schedule_configurations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    aggregate_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    aggregate_interval_minutes: Mapped[int] = mapped_column(Integer, default=15, server_default="15", nullable=False)
    availability_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    availability_interval_minutes: Mapped[int] = mapped_column(Integer, default=30, server_default="30", nullable=False)
    health_score_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    health_score_interval_minutes: Mapped[int] = mapped_column(Integer, default=30, server_default="30", nullable=False)
    capacity_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    capacity_interval_minutes: Mapped[int] = mapped_column(Integer, default=60, server_default="60", nullable=False)
    sla_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    sla_interval_hours: Mapped[int] = mapped_column(Integer, default=24, server_default="24", nullable=False)
    reliability_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    reliability_interval_hours: Mapped[int] = mapped_column(Integer, default=24, server_default="24", nullable=False)
    data_quality_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    data_quality_interval_minutes: Mapped[int] = mapped_column(Integer, default=60, server_default="60", nullable=False)
    retention_cleanup_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    retention_cleanup_interval_hours: Mapped[int] = mapped_column(Integer, default=24, server_default="24", nullable=False)
    default_lookback_minutes: Mapped[int] = mapped_column(Integer, default=60, server_default="60", nullable=False)
    late_data_overlap_minutes: Mapped[int] = mapped_column(Integer, default=15, server_default="15", nullable=False)
    maximum_entities_per_run: Mapped[int] = mapped_column(Integer, default=500, server_default="500", nullable=False)
    maximum_run_duration_minutes: Mapped[int] = mapped_column(Integer, default=30, server_default="30", nullable=False)
    batch_size: Mapped[int] = mapped_column(Integer, default=100, server_default="100", nullable=False)
    jitter_seconds: Mapped[int] = mapped_column(Integer, default=30, server_default="30", nullable=False)
    stale_run_timeout_minutes: Mapped[int] = mapped_column(Integer, default=60, server_default="60", nullable=False)
    paused: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    last_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AnalyticsCheckpoint(TimestampMixin, Base):
    __tablename__ = "analytics_checkpoints"
    __table_args__ = (
        UniqueConstraint("metric_definition_id", "entity_type", "entity_id", "bucket_size", "calculation_type", name="uq_analytics_checkpoint_scope"),
        Index("ix_analytics_checkpoint_updated", "updated_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    metric_definition_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("analytics_metric_definitions.id", ondelete="CASCADE"))
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    bucket_size: Mapped[str] = mapped_column(String(20), nullable=False)
    calculation_type: Mapped[str] = mapped_column(String(30), nullable=False)
    completed_through: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("analytics_runs.id", ondelete="SET NULL"))


class AnalyticsRetentionPolicy(TimestampMixin, Base):
    __tablename__ = "analytics_retention_policies"
    __table_args__ = (UniqueConstraint("record_type", "bucket_size", name="uq_analytics_retention_type_bucket"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_type: Mapped[str] = mapped_column(String(40), nullable=False)
    bucket_size: Mapped[str | None] = mapped_column(String(20))
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    preserve_latest: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    preserve_breaches: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    preserve_sla_periods: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
