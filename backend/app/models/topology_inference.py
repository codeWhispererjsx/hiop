"""Explainable, review-first topology inference state."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String,
    func, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class TopologyInferenceRun(Base):
    __tablename__ = "topology_inference_runs"
    __table_args__ = (
        Index("ix_topology_inference_runs_topology_status", "topology_id", "status", "started_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topology_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topologies.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    triggered_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    nodes_analyzed: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    links_analyzed: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    links_merged: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    node_recommendations: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    dependencies_inferred: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    conflicts_detected: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    review_items_created: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    graph_checksum_before: Mapped[str | None] = mapped_column(String(64))
    graph_checksum_after: Mapped[str | None] = mapped_column(String(64))
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)
    error_summary: Mapped[str | None] = mapped_column(String(500))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TopologyConflict(Base):
    __tablename__ = "topology_conflicts"
    __table_args__ = (
        Index("ix_topology_conflicts_topology_status", "topology_id", "status", "severity"),
        Index("ix_topology_conflicts_entity", "entity_type", "entity_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topology_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topologies.id", ondelete="CASCADE"), nullable=False)
    inference_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("topology_inference_runs.id", ondelete="SET NULL"))
    conflict_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    related_entity_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)
    suggested_resolution: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", server_default="open", nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))


class TopologyReviewItem(Base):
    __tablename__ = "topology_review_items"
    __table_args__ = (
        Index("ix_topology_review_items_topology_status", "topology_id", "status", "created_at"),
        CheckConstraint("confidence_score BETWEEN 0 AND 100", name="ck_topology_review_confidence"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topology_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topologies.id", ondelete="CASCADE"), nullable=False)
    inference_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("topology_inference_runs.id", ondelete="SET NULL"))
    review_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    proposed_change: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)
    impact: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending", nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class TopologyConfidenceHistory(Base):
    __tablename__ = "topology_confidence_history"
    __table_args__ = (
        Index("ix_topology_confidence_entity_time", "topology_id", "entity_type", "entity_id", "calculated_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topology_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topologies.id", ondelete="CASCADE"), nullable=False)
    inference_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("topology_inference_runs.id", ondelete="SET NULL"))
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    previous_score: Mapped[int | None] = mapped_column(Integer)
    calculated_score: Mapped[int] = mapped_column(Integer, nullable=False)
    contributions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
