import uuid

from sqlalchemy import String, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.database import Base


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (
        Index("ix_devices_hostname", "hostname"),
        Index("ix_devices_ip_address", "ip_address"),
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

    mac_address: Mapped[str] = mapped_column(
        String,
        unique=True,
        nullable=False
    )

    status: Mapped[str] = mapped_column(
        String,
        default="Active"
    )

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
