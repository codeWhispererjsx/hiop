"""V3C historical, read-only VLAN membership observations."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class VLANMembershipObservation(Base):
    __tablename__ = "vlan_membership_observations"
    __table_args__ = (
        UniqueConstraint("network_segment_id", "interface_id", "connected_device_id", "membership_type", name="uq_vlan_membership_identity"),
        CheckConstraint("confidence_score BETWEEN 0 AND 100", name="ck_vlan_membership_confidence"),
        Index("ix_vlan_membership_device_current", "connected_device_id", "is_current"),
        Index("ix_vlan_membership_switch_current", "switch_device_id", "is_current"),
        Index("ix_vlan_membership_interface_current", "interface_id", "is_current"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    network_segment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("network_segments.id", ondelete="CASCADE"), nullable=False)
    switch_device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    interface_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_interfaces.id", ondelete="CASCADE"), nullable=False)
    connected_device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="SET NULL"))
    port_association_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("port_device_associations.id", ondelete="SET NULL"))
    membership_type: Mapped[str] = mapped_column(String(20), nullable=False)
    port_mode: Mapped[str] = mapped_column(String(10), default="unknown", server_default="unknown", nullable=False)
    evidence_source: Mapped[str] = mapped_column(String(40), default="SNMP_Q_BRIDGE", server_default="SNMP_Q_BRIDGE", nullable=False)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    confidence_explanation: Mapped[str] = mapped_column(String(500), nullable=False)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    stale_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
