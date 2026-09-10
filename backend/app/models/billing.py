import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.database import Base


class CommercialPlan(Base):
    __tablename__ = "commercial_plans"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    audience: Mapped[str | None] = mapped_column(String(200))
    monthly_price: Mapped[object | None] = mapped_column(Numeric(14, 2))
    yearly_price: Mapped[object | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="NGN")
    trial_days: Mapped[int] = mapped_column(Integer, nullable=False, default=14)
    features: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    entitlements: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    limits: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider_monthly_price_id: Mapped[str | None] = mapped_column(String(255))
    provider_yearly_price_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class OrganizationSubscription(Base):
    __tablename__ = "organization_subscriptions"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_subscription_organization"), Index("ix_subscription_status_period", "status", "current_period_end"))
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("commercial_plans.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="trial", index=True)
    billing_interval: Mapped[str] = mapped_column(String(20), nullable=False, default="monthly")
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trial_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trial_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    renewal_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider: Mapped[str | None] = mapped_column(String(40))
    provider_customer_reference: Mapped[str | None] = mapped_column(String(255))
    provider_subscription_reference: Mapped[str | None] = mapped_column(String(255), unique=True)
    payment_status: Mapped[str] = mapped_column(String(30), nullable=False, default="not_required")
    billing_exempt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    billing_exemption_reason: Mapped[str | None] = mapped_column(Text)
    billing_exempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    billing_exempted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class BillingEvent(Base):
    __tablename__ = "billing_events"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("organization_subscriptions.id", ondelete="SET NULL"), index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    provider_event_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    safe_details: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class BillingDocumentReference(Base):
    __tablename__ = "billing_document_references"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    subscription_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organization_subscriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_reference: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    hosted_url: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[object | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    status: Mapped[str | None] = mapped_column(String(30))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
