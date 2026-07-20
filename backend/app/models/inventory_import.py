import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.device import Device
from app.models.discovered_device import DiscoveredDevice
from app.models.hierarchy import Building, Department, Floor, NetworkZone, Room
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


class ImportMatchLevel(str, enum.Enum):
    EXACT = "exact"
    STRONG = "strong"
    PROBABLE = "probable"
    WEAK = "weak"
    NONE = "none"


class ImportMatchStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class ImportCandidateType(str, enum.Enum):
    INVENTORY_DEVICE = "inventory_device"
    DISCOVERED_DEVICE = "discovered_device"
    IMPORTED_DEVICE = "imported_device"


class ImportRecommendedAction(str, enum.Enum):
    LINK = "link"
    MERGE = "merge"
    CREATE_NEW = "create_new"
    REVIEW = "review"
    SKIP = "skip"


class LocationSuggestionStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    OVERRIDDEN = "overridden"


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
        CheckConstraint("matching_state IN ('idle', 'running', 'completed', 'failed')", name="ck_import_sessions_matching_state"),
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
    mapping_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    selected_worksheet: Mapped[str | None] = mapped_column(String(255))
    matching_state: Mapped[str] = mapped_column(String(16), nullable=False, default="idle", server_default="idle")
    match_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    uploader = relationship(User, foreign_keys=[uploaded_by])
    imported_devices: Mapped[list["ImportedDevice"]] = relationship(
        back_populates="import_session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    match_candidates: Mapped[list["ImportMatchCandidate"]] = relationship(back_populates="import_session", cascade="all, delete-orphan", passive_deletes=True)


class ImportedDevice(Base):
    __tablename__ = "imported_devices"
    __table_args__ = (
        Index("ix_imported_devices_import_session_id", "import_session_id"),
        Index("ix_imported_devices_asset_tag", "asset_tag"),
        Index("ix_imported_devices_hostname", "hostname"),
        Index("ix_imported_devices_ip_address", "ip_address"),
        Index("ix_imported_devices_mac_address", "mac_address"),
        Index("ix_imported_devices_validation_status", "validation_status"),
        Index("ix_imported_devices_session_asset_tag", "import_session_id", "asset_tag"),
        Index("ix_imported_devices_session_mac", "import_session_id", "mac_address"),
        Index("uq_imported_devices_session_source_row", "import_session_id", "source_row_number", unique=True),
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
    notes: Mapped[str | None] = mapped_column(Text)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    normalized_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    resolution_action: Mapped[str | None] = mapped_column(String(32))
    linked_device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="SET NULL"))
    linked_discovery_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("discovered_devices.id", ondelete="SET NULL"))
    resolved_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
    match_candidates: Mapped[list["ImportMatchCandidate"]] = relationship(
        foreign_keys="ImportMatchCandidate.imported_device_id", cascade="all, delete-orphan", passive_deletes=True
    )
    location_suggestion: Mapped["ImportLocationSuggestion | None"] = relationship(
        back_populates="imported_device", cascade="all, delete-orphan", passive_deletes=True, uselist=False
    )
    linked_device = relationship(Device, foreign_keys=[linked_device_id])
    linked_discovery = relationship(DiscoveredDevice, foreign_keys=[linked_discovery_id])
    resolver = relationship(User, foreign_keys=[resolved_by])


class ImportMatchCandidate(Base):
    __tablename__ = "import_match_candidates"
    __table_args__ = (
        CheckConstraint("match_score >= 0 AND match_score <= 100", name="ck_import_match_candidates_score"),
        CheckConstraint(
            "num_nonnulls(candidate_device_id, candidate_discovery_id, candidate_imported_device_id) = 1",
            name="ck_import_match_candidates_one_target",
        ),
        Index("ix_import_match_candidates_session_rank", "import_session_id", "match_score"),
        Index("ix_import_match_candidates_imported_device", "imported_device_id"),
        Index("ix_import_match_candidates_status", "match_status"),
        Index("uq_import_match_candidate_inventory", "imported_device_id", "candidate_device_id", unique=True),
        Index("uq_import_match_candidate_discovery", "imported_device_id", "candidate_discovery_id", unique=True),
        Index("uq_import_match_candidate_imported", "imported_device_id", "candidate_imported_device_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    import_session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("import_sessions.id", ondelete="CASCADE"), nullable=False)
    imported_device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("imported_devices.id", ondelete="CASCADE"), nullable=False)
    candidate_type: Mapped[ImportCandidateType] = mapped_column(_enum(ImportCandidateType, "import_candidate_type"), nullable=False)
    candidate_device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"))
    candidate_discovery_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("discovered_devices.id", ondelete="CASCADE"))
    candidate_imported_device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("imported_devices.id", ondelete="CASCADE"))
    match_score: Mapped[int] = mapped_column(Integer, nullable=False)
    match_level: Mapped[ImportMatchLevel] = mapped_column(_enum(ImportMatchLevel, "import_match_level"), nullable=False)
    match_status: Mapped[ImportMatchStatus] = mapped_column(_enum(ImportMatchStatus, "import_match_status"), nullable=False, default=ImportMatchStatus.PENDING, server_default="pending")
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    conflicting_fields: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    matching_fields: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    recommended_action: Mapped[ImportRecommendedAction] = mapped_column(_enum(ImportRecommendedAction, "import_recommended_action"), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    import_session = relationship(ImportSession, back_populates="match_candidates")
    imported_device = relationship(ImportedDevice, foreign_keys=[imported_device_id], back_populates="match_candidates")
    candidate_device = relationship(Device, foreign_keys=[candidate_device_id])
    candidate_discovery = relationship(DiscoveredDevice, foreign_keys=[candidate_discovery_id])
    candidate_imported_device = relationship(ImportedDevice, foreign_keys=[candidate_imported_device_id])
    reviewer = relationship(User, foreign_keys=[reviewed_by])


class ImportLocationSuggestion(Base):
    __tablename__ = "import_location_suggestions"
    __table_args__ = (
        CheckConstraint("confidence_score >= 0 AND confidence_score <= 100", name="ck_import_location_suggestions_score"),
        Index("uq_import_location_suggestions_imported_device", "imported_device_id", unique=True),
        Index("ix_import_location_suggestions_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    imported_device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("imported_devices.id", ondelete="CASCADE"), nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"))
    building_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("buildings.id", ondelete="SET NULL"))
    floor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("floors.id", ondelete="SET NULL"))
    room_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="SET NULL"))
    network_zone_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("network_zones.id", ondelete="SET NULL"))
    confidence_score: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    conflicts: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    status: Mapped[LocationSuggestionStatus] = mapped_column(_enum(LocationSuggestionStatus, "import_location_suggestion_status"), nullable=False, default=LocationSuggestionStatus.PENDING, server_default="pending")
    reviewed_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    imported_device = relationship(ImportedDevice, back_populates="location_suggestion")
    department = relationship(Department, foreign_keys=[department_id])
    building = relationship(Building, foreign_keys=[building_id])
    floor = relationship(Floor, foreign_keys=[floor_id])
    room = relationship(Room, foreign_keys=[room_id])
    network_zone = relationship(NetworkZone, foreign_keys=[network_zone_id])
    reviewer = relationship(User, foreign_keys=[reviewed_by])
