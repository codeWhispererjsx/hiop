import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    jti: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True
    )

    user_id: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True
    )

    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    reason: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )