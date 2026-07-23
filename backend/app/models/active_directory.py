import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.device import Device
from app.models.user import User


class ADAuthenticationMethod(str, enum.Enum):
    SIMPLE = "simple"
    LDAPS = "ldaps"
    START_TLS = "start_tls"
    ANONYMOUS = "anonymous"
    KERBEROS = "kerberos"


class ADObjectType(str, enum.Enum):
    USER = "user"
    COMPUTER = "computer"
    GROUP = "group"


class ADSyncStatus(str, enum.Enum):
    DISCOVERED = "discovered"
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    MISSING = "missing"
    ERROR = "error"


class ADReviewStatus(str, enum.Enum):
    PENDING = "pending"
    MATCHED = "matched"
    APPROVED = "approved"
    IGNORED = "ignored"
    CONFLICT = "conflict"


class ADSyncRunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ADConflictPolicy(str, enum.Enum):
    REVIEW = "review"
    PRESERVE_HIOP = "preserve_hiop"
    PREFER_DIRECTORY = "prefer_directory"
    FILL_MISSING_ONLY = "fill_missing_only"


class ADMatchCandidateType(str, enum.Enum):
    HIOP_USER = "hiop_user"
    HIOP_DEVICE = "hiop_device"


class ADMatchLevel(str, enum.Enum):
    EXACT = "exact"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class ADMatchStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    AUTO_MATCHED = "auto_matched"


class ADRecommendedAction(str, enum.Enum):
    LINK = "link"
    CREATE = "create"
    ENRICH = "enrich"
    REVIEW = "review"
    IGNORE = "ignore"


class ActiveDirectoryConnection(Base):
    __tablename__ = "active_directory_connections"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
    )
    domain_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    server_host: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    server_port: Mapped[int] = mapped_column(
        Integer,
        default=389,
        nullable=False,
    )
    use_ssl: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    use_start_tls: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    base_dn: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    user_search_base: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    computer_search_base: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    group_search_base: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    bind_username: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    encrypted_bind_secret: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    authentication_method: Mapped[str] = mapped_column(
        String(30),
        default="simple",
        nullable=False,
    )
    connection_timeout_seconds: Mapped[int] = mapped_column(
        Integer,
        default=10,
        nullable=False,
    )
    page_size: Mapped[int] = mapped_column(
        Integer,
        default=500,
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    verify_tls: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    ca_certificate_reference: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    last_tested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_test_status: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )
    last_test_message: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    created_by: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    sync_configuration: Mapped["ActiveDirectorySyncConfiguration"] = relationship(
        "ActiveDirectorySyncConfiguration",
        back_populates="connection",
        uselist=False,
        cascade="all, delete-orphan",
    )
    sync_runs: Mapped[list["ActiveDirectorySyncRun"]] = relationship(
        "ActiveDirectorySyncRun",
        back_populates="connection",
        cascade="all, delete-orphan",
    )
    objects: Mapped[list["ActiveDirectoryObject"]] = relationship(
        "ActiveDirectoryObject",
        back_populates="connection",
        cascade="all, delete-orphan",
    )
    creator: Mapped[User | None] = relationship("User", foreign_keys=[created_by])
    updater: Mapped[User | None] = relationship("User", foreign_keys=[updated_by])


class ActiveDirectorySyncConfiguration(Base):
    __tablename__ = "active_directory_sync_configurations"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    connection_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("active_directory_connections.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    sync_users_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    sync_computers_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    sync_groups_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    sync_interval_minutes: Mapped[int] = mapped_column(
        Integer,
        default=60,
        nullable=False,
    )
    auto_create_users: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    auto_disable_missing_users: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    auto_create_devices: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    auto_update_devices: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    sync_group_memberships: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    department_mapping_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    organizational_unit_mapping_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    dry_run_default: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    conflict_policy: Mapped[str] = mapped_column(
        String(30),
        default="review",
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    connection: Mapped[ActiveDirectoryConnection] = relationship(
        "ActiveDirectoryConnection",
        back_populates="sync_configuration",
    )


class ActiveDirectoryObject(Base):
    __tablename__ = "active_directory_objects"
    __table_args__ = (
        UniqueConstraint("connection_id", "object_guid", name="uq_ad_object_connection_guid"),
        Index("ix_ad_objects_connection_id", "connection_id"),
        Index("ix_ad_objects_object_guid", "object_guid"),
        Index("ix_ad_objects_object_sid", "object_sid"),
        Index("ix_ad_objects_distinguished_name", "distinguished_name"),
        Index("ix_ad_objects_sam_account_name", "sam_account_name"),
        Index("ix_ad_objects_user_principal_name", "user_principal_name"),
        Index("ix_ad_objects_dns_hostname", "dns_hostname"),
        Index("ix_ad_objects_object_type", "object_type"),
        Index("ix_ad_objects_sync_status", "sync_status"),
        Index("ix_ad_objects_review_status", "review_status"),
        Index("ix_ad_objects_matched_user_id", "matched_user_id"),
        Index("ix_ad_objects_matched_device_id", "matched_device_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    connection_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("active_directory_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    object_guid: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    object_sid: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    object_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    distinguished_name: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )
    sam_account_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    user_principal_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    common_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    display_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    dns_hostname: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    department: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    job_title: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    operating_system: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    operating_system_version: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    organizational_unit: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    description: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    last_logon_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    when_created: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    when_changed: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    raw_attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        server_default=func.text("'{}'::jsonb"),
        nullable=False,
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    sync_status: Mapped[str] = mapped_column(
        String(30),
        default="discovered",
        nullable=False,
    )
    review_status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        nullable=False,
    )
    matched_user_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    matched_device_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    connection: Mapped[ActiveDirectoryConnection] = relationship(
        "ActiveDirectoryConnection",
        back_populates="objects",
    )
    matched_user: Mapped[User | None] = relationship("User", foreign_keys=[matched_user_id])
    matched_device: Mapped[Device | None] = relationship("Device", foreign_keys=[matched_device_id])
    match_candidates: Mapped[list["ActiveDirectoryMatchCandidate"]] = relationship(
        "ActiveDirectoryMatchCandidate",
        back_populates="directory_object",
        cascade="all, delete-orphan",
    )


class ActiveDirectorySyncRun(Base):
    __tablename__ = "active_directory_sync_runs"
    __table_args__ = (
        Index("ix_ad_sync_runs_connection_id", "connection_id"),
        Index("ix_ad_sync_runs_status", "status"),
        Index("ix_ad_sync_runs_started_at", "started_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    connection_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("active_directory_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        nullable=False,
    )
    trigger_type: Mapped[str] = mapped_column(
        String(30),
        default="manual",
        nullable=False,
    )
    triggered_by: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    dry_run: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    users_seen: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    computers_seen: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    groups_seen: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    created_objects: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    updated_objects: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    unchanged_objects: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    missing_objects: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    conflicts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    errors_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    duration_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    error_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    connection: Mapped[ActiveDirectoryConnection] = relationship(
        "ActiveDirectoryConnection",
        back_populates="sync_runs",
    )
    trigger_user: Mapped[User | None] = relationship("User", foreign_keys=[triggered_by])


class ActiveDirectoryMatchCandidate(Base):
    __tablename__ = "active_directory_match_candidates"
    __table_args__ = (
        Index("ix_ad_candidates_directory_object_id", "directory_object_id"),
        Index("ix_ad_candidates_candidate_user_id", "candidate_user_id"),
        Index("ix_ad_candidates_candidate_device_id", "candidate_device_id"),
        Index("ix_ad_candidates_match_status", "match_status"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    directory_object_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("active_directory_objects.id", ondelete="CASCADE"),
        nullable=False,
    )
    candidate_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    candidate_user_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    candidate_device_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=True,
    )
    match_score: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )
    match_level: Mapped[str] = mapped_column(
        String(30),
        default="none",
        nullable=False,
    )
    match_status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        nullable=False,
    )
    matching_fields: Mapped[list[Any]] = mapped_column(
        JSONB,
        server_default=func.text("'[]'::jsonb"),
        nullable=False,
    )
    conflicting_fields: Mapped[list[Any]] = mapped_column(
        JSONB,
        server_default=func.text("'[]'::jsonb"),
        nullable=False,
    )
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        server_default=func.text("'{}'::jsonb"),
        nullable=False,
    )
    recommended_action: Mapped[str] = mapped_column(
        String(30),
        default="review",
        nullable=False,
    )
    reviewed_by: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    directory_object: Mapped[ActiveDirectoryObject] = relationship(
        "ActiveDirectoryObject",
        back_populates="match_candidates",
    )
    candidate_user: Mapped[User | None] = relationship("User", foreign_keys=[candidate_user_id])
    candidate_device: Mapped[Device | None] = relationship("Device", foreign_keys=[candidate_device_id])
    reviewer: Mapped[User | None] = relationship("User", foreign_keys=[reviewed_by])
