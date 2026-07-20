import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.database import Base
from app.models.device import Device
from app.models.hierarchy import NetworkZone
from app.models.user import User


class DiscoveryStatus(str, enum.Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class ReviewStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    IGNORED = "ignored"
    REJECTED = "rejected"


class RunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


def _enum(enum_type: type[enum.Enum], name: str) -> Enum:
    return Enum(
        enum_type,
        name=name,
        native_enum=False,
        create_constraint=True,
        values_callable=lambda members: [member.value for member in members],
    )


class DiscoveredDevice(Base):
    __tablename__ = "discovered_devices"
    __table_args__ = (
        CheckConstraint("times_seen >= 1", name="ck_discovered_devices_times_seen_positive"),
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 100)",
            name="ck_discovered_devices_confidence_score_range",
        ),
        CheckConstraint(
            "response_time IS NULL OR response_time >= 0",
            name="ck_discovered_devices_response_time_nonnegative",
        ),
        Index("ix_discovered_devices_ip_address", "ip_address"),
        Index("ix_discovered_devices_hostname", "hostname"),
        Index("ix_discovered_devices_review_status", "review_status"),
        Index("ix_discovered_devices_status", "status"),
        Index("ix_discovered_devices_last_seen_at", "last_seen_at"),
        Index("ix_discovered_devices_subnet", "subnet"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    mac_address: Mapped[str | None] = mapped_column(String(17))
    hostname: Mapped[str | None] = mapped_column(String(255))
    vendor: Mapped[str | None] = mapped_column(String(128))
    operating_system_guess: Mapped[str | None] = mapped_column(String(128))
    device_type_guess: Mapped[str | None] = mapped_column(String(64))
    network_zone_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_zones.id", ondelete="SET NULL")
    )
    subnet: Mapped[str | None] = mapped_column(String(45))
    discovery_method: Mapped[str] = mapped_column(String(32), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    times_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    response_time: Mapped[float | None] = mapped_column(Float)
    status: Mapped[DiscoveryStatus] = mapped_column(
        _enum(DiscoveryStatus, "discovery_status"), nullable=False, default=DiscoveryStatus.UNKNOWN, server_default="unknown"
    )
    review_status: Mapped[ReviewStatus] = mapped_column(
        _enum(ReviewStatus, "review_status"), nullable=False, default=ReviewStatus.PENDING, server_default="pending"
    )
    confidence_score: Mapped[float | None] = mapped_column(Float)
    approved_device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="SET NULL")
    )
    reviewed_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    approved_device = relationship(Device, foreign_keys=[approved_device_id])
    reviewer = relationship(User, foreign_keys=[reviewed_by])
    network_zone = relationship(NetworkZone, foreign_keys=[network_zone_id])


Index(
    "uq_discovered_devices_mac_identity",
    func.lower(DiscoveredDevice.mac_address),
    unique=True,
    postgresql_where=DiscoveredDevice.mac_address.is_not(None),
)
Index(
    "uq_discovered_devices_approved_device_identity",
    DiscoveredDevice.approved_device_id,
    unique=True,
    postgresql_where=DiscoveredDevice.approved_device_id.is_not(None),
)
Index(
    "uq_discovered_devices_ip_hostname_identity",
    DiscoveredDevice.ip_address,
    func.lower(DiscoveredDevice.hostname),
    unique=True,
    postgresql_where=(
        DiscoveredDevice.mac_address.is_(None)
        & DiscoveredDevice.approved_device_id.is_(None)
        & DiscoveredDevice.hostname.is_not(None)
    ),
)
Index(
    "uq_discovered_devices_ip_only_identity",
    DiscoveredDevice.ip_address,
    unique=True,
    postgresql_where=(
        DiscoveredDevice.mac_address.is_(None)
        & DiscoveredDevice.approved_device_id.is_(None)
        & DiscoveredDevice.hostname.is_(None)
    ),
)


class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"
    __table_args__ = (
        CheckConstraint("hosts_attempted >= 0", name="ck_discovery_runs_hosts_attempted_nonnegative"),
        CheckConstraint("hosts_responded >= 0", name="ck_discovery_runs_hosts_responded_nonnegative"),
        CheckConstraint("new_devices >= 0", name="ck_discovery_runs_new_devices_nonnegative"),
        CheckConstraint("matched_devices >= 0", name="ck_discovery_runs_matched_devices_nonnegative"),
        CheckConstraint("updated_devices >= 0", name="ck_discovery_runs_updated_devices_nonnegative"),
        CheckConstraint("error_count >= 0", name="ck_discovery_runs_error_count_nonnegative"),
        CheckConstraint("duration IS NULL OR duration >= 0", name="ck_discovery_runs_duration_nonnegative"),
        Index("ix_discovery_runs_started_at", "started_at"),
        Index("ix_discovery_runs_status", "status"),
        Index("ix_discovery_runs_triggered_by", "triggered_by"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[RunStatus] = mapped_column(
        _enum(RunStatus, "discovery_run_status"), nullable=False, default=RunStatus.PENDING, server_default="pending"
    )
    range_scanned: Mapped[str | None] = mapped_column(String(255))
    hosts_attempted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    hosts_responded: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    new_devices: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    matched_devices: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    updated_devices: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    duration: Mapped[float | None] = mapped_column(Float)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)
    triggered_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    error_summary: Mapped[str | None] = mapped_column(Text)

    triggering_user = relationship(User, foreign_keys=[triggered_by])
