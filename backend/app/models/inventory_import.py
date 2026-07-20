import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.user import User


class ImportSessionStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    VALIDATING = "validating"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class ImportValidationStatus(str, enum.Enum):
    PENDING = "pending"
    VALID = "valid"
    WARNING = "warning"
    DUPLICATE = "duplicate"
    INVALID = "invalid"


def _enum(enum_type: type[enum.Enum], name: str) -> Enum:
    return Enum(
        enum_type,
        name=name,
        native_enum=False,
        create_constraint=True,
        values_callable=lambda members: [member.value for member in members],
    )


class ImportSession(Base):
    __tablename__ = "import_sessions"
    __table_args__ = (
        CheckConstraint("total_rows >= 0", name="ck_import_sessions_total_rows_nonnegative"),
        CheckConstraint("processed_rows >= 0", name="ck_import_sessions_processed_rows_nonnegative"),
        CheckConstraint("successful_rows >= 0", name="ck_import_sessions_successful_rows_nonnegative"),
        CheckConstraint("failed_rows >= 0", name="ck_import_sessions_failed_rows_nonnegative"),
        CheckConstraint("duplicate_rows >= 0", name="ck_import_sessions_duplicate_rows_nonnegative"),
        CheckConstraint("matched_rows >= 0", name="ck_import_sessions_matched_rows_nonnegative"),
        CheckConstraint("skipped_rows >= 0", name="ck_import_sessions_skipped_rows_nonnegative"),
        CheckConstraint("processed_rows <= total_rows", name="ck_import_sessions_processed_within_total"),
        Index("ix_import_sessions_status", "status"),
        Index("ix_import_sessions_uploaded_by", "uploaded_by"),
        Index("ix_import_sessions_uploaded_at", "uploaded_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    import_type: Mapped[str] = mapped_column(String(64), nullable=False)
    file_format: Mapped[str] = mapped_column(String(16), nullable=False)
    uploaded_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[ImportSessionStatus] = mapped_column(
        _enum(ImportSessionStatus, "import_session_status"),
        nullable=False,
        default=ImportSessionStatus.UPLOADED,
        server_default="uploaded",
    )
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    processed_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    successful_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    failed_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    duplicate_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    matched_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    skipped_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    uploader = relationship(User, foreign_keys=[uploaded_by])
    imported_devices: Mapped[list["ImportedDevice"]] = relationship(
        back_populates="import_session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ImportedDevice(Base):
    __tablename__ = "imported_devices"
    __table_args__ = (
        Index("ix_imported_devices_import_session_id", "import_session_id"),
        Index("ix_imported_devices_asset_tag", "asset_tag"),
        Index("ix_imported_devices_hostname", "hostname"),
        Index("ix_imported_devices_ip_address", "ip_address"),
        Index("ix_imported_devices_mac_address", "mac_address"),
        Index("ix_imported_devices_validation_status", "validation_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    import_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_sessions.id", ondelete="CASCADE"), nullable=False
    )
    asset_tag: Mapped[str | None] = mapped_column(String(100))
    hostname: Mapped[str | None] = mapped_column(String(255))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    mac_address: Mapped[str | None] = mapped_column(String(17))
    department_name: Mapped[str | None] = mapped_column(String(120))
    building_name: Mapped[str | None] = mapped_column(String(120))
    floor_name: Mapped[str | None] = mapped_column(String(120))
    room_name: Mapped[str | None] = mapped_column(String(120))
    network_zone: Mapped[str | None] = mapped_column(String(120))
    vendor: Mapped[str | None] = mapped_column(String(128))
    brand: Mapped[str | None] = mapped_column(String(128))
    model: Mapped[str | None] = mapped_column(String(128))
    serial_number: Mapped[str | None] = mapped_column(String(128))
    inventory_status: Mapped[str | None] = mapped_column(String(32))
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    validation_status: Mapped[ImportValidationStatus] = mapped_column(
        _enum(ImportValidationStatus, "import_validation_status"),
        nullable=False,
        default=ImportValidationStatus.PENDING,
        server_default="pending",
    )
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    import_session: Mapped[ImportSession] = relationship(back_populates="imported_devices")


Index(
    "uq_imported_devices_session_asset_tag",
    ImportedDevice.import_session_id,
    func.lower(ImportedDevice.asset_tag),
    unique=True,
    postgresql_where=ImportedDevice.asset_tag.is_not(None),
)
Index(
    "uq_imported_devices_session_mac",
    ImportedDevice.import_session_id,
    func.lower(ImportedDevice.mac_address),
    unique=True,
    postgresql_where=ImportedDevice.mac_address.is_not(None),
)
