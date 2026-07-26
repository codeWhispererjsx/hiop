"""Persisted, reviewable LLDP/CDP neighbor evidence."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String,
    Text, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class TopologyNeighborCollectionRun(Base):
    __tablename__ = "topology_neighbor_collection_runs"
    __table_args__ = (
        Index("ix_neighbor_runs_topology_status_started", "topology_id", "status", "started_at"),
        Index("ix_neighbor_runs_target_started", "target_id", "started_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topology_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topologies.id", ondelete="CASCADE"), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_targets.id", ondelete="CASCADE"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending", nullable=False)
    protocols_requested: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False)
    protocols_completed: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False)
    local_ports_seen: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    raw_neighbors_seen: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    normalized_neighbors: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    candidate_nodes_created: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    candidate_links_created: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    candidate_links_updated: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    conflicts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    errors_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(20), default="manual", server_default="manual", nullable=False)
    triggered_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_category: Mapped[str | None] = mapped_column(String(40))
    error_summary: Mapped[str | None] = mapped_column(String(500))
    cancellation_requested: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class TopologyNeighborObservation(Base):
    __tablename__ = "topology_neighbor_observations"
    __table_args__ = (
        UniqueConstraint(
            "topology_id", "source_target_id", "protocol", "local_port_identifier",
            "remote_identity_key", name="uq_neighbor_observation_identity",
        ),
        Index("ix_neighbor_observations_topology_status", "topology_id", "observation_status"),
        Index("ix_neighbor_observations_target_protocol", "source_target_id", "protocol"),
        Index("ix_neighbor_observations_remote_identity", "remote_identity_key"),
        Index("ix_neighbor_observations_last_seen", "last_seen_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    collection_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topology_neighbor_collection_runs.id", ondelete="CASCADE"), nullable=False)
    topology_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topologies.id", ondelete="CASCADE"), nullable=False)
    source_target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_targets.id", ondelete="CASCADE"), nullable=False)
    source_device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="SET NULL"))
    source_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("topology_nodes.id", ondelete="SET NULL"))
    source_interface_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_interfaces.id", ondelete="SET NULL"))
    protocol: Mapped[str] = mapped_column(String(8), nullable=False)
    local_port_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    local_port_description: Mapped[str | None] = mapped_column(String(500))
    remote_identity_key: Mapped[str] = mapped_column(String(300), nullable=False)
    remote_chassis_id: Mapped[str | None] = mapped_column(String(255))
    remote_chassis_subtype: Mapped[str | None] = mapped_column(String(40))
    remote_port_id: Mapped[str | None] = mapped_column(String(255))
    remote_port_subtype: Mapped[str | None] = mapped_column(String(40))
    remote_port_description: Mapped[str | None] = mapped_column(String(500))
    remote_system_name: Mapped[str | None] = mapped_column(String(255))
    remote_system_description: Mapped[str | None] = mapped_column(String(1000))
    remote_management_address: Mapped[str | None] = mapped_column(String(45))
    remote_capabilities: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False)
    remote_platform: Mapped[str | None] = mapped_column(String(255))
    native_vlan: Mapped[int | None] = mapped_column(Integer)
    duplex: Mapped[str | None] = mapped_column(String(20))
    raw_index: Mapped[str | None] = mapped_column(String(255))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    observation_status: Mapped[str] = mapped_column(String(20), default="current", server_default="current", nullable=False)
    missing_collections: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    normalized_identity: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class TopologyNeighborCandidate(Base):
    __tablename__ = "topology_neighbor_candidates"
    __table_args__ = (
        UniqueConstraint("topology_id", "remote_identity_key", name="uq_neighbor_candidate_identity"),
        CheckConstraint("confidence_score BETWEEN 0 AND 100", name="ck_neighbor_candidate_confidence"),
        Index("ix_neighbor_candidates_topology_review", "topology_id", "review_status"),
        Index("ix_neighbor_candidates_management_address", "remote_management_address"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topology_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topologies.id", ondelete="CASCADE"), nullable=False)
    source_observation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("topology_neighbor_observations.id", ondelete="SET NULL"))
    remote_identity_key: Mapped[str] = mapped_column(String(300), nullable=False)
    remote_chassis_id: Mapped[str | None] = mapped_column(String(255))
    remote_system_name: Mapped[str | None] = mapped_column(String(255))
    remote_management_address: Mapped[str | None] = mapped_column(String(45))
    remote_port_id: Mapped[str | None] = mapped_column(String(255))
    vendor_guess: Mapped[str | None] = mapped_column(String(120))
    device_type_guess: Mapped[str] = mapped_column(String(40), default="unknown", server_default="unknown", nullable=False)
    matched_device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="SET NULL"))
    matched_discovered_device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("discovered_devices.id", ondelete="SET NULL"))
    matched_snmp_target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_targets.id", ondelete="SET NULL"))
    matched_topology_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("topology_nodes.id", ondelete="SET NULL"))
    confidence_score: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)
    conflict_flags: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False)
    review_status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
