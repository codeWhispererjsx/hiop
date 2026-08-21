import uuid

from sqlalchemy import Boolean, String, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.database import Base


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (
        Index("ix_devices_hostname", "hostname"),
        Index("ix_devices_ip_address", "ip_address"),
        Index("ix_devices_property_id", "property_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    asset_tag: Mapped[str] = mapped_column(
        String,
        unique=True,
        nullable=False
    )

    hostname: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    device_type: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    brand: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    model: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    serial_number: Mapped[str] = mapped_column(
        String,
        unique=True,
        nullable=False
    )

    department: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    location: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    ip_address: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    mac_address: Mapped[str | None] = mapped_column(
        String,
        unique=True,
        nullable=True
    )

    status: Mapped[str] = mapped_column(
        String,
        default="Active"
    )
    description: Mapped[str | None] = mapped_column(Text)
    description_source: Mapped[str | None] = mapped_column(String(40))
    ad_computer_name: Mapped[str | None] = mapped_column(String(255))
    ad_distinguished_name: Mapped[str | None] = mapped_column(String(512))
    ad_domain: Mapped[str | None] = mapped_column(String(255))
    ad_organizational_unit: Mapped[str | None] = mapped_column(String(255))
    ad_description: Mapped[str | None] = mapped_column(Text)
    ad_operating_system: Mapped[str | None] = mapped_column(String(255))
    ad_operating_system_version: Mapped[str | None] = mapped_column(String(255))
    ad_enabled: Mapped[bool | None] = mapped_column(Boolean)
    ad_last_logon_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))

    property_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="SET NULL"), nullable=True
    )
    building_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("buildings.id", ondelete="SET NULL"), nullable=True, index=True)
    floor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("floors.id", ondelete="SET NULL"), nullable=True, index=True)
    zone_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("zones.id", ondelete="SET NULL"), nullable=True, index=True)

    inventory_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="Active", server_default="Active"
    )

    network_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="Unknown", server_default="Unknown"
    )

    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), index=True
    )
    room_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="SET NULL"), index=True
    )
    network_zone_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_zones.id", ondelete="SET NULL"), index=True
    )

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
