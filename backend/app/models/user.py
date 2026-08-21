import uuid

from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy import Boolean
from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False
    )

    email: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False
    )

    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    role: Mapped[str] = mapped_column(
        String(30),
        default="viewer"
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
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True, index=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    primary_location_type: Mapped[str | None] = mapped_column(String(30))
    primary_location_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    last_login_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True
    )

    must_change_password: Mapped[bool] = mapped_column(
        Boolean,
        nullable=True,
        default=False
    )
