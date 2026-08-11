"""Relational graph foundation for manually managed network topology."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index,
    Integer, String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Topology(Base):
    __tablename__ = "topologies"
    __table_args__ = (UniqueConstraint("name", "scope_type", name="uq_topology_name_scope"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    topology_type: Mapped[str] = mapped_column(String(30), default="physical", server_default="physical", nullable=False)
    scope_type: Mapped[str] = mapped_column(String(30), default="global", server_default="global", nullable=False)
    building_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("buildings.id", ondelete="SET NULL"))
    floor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("floors.id", ondelete="SET NULL"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"))
    network_zone_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("network_zones.id", ondelete="SET NULL"))
    root_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    layout_mode: Mapped[str] = mapped_column(String(30), default="manual", server_default="manual", nullable=False)
    created_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    nodes: Mapped[list["TopologyNode"]] = relationship(back_populates="topology", cascade="all, delete-orphan")
    links: Mapped[list["TopologyLink"]] = relationship(back_populates="topology", cascade="all, delete-orphan")


class TopologyNode(Base):
    __tablename__ = "topology_nodes"
    __table_args__ = (
        UniqueConstraint("topology_id", "device_id", name="uq_topology_node_device"),
        CheckConstraint("confidence_score BETWEEN 0 AND 100", name="ck_topology_node_confidence"),
        CheckConstraint("parent_node_id IS NULL OR parent_node_id <> id", name="ck_topology_node_parent_self"),
        Index("ix_topology_nodes_topology_type_status", "topology_id", "node_type", "status"),
        Index("ix_topology_nodes_location", "building_id", "floor_id", "room_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topology_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topologies.id", ondelete="CASCADE"), nullable=False)
    device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="SET NULL"))
    discovered_device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("discovered_devices.id", ondelete="SET NULL"))
    snmp_target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_targets.id", ondelete="SET NULL"))
    node_type: Mapped[str] = mapped_column(String(40), default="unknown", server_default="unknown", nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(30), default="unknown", server_default="unknown", nullable=False)
    role: Mapped[str] = mapped_column(String(30), default="unknown", server_default="unknown", nullable=False)
    layer: Mapped[str] = mapped_column(String(30), default="unknown", server_default="unknown", nullable=False)
    parent_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("topology_nodes.id", ondelete="SET NULL"))
    network_zone_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("network_zones.id", ondelete="SET NULL"))
    building_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("buildings.id", ondelete="SET NULL"))
    floor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("floors.id", ondelete="SET NULL"))
    room_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="SET NULL"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"))
    management_ip: Mapped[str | None] = mapped_column(String(45))
    vendor: Mapped[str | None] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(120))
    source_type: Mapped[str] = mapped_column(String(30), default="manual", server_default="manual", nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, default=100, server_default="100", nullable=False)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    topology: Mapped[Topology] = relationship(back_populates="nodes")


class TopologyLink(Base):
    __tablename__ = "topology_links"
    __table_args__ = (
        CheckConstraint("source_node_id <> target_node_id", name="ck_topology_link_not_self"),
        CheckConstraint("confidence_score BETWEEN 0 AND 100", name="ck_topology_link_confidence"),
        Index("ix_topology_links_topology_status", "topology_id", "status"),
        Index("ix_topology_links_endpoints", "source_node_id", "target_node_id"),
        Index("ix_topology_links_interfaces", "source_interface_id", "target_interface_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topology_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topologies.id", ondelete="CASCADE"), nullable=False)
    source_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topology_nodes.id", ondelete="CASCADE"), nullable=False)
    target_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topology_nodes.id", ondelete="CASCADE"), nullable=False)
    source_interface_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_interfaces.id", ondelete="SET NULL"))
    target_interface_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_interfaces.id", ondelete="SET NULL"))
    link_type: Mapped[str] = mapped_column(String(30), default="physical", server_default="physical", nullable=False)
    direction: Mapped[str] = mapped_column(String(30), default="bidirectional", server_default="bidirectional", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", server_default="active", nullable=False)
    speed_bps: Mapped[int | None] = mapped_column(BigInteger)
    duplex: Mapped[str | None] = mapped_column(String(20))
    vlan_id: Mapped[int | None] = mapped_column(Integer)
    lag_identifier: Mapped[str | None] = mapped_column(String(80))
    source_type: Mapped[str] = mapped_column(String(30), default="manual", server_default="manual", nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, default=100, server_default="100", nullable=False)
    discovery_method: Mapped[str] = mapped_column(String(30), default="manual", server_default="manual", nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    missing_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_manual: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    is_suppressed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    topology: Mapped[Topology] = relationship(back_populates="links")
    evidence: Mapped[list["TopologyLinkEvidence"]] = relationship(cascade="all, delete-orphan")


class TopologyLinkEvidence(Base):
    __tablename__ = "topology_link_evidence"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topology_link_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topology_links.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(255))
    evidence_type: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_value: Mapped[str | None] = mapped_column(String(500))
    confidence_score: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class NetworkSegment(Base):
    __tablename__ = "network_segments"
    __table_args__ = (UniqueConstraint("topology_id", "cidr", "vlan_id", name="uq_topology_segment_cidr_vlan"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topology_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topologies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    cidr: Mapped[str | None] = mapped_column(String(64), index=True)
    vlan_id: Mapped[int | None] = mapped_column(Integer, index=True)
    vlan_name: Mapped[str | None] = mapped_column(String(120))
    segment_type: Mapped[str] = mapped_column(String(30), default="unknown", server_default="unknown", nullable=False)
    network_zone_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("network_zones.id", ondelete="SET NULL"))
    description: Mapped[str | None] = mapped_column(String(500))
    vlan_status: Mapped[str] = mapped_column(String(20), default="unknown", server_default="unknown", nullable=False)
    gateway: Mapped[str | None] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), default="manual", server_default="manual", nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, default=100, server_default="100", nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    stale_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class TopologyNodeSegment(Base):
    __tablename__ = "topology_node_segments"
    __table_args__ = (UniqueConstraint("topology_node_id", "network_segment_id", "interface_id", name="uq_topology_node_segment"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topology_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topology_nodes.id", ondelete="CASCADE"), index=True)
    network_segment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("network_segments.id", ondelete="CASCADE"), index=True)
    interface_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_interfaces.id", ondelete="SET NULL"))
    membership_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), default="manual", server_default="manual", nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, default=100, server_default="100", nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class DeviceDependency(Base):
    __tablename__ = "topology_dependencies"
    __table_args__ = (
        UniqueConstraint("topology_id", "upstream_node_id", "downstream_node_id", "dependency_type", name="uq_topology_dependency"),
        CheckConstraint("upstream_node_id <> downstream_node_id", name="ck_topology_dependency_not_self"),
        Index("ix_topology_dependency_nodes", "upstream_node_id", "downstream_node_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topology_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topologies.id", ondelete="CASCADE"), index=True)
    upstream_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topology_nodes.id", ondelete="CASCADE"))
    downstream_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topology_nodes.id", ondelete="CASCADE"))
    dependency_type: Mapped[str] = mapped_column(String(30), nullable=False)
    criticality: Mapped[str] = mapped_column(String(20), default="medium", server_default="medium", nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), default="manual", server_default="manual", nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, default=100, server_default="100", nullable=False)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class TopologySnapshot(Base):
    __tablename__ = "topology_snapshots"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topology_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topologies.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    snapshot_type: Mapped[str] = mapped_column(String(30), default="manual", server_default="manual", nullable=False)
    is_operational_baseline: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    is_protected: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending", nullable=False)
    node_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    link_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    segment_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checksum: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)


class TopologySnapshotNode(Base):
    __tablename__ = "topology_snapshot_nodes"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topology_snapshots.id", ondelete="CASCADE"), index=True)
    source_topology_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    node_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    layer: Mapped[str] = mapped_column(String(30), nullable=False)
    management_ip: Mapped[str | None] = mapped_column(String(45))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)


class TopologySnapshotLink(Base):
    __tablename__ = "topology_snapshot_links"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topology_snapshots.id", ondelete="CASCADE"), index=True)
    source_topology_link_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_node_reference: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    target_node_reference: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    link_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    speed_bps: Mapped[int | None] = mapped_column(BigInteger)
    vlan_id: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)


class TopologyChange(Base):
    __tablename__ = "topology_changes"
    __table_args__ = (Index("ix_topology_changes_topology_type_time", "topology_id", "change_type", "detected_at"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topology_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topologies.id", ondelete="CASCADE"))
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("topology_snapshots.id", ondelete="SET NULL"))
    change_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("topology_nodes.id", ondelete="SET NULL"))
    link_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("topology_links.id", ondelete="SET NULL"))
    segment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("network_segments.id", ondelete="SET NULL"))
    previous_values: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)
    current_values: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), default="manual", server_default="manual", nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, default=100, server_default="100", nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending", nullable=False)


class TopologyNodePosition(Base):
    __tablename__ = "topology_node_positions"
    __table_args__ = (UniqueConstraint("topology_id", "node_id", name="uq_topology_node_position"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topology_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topologies.id", ondelete="CASCADE"))
    node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topology_nodes.id", ondelete="CASCADE"), index=True)
    x_position: Mapped[float] = mapped_column(Float, nullable=False)
    y_position: Mapped[float] = mapped_column(Float, nullable=False)
    group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    locked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    layout_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class TopologyGroup(Base):
    __tablename__ = "topology_groups"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topology_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topologies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    group_type: Mapped[str] = mapped_column(String(30), nullable=False)
    parent_group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("topology_groups.id", ondelete="SET NULL"))
    collapsed_by_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
