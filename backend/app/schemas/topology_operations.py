"""Validated operational topology contracts."""
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

RULE_TYPES = Literal[
    "node_missing", "node_restored", "confirmed_link_missing", "link_restored",
    "topology_partitioned", "orphan_count_exceeded", "conflict_count_exceeded",
    "low_confidence_link", "critical_dependency_removed", "uplink_changed",
    "core_path_changed", "unexpected_neighbor", "snapshot_failed",
    "collection_failed", "inference_failed", "topology_stale",
]


class ScheduleWrite(BaseModel):
    neighbor_collection_enabled: bool = False
    neighbor_collection_interval_minutes: int = Field(default=60, ge=15, le=10080)
    inference_enabled: bool = False
    inference_interval_minutes: int = Field(default=120, ge=15, le=10080)
    snapshot_enabled: bool = False
    snapshot_interval_hours: int = Field(default=24, ge=1, le=720)
    change_evaluation_enabled: bool = False
    change_evaluation_interval_minutes: int = Field(default=60, ge=15, le=10080)
    protocol_mode: Literal["auto", "lldp", "cdp", "both"] = "auto"
    dry_run_default: bool = False
    maximum_targets_per_run: int = Field(default=25, ge=1, le=500)
    maximum_run_duration: int = Field(default=1800, ge=60, le=14400)
    jitter_seconds: int = Field(default=60, ge=0, le=900)
    stale_run_timeout_minutes: int = Field(default=30, ge=5, le=1440)
    missing_link_grace_runs: int = Field(default=3, ge=1, le=20)
    automatic_review_threshold: int = Field(default=95, ge=80, le=100)
    alerting_enabled: bool = False
    enabled: bool = False


class ScheduleRead(ScheduleWrite):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    topology_id: UUID
    maintenance_mode: bool
    maintenance_reason: str | None
    maintenance_started_at: datetime | None
    maintenance_ends_at: datetime | None
    last_scheduler_reconciliation_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MaintenanceRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    ends_at: datetime | None = None


class AlertRuleWrite(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    topology_id: UUID | None = None
    rule_type: RULE_TYPES
    node_id: UUID | None = None
    link_id: UUID | None = None
    group_id: UUID | None = None
    severity: Literal["info", "warning", "high", "critical"] = "warning"
    threshold: int | None = Field(default=None, ge=0, le=100000)
    enabled: bool = False
    minimum_confidence: int = Field(default=70, ge=0, le=100)
    consecutive_occurrences: int = Field(default=2, ge=1, le=100)
    recovery_occurrences: int = Field(default=2, ge=1, le=100)
    suppress_during_maintenance: bool = True
    notification_enabled: bool = True
    ticket_creation_enabled: bool = False

    @model_validator(mode="after")
    def scoped_entity(self):
        if sum(value is not None for value in (self.node_id, self.link_id, self.group_id)) > 1:
            raise ValueError("An alert rule may scope to only one node, link, or group.")
        return self


class AlertRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    severity: Literal["info", "warning", "high", "critical"] | None = None
    threshold: int | None = Field(default=None, ge=0, le=100000)
    enabled: bool | None = None
    minimum_confidence: int | None = Field(default=None, ge=0, le=100)
    consecutive_occurrences: int | None = Field(default=None, ge=1, le=100)
    recovery_occurrences: int | None = Field(default=None, ge=1, le=100)
    suppress_during_maintenance: bool | None = None
    notification_enabled: bool | None = None
    ticket_creation_enabled: bool | None = None


class AlertRuleRead(AlertRuleWrite):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime


class AlertEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    topology_id: UUID
    rule_id: UUID
    entity_type: str
    entity_id: UUID | None
    alert_type: str
    severity: str
    is_open: bool
    occurrence_count: int
    recovery_count: int
    flapping: bool
    suppressed: bool
    evidence: dict[str, Any]
    first_seen_at: datetime
    last_seen_at: datetime
    resolved_at: datetime | None
