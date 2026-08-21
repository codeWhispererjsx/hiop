import uuid
from datetime import datetime
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base

class SystemHealthSnapshot(Base):
    """Current health state of HIOP system components."""
    __tablename__ = "system_health_snapshots"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    component: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # HEALTHY, DEGRADED, STALE, FAILED, NOT_CONFIGURED, UNKNOWN
    last_success: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_check: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=False)
    details: Mapped[str | None] = mapped_column(Text)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    __table_args__ = (Index("uq_health_component_org_prop", "component", "organization_id", "property_id", unique=True),)

class HealthEvent(Base):
    """Health state transitions for historical analysis."""
    __tablename__ = "health_events"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    component: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    previous_status: Mapped[str | None] = mapped_column(String(20))
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500))
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=False, index=True)
    __table_args__ = (Index("ix_health_events_component", "component"), Index("ix_health_events_created", "created_at"),)

class JobExecution(Base):
    """Execution history for critical recurring jobs."""
    __tablename__ = "job_executions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    job_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # RUNNING, SUCCESS, FAILED, STALE, WAITING, DISABLED
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(String(1000))
    result_summary: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    __table_args__ = (Index("ix_job_executions_job_id", "job_id"), Index("ix_job_executions_started", "started_at"),)

class NotificationDelivery(Base):
    """Track notification delivery health without exposing message contents."""
    __tablename__ = "notification_deliveries"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    notification_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # PENDING, SENT, FAILED, RETRYING
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    error: Mapped[str | None] = mapped_column(String(500))
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    __table_args__ = (Index("ix_notification_deliveries_status", "status"), Index("ix_notification_deliveries_attempted", "attempted_at"),)
