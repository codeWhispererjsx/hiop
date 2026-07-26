"""Validated analytics contracts with bounded time and entity scopes."""
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

EntityType = Literal["system", "device", "interface", "SNMP_target", "topology", "topology_link", "department", "floor", "building", "network_zone"]
BucketSize = Literal["5_minutes", "15_minutes", "1_hour", "1_day", "1_week", "1_month"]
Quality = Literal["good", "partial", "poor", "insufficient", "unknown"]
Aggregation = Literal["latest", "average", "minimum", "maximum", "sum", "count", "percentage", "rate", "percentile", "duration", "availability"]


class MetricDefinitionWrite(BaseModel):
    metric_key: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,119}$")
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    source_module: Literal["device", "network_scan", "SNMP", "topology", "alerts", "tickets", "system"]
    source_metric_key: str = Field(min_length=1, max_length=120)
    entity_type: EntityType
    data_type: Literal["numeric", "duration", "percentage", "count"] = "numeric"
    unit: str | None = Field(default=None, max_length=40)
    aggregation_method: Aggregation
    higher_is_better: bool = False
    warning_threshold: float | None = None
    critical_threshold: float | None = None
    minimum_expected: float | None = None
    maximum_expected: float | None = None
    enabled: bool = True


class MetricDefinitionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    warning_threshold: float | None = None
    critical_threshold: float | None = None
    minimum_expected: float | None = None
    maximum_expected: float | None = None
    enabled: bool | None = None


class MetricDefinitionRead(MetricDefinitionWrite):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime


class HealthConfigurationWrite(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    entity_type: EntityType
    availability_weight: float = Field(30, ge=0, le=100)
    performance_weight: float = Field(20, ge=0, le=100)
    reliability_weight: float = Field(15, ge=0, le=100)
    alert_weight: float = Field(10, ge=0, le=100)
    capacity_weight: float = Field(10, ge=0, le=100)
    topology_weight: float = Field(5, ge=0, le=100)
    data_quality_weight: float = Field(10, ge=0, le=100)
    excellent_threshold: float = Field(90, ge=0, le=100)
    healthy_threshold: float = Field(75, ge=0, le=100)
    warning_threshold: float = Field(60, ge=0, le=100)
    degraded_threshold: float = Field(40, ge=0, le=100)
    minimum_data_coverage: float = Field(50, ge=0, le=100)
    enabled: bool = True
    is_default: bool = False

    @model_validator(mode="after")
    def validate_configuration(self):
        weights = [self.availability_weight, self.performance_weight, self.reliability_weight, self.alert_weight, self.capacity_weight, self.topology_weight, self.data_quality_weight]
        if sum(weights) <= 0:
            raise ValueError("At least one health component weight must be positive.")
        if not self.excellent_threshold > self.healthy_threshold > self.warning_threshold > self.degraded_threshold:
            raise ValueError("Health thresholds must descend from excellent to degraded.")
        return self


class HealthConfigurationRead(HealthConfigurationWrite):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime


class CapacityPolicyWrite(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    entity_type: EntityType
    metric_key: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,119}$")
    warning_threshold: float
    critical_threshold: float
    minimum_duration_seconds: int = Field(300, ge=0, le=2592000)
    evaluation_window_seconds: int = Field(3600, ge=60, le=2678400)
    minimum_samples: int = Field(3, ge=1, le=100000)
    enabled: bool = False
    scope_type: Literal["global", "entity", "department", "building", "floor", "network_zone", "topology"] = "global"
    scope_id: UUID | None = None

    @model_validator(mode="after")
    def thresholds(self):
        if self.warning_threshold >= self.critical_threshold:
            raise ValueError("Critical threshold must exceed warning threshold.")
        return self


class CapacityPolicyRead(CapacityPolicyWrite):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime


class SLADefinitionWrite(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    entity_type: EntityType
    scope_type: Literal["global", "device", "device_type", "department", "building", "floor", "network_zone", "topology", "custom"]
    scope_id: UUID | None = None
    target_availability_percent: float = Field(ge=0, le=100)
    target_response_time_ms: float | None = Field(default=None, ge=0)
    maximum_incident_resolution_seconds: int | None = Field(default=None, ge=0)
    measurement_window: Literal["1_day", "1_week", "1_month"] = "1_month"
    exclude_maintenance: bool = True
    enabled: bool = False


class SLADefinitionRead(SLADefinitionWrite):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime


class TimeRange(BaseModel):
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def ordered_utc(self):
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("Analytics timestamps must include a timezone.")
        if self.start >= self.end:
            raise ValueError("Start must precede end.")
        return self


class AnalyticsRunRequest(BaseModel):
    run_type: Literal["aggregate", "availability", "health_score", "capacity", "SLA", "reliability", "full"]
    scope_type: Literal["global", "entity", "device", "interface", "topology"] = "global"
    scope_id: UUID | None = None
    period_start: datetime
    period_end: datetime
    entity_ids: list[UUID] = Field(default_factory=list, max_length=500)
    dry_run: bool = True
    recalculate_existing_buckets: bool = False
    maximum_entities: int = Field(default=100, ge=1, le=500)

    @model_validator(mode="after")
    def bounded(self):
        TimeRange(start=self.period_start, end=self.period_end)
        if len(self.entity_ids) > self.maximum_entities:
            raise ValueError("Entity selection exceeds maximum_entities.")
        return self


class TimeSeriesResponse(BaseModel):
    metric_key: str
    entity_type: str
    entity_id: UUID | None
    unit: str | None
    bucket_size: str
    aggregation: str
    points: list[dict[str, Any]]
    quality: dict[str, int]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Page(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int
