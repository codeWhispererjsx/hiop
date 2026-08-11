"""V3B cached, historical switch-port observations over existing devices."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class PortDeviceAssociation(Base):
    __tablename__ = "port_device_associations"
    __table_args__ = (
        UniqueConstraint("interface_id", "observed_mac", "connected_device_id", name="uq_port_device_association_identity"),
        CheckConstraint("confidence_score BETWEEN 0 AND 100", name="ck_port_device_association_confidence"),
        Index("ix_port_associations_switch_current", "switch_device_id", "is_current"),
        Index("ix_port_associations_device_current", "connected_device_id", "is_current"),
        Index("ix_port_associations_interface_current", "interface_id", "is_current"),
        Index("ix_port_associations_mac", "observed_mac"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    switch_device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    interface_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_interfaces.id", ondelete="CASCADE"), nullable=False)
    connected_device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="SET NULL"))
    topology_link_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("topology_links.id", ondelete="SET NULL"))
    observed_mac: Mapped[str | None] = mapped_column(String(17))
    association_type: Mapped[str] = mapped_column(String(20), default="endpoint", server_default="endpoint", nullable=False)
    evidence_source: Mapped[str] = mapped_column(String(40), default="SNMP_MAC_TABLE", server_default="SNMP_MAC_TABLE", nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    confidence_level: Mapped[str] = mapped_column(String(10), default="low", server_default="low", nullable=False)
    confidence_explanation: Mapped[str] = mapped_column(String(500), nullable=False)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    stale_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
