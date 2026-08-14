import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class ManagedAsset(Base):
    """V4A organizational asset metadata; Device remains technical identity authority."""

    __tablename__ = "managed_assets"
    __table_args__ = (
        UniqueConstraint("device_id", name="uq_managed_asset_device"),
        UniqueConstraint("asset_number", name="uq_managed_asset_number"),
        UniqueConstraint("asset_tag", name="uq_managed_asset_tag"),
        CheckConstraint("status IN ('planned','received','deployed','active','in_maintenance','retired')", name="ck_managed_asset_status"),
        CheckConstraint("condition IS NULL OR condition IN ('new','good','fair','poor','damaged')", name="ck_managed_asset_condition"),
        CheckConstraint("ci_category IN ('device','network','server','application','service','other')", name="ck_managed_asset_category"),
        Index("ix_managed_assets_status_type", "status", "device_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)
    property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id", ondelete="RESTRICT"), index=True)
    asset_number: Mapped[str] = mapped_column(String(24), nullable=False)
    device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    asset_tag: Mapped[str | None] = mapped_column(String(80))
    device_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active", server_default="active")
    ci_category: Mapped[str] = mapped_column(String(24), nullable=False, default="device", server_default="device")
    vendor: Mapped[str | None] = mapped_column(String(120))
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="SET NULL"), index=True)
    model: Mapped[str | None] = mapped_column(String(160))
    serial_number: Mapped[str | None] = mapped_column(String(180), index=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), index=True)
    department_name: Mapped[str | None] = mapped_column(String(120))
    room_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="SET NULL"), index=True)
    location_name: Mapped[str | None] = mapped_column(String(160))
    business_owner: Mapped[str | None] = mapped_column(String(180))
    technical_owner: Mapped[str | None] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text)
    condition: Mapped[str | None] = mapped_column(String(20))
    acquisition_date: Mapped[date | None] = mapped_column(Date)
    received_date: Mapped[date | None] = mapped_column(Date)
    deployment_date: Mapped[date | None] = mapped_column(Date)
    retirement_date: Mapped[date | None] = mapped_column(Date)
    retirement_reason: Mapped[str | None] = mapped_column(String(40))
    retired_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    warranty_start: Mapped[date | None] = mapped_column(Date)
    warranty_end: Mapped[date | None] = mapped_column(Date)
    expected_replacement_date: Mapped[date | None] = mapped_column(Date)
    lifecycle_notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="manual", server_default="manual")
    field_sources: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    created_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class AssetLifecycleEvent(Base):
    __tablename__ = "asset_lifecycle_events"
    __table_args__ = (Index("ix_asset_lifecycle_events_asset_created", "asset_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("managed_assets.id", ondelete="RESTRICT"), nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)
    previous_status: Mapped[str | None] = mapped_column(String(24))
    new_status: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(Text)
    changed_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    changed_by_name: Mapped[str] = mapped_column(String(180), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
