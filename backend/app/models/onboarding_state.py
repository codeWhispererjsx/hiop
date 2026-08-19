"""
Onboarding State Model

Tracks the onboarding progress for organizations and properties.
"""
import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.database import Base


class OnboardingState(str, Enum):
    """Onboarding completion states"""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class PropertyOnboardingState(Base):
    """Tracks onboarding state for individual properties"""
    __tablename__ = "property_onboarding_state"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    state: Mapped[str] = mapped_column(
        String(20),
        default="not_started",
        nullable=False,
    )
    
    # Checklist items
    organization_configured: Mapped[bool] = mapped_column(Boolean, default=False)
    departments_configured: Mapped[bool] = mapped_column(Boolean, default=False)
    locations_configured: Mapped[bool] = mapped_column(Boolean, default=False)
    agent_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    network_configured: Mapped[bool] = mapped_column(Boolean, default=False)
    discovery_run: Mapped[bool] = mapped_column(Boolean, default=False)
    devices_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    devices_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    monitoring_configured: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Current step tracking
    current_step: Mapped[str] = mapped_column(String(50), nullable=True)
    
    # Progress tracking
    steps_completed: Mapped[int] = mapped_column(default=0)
    total_steps: Mapped[int] = mapped_column(default=8)  # Core steps
    
    # Timestamps
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
    )
    
    # Notes
    notes: Mapped[str] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
    )
    
    def get_progress_percentage(self) -> float:
        """Calculate progress percentage based on core steps"""
        if self.total_steps == 0:
            return 0.0
        return (self.steps_completed / self.total_steps) * 100
    
    def get_checklist(self) -> dict:
        """Get checklist status"""
        return {
            "organization_configured": self.organization_configured,
            "departments_configured": self.departments_configured,
            "locations_configured": self.locations_configured,
            "agent_connected": self.agent_connected,
            "network_configured": self.network_configured,
            "discovery_run": self.discovery_run,
            "devices_reviewed": self.devices_reviewed,
            "devices_approved": self.devices_approved,
            "monitoring_configured": self.monitoring_configured,
        }
    
    def is_core_complete(self) -> bool:
        """Check if core onboarding steps are complete"""
        return (
            self.organization_configured
            and self.agent_connected
            and self.network_configured
            and self.discovery_run
            and self.devices_approved
        )
    
    def is_fully_complete(self) -> bool:
        """Check if all onboarding steps are complete"""
        return self.state == OnboardingState.COMPLETED.value