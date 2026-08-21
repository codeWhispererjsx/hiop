import uuid
from datetime import datetime
from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base

class BackupRecord(Base):
    """Track database backup status and metadata."""
    __tablename__ = "backup_records"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    backup_type: Mapped[str] = mapped_column(String(20), nullable=False)  # manual, scheduled
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # in_progress, success, failed, verification_failed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    file_path: Mapped[str | None] = mapped_column(String(500))
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    checksum: Mapped[str | None] = mapped_column(String(64))  # SHA256
    checksum_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    error: Mapped[str | None] = mapped_column(String(1000))
    retention_days: Mapped[int] = mapped_column(Integer, default=14, server_default="14", nullable=False)
    database_version: Mapped[str | None] = mapped_column(String(50))
    __table_args__ = ({"comment": "Track database backup operations for disaster recovery"},)

class RestoreTest(Base):
    """Track restore drill tests for disaster recovery validation."""
    __tablename__ = "restore_tests"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # in_progress, success, failed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    backup_id: Mapped[uuid.UUID | None] = mapped_column(UUID, nullable=False)  # References backup_record.id
    backup_file: Mapped[str] = mapped_column(String(500), nullable=False)
    database_version: Mapped[str | None] = mapped_column(String(50))
    restore_duration_seconds: Mapped[int | None] = mapped_column(Integer)
    organizations_verified: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    properties_verified: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    users_verified: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    assets_verified: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    devices_verified: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    incidents_verified: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    data_integrity_checks: Mapped[str | None] = mapped_column(Text)  # JSON of check results
    error: Mapped[str | None] = mapped_column(String(1000))
    performed_by: Mapped[str] = mapped_column(String(100), nullable=False)  # System user or operator ID
    __table_args__ = ({"comment": "Track disaster recovery restore drill tests"},)
