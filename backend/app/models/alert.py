import uuid

from sqlalchemy import Boolean, String, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
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
