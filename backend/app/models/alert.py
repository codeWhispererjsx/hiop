import uuid

from sqlalchemy import Boolean, String, DateTime, ForeignKey, Index, Integer, Float, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.database import Base


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_acknowledged_created_at", "acknowledged", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id"),
        nullable=False
    )

    previous_status: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    current_status: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    message: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    rule_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("alert_rules.id", ondelete="SET NULL"))
    alert_type: Mapped[str] = mapped_column(String(40), default="device_status", server_default="device_status", nullable=False)
    title: Mapped[str] = mapped_column(String(255), default="Device status changed", server_default="Device status changed", nullable=False)
    severity: Mapped[str] = mapped_column(String(10), default="warning", server_default="warning", nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(20), default="open", server_default="open", nullable=False)
    source: Mapped[str] = mapped_column(String(40), default="monitoring", server_default="monitoring", nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="Monitoring condition crossed a threshold", server_default="Monitoring condition crossed a threshold", nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    current_value: Mapped[float | None] = mapped_column(Float)
    threshold_value: Mapped[float | None] = mapped_column(Float)
    deduplication_key: Mapped[str | None] = mapped_column(String(255), index=True)
    last_updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    acknowledged_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    acknowledged_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    resolution_reason: Mapped[str | None] = mapped_column(String(500))
    manually_resolved: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)

class AlertRule(Base):
    __tablename__="alert_rules"
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    rule_type:Mapped[str]=mapped_column(String(40),unique=True,nullable=False)
    name:Mapped[str]=mapped_column(String(120),nullable=False)
    description:Mapped[str]=mapped_column(String(500),nullable=False)
    enabled:Mapped[bool]=mapped_column(Boolean,default=True,server_default="true",nullable=False)
    severity:Mapped[str]=mapped_column(String(10),nullable=False)
    threshold_value:Mapped[float|None]=mapped_column(Float)
    duration_minutes:Mapped[int]=mapped_column(Integer,default=5,server_default="5",nullable=False)
    consecutive_observations:Mapped[int]=mapped_column(Integer,default=3,server_default="3",nullable=False)
    notify_in_app:Mapped[bool]=mapped_column(Boolean,default=True,server_default="true",nullable=False)
    notify_email:Mapped[bool]=mapped_column(Boolean,default=False,server_default="false",nullable=False)
    updated_by:Mapped[str|None]=mapped_column(String,ForeignKey("users.id",ondelete="SET NULL"))
    created_at:Mapped[DateTime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
    updated_at:Mapped[DateTime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)

class MonitoringEvent(Base):
    __tablename__="monitoring_events"
    __table_args__=(UniqueConstraint("source_type","source_id","event_type",name="uq_monitoring_event_source_type"),Index("ix_monitoring_events_device_occurred","device_id","occurred_at"))
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    device_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("devices.id",ondelete="CASCADE"),nullable=False)
    event_type:Mapped[str]=mapped_column(String(40),nullable=False)
    source:Mapped[str]=mapped_column(String(40),nullable=False)
    source_type:Mapped[str]=mapped_column(String(40),nullable=False)
    source_id:Mapped[str]=mapped_column(String(64),nullable=False)
    value_numeric:Mapped[float|None]=mapped_column(Float)
    evidence:Mapped[dict]=mapped_column(JSONB,default=dict,server_default="{}",nullable=False)
    occurred_at:Mapped[DateTime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
    processed_at:Mapped[DateTime|None]=mapped_column(DateTime(timezone=True))

class AlertHistory(Base):
    __tablename__="alert_history"
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    alert_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("alerts.id",ondelete="CASCADE"),index=True,nullable=False)
    action:Mapped[str]=mapped_column(String(30),nullable=False)
    actor:Mapped[str]=mapped_column(String(120),nullable=False)
    previous_status:Mapped[str|None]=mapped_column(String(20))
    current_status:Mapped[str]=mapped_column(String(20),nullable=False)
    reason:Mapped[str]=mapped_column(String(500),nullable=False)
    created_at:Mapped[DateTime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)

class InAppNotification(Base):
    __tablename__="in_app_notifications"
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    alert_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("alerts.id",ondelete="CASCADE"),index=True,nullable=False)
    user_id:Mapped[str|None]=mapped_column(String,ForeignKey("users.id",ondelete="CASCADE"),index=True)
    channel:Mapped[str]=mapped_column(String(20),default="in_app",server_default="in_app",nullable=False)
    delivery_status:Mapped[str]=mapped_column(String(20),default="pending",server_default="pending",nullable=False)
    read_at:Mapped[DateTime|None]=mapped_column(DateTime(timezone=True))
    error_summary:Mapped[str|None]=mapped_column(String(500))
    created_at:Mapped[DateTime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
