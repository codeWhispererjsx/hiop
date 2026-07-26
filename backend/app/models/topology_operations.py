"""Scheduled topology operations, alert rules/events, and retained change findings."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class TopologyScheduleConfiguration(Base):
    __tablename__ = "topology_schedule_configurations"
    __table_args__ = (UniqueConstraint("topology_id", name="uq_topology_schedule_topology"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topology_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topologies.id", ondelete="CASCADE"), nullable=False, index=True)
    neighbor_collection_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    neighbor_collection_interval_minutes: Mapped[int] = mapped_column(Integer, default=60, server_default="60", nullable=False)
    inference_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    inference_interval_minutes: Mapped[int] = mapped_column(Integer, default=120, server_default="120", nullable=False)
    snapshot_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    snapshot_interval_hours: Mapped[int] = mapped_column(Integer, default=24, server_default="24", nullable=False)
    change_evaluation_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    change_evaluation_interval_minutes: Mapped[int] = mapped_column(Integer, default=60, server_default="60", nullable=False)
    protocol_mode: Mapped[str] = mapped_column(String(10), default="auto", server_default="auto", nullable=False)
    dry_run_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    maximum_targets_per_run: Mapped[int] = mapped_column(Integer, default=25, server_default="25", nullable=False)
    maximum_run_duration: Mapped[int] = mapped_column(Integer, default=1800, server_default="1800", nullable=False)
    jitter_seconds: Mapped[int] = mapped_column(Integer, default=60, server_default="60", nullable=False)
    stale_run_timeout_minutes: Mapped[int] = mapped_column(Integer, default=30, server_default="30", nullable=False)
    missing_link_grace_runs: Mapped[int] = mapped_column(Integer, default=3, server_default="3", nullable=False)
    automatic_review_threshold: Mapped[int] = mapped_column(Integer, default=95, server_default="95", nullable=False)
    alerting_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    maintenance_reason: Mapped[str | None] = mapped_column(String(500))
    maintenance_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    maintenance_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    maintenance_started_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    last_scheduler_reconciliation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class TopologyOperationalRun(Base):
    __tablename__ = "topology_operational_runs"
    __table_args__ = (
        Index("ix_topology_operational_topology_status_started", "topology_id", "status", "started_at"),
        Index("ix_topology_operational_type_started", "run_type", "started_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topology_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topologies.id", ondelete="CASCADE"), nullable=False)
    run_type: Mapped[str] = mapped_column(String(30), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(20), default="scheduled", server_default="scheduled", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="running", server_default="running", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    target_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    changes_found: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    conflicts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    alerts_created: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("topology_snapshots.id", ondelete="SET NULL"))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_summary: Mapped[str | None] = mapped_column(String(500))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)
    triggered_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TopologyAlertRule(Base):
    __tablename__ = "topology_alert_rules"
    __table_args__ = (Index("ix_topology_alert_rules_topology_enabled", "topology_id", "enabled"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    topology_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("topologies.id", ondelete="CASCADE"))
    rule_type: Mapped[str] = mapped_column(String(50), nullable=False)
    node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("topology_nodes.id", ondelete="CASCADE"))
    link_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("topology_links.id", ondelete="CASCADE"))
    group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("topology_groups.id", ondelete="CASCADE"))
    severity: Mapped[str] = mapped_column(String(20), default="warning", server_default="warning", nullable=False)
    threshold: Mapped[int | None] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    minimum_confidence: Mapped[int] = mapped_column(Integer, default=70, server_default="70", nullable=False)
    consecutive_occurrences: Mapped[int] = mapped_column(Integer, default=2, server_default="2", nullable=False)
    recovery_occurrences: Mapped[int] = mapped_column(Integer, default=2, server_default="2", nullable=False)
    suppress_during_maintenance: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    notification_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    ticket_creation_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    created_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class TopologyAlertEvent(Base):
    __tablename__ = "topology_alert_events"
    __table_args__ = (
        Index("ix_topology_alert_open_severity", "is_open", "severity"),
        Index("ix_topology_alert_topology_seen", "topology_id", "last_seen_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topology_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topologies.id", ondelete="CASCADE"), nullable=False)
    rule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topology_alert_rules.id", ondelete="CASCADE"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    recovery_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    flapping: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    suppressed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
