import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.database import Base


def uid(): return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
def now(): return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ChangeType(Base):
    __tablename__ = "change_types"
    id: Mapped[uuid.UUID] = uid(); name: Mapped[str] = mapped_column(String(100), unique=True); code: Mapped[str] = mapped_column(String(50), unique=True)
    approval_policy: Mapped[str] = mapped_column(String(40), default="technical_and_cab"); risk_template: Mapped[str] = mapped_column(Text, default="{}"); default_tasks: Mapped[str] = mapped_column(Text, default="[]")
    rollback_required: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true"); enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class ChangeCategory(Base):
    __tablename__ = "change_categories"
    id: Mapped[uuid.UUID] = uid(); name: Mapped[str] = mapped_column(String(100), unique=True); code: Mapped[str] = mapped_column(String(50), unique=True); description: Mapped[str | None] = mapped_column(Text); enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class ChangePriority(Base):
    __tablename__ = "change_priorities"
    id: Mapped[uuid.UUID] = uid(); name: Mapped[str] = mapped_column(String(40), unique=True); rank: Mapped[int] = mapped_column(Integer, unique=True); target_days: Mapped[int | None] = mapped_column(Integer)


class ChangeRisk(Base):
    __tablename__ = "change_risks"
    id: Mapped[uuid.UUID] = uid(); name: Mapped[str] = mapped_column(String(40), unique=True); minimum_score: Mapped[int] = mapped_column(Integer); maximum_score: Mapped[int] = mapped_column(Integer); color_token: Mapped[str] = mapped_column(String(40), default="neutral")


class ChangeImpact(Base):
    __tablename__ = "change_impacts"
    id: Mapped[uuid.UUID] = uid(); name: Mapped[str] = mapped_column(String(40), unique=True); rank: Mapped[int] = mapped_column(Integer); description: Mapped[str | None] = mapped_column(Text)


class ChangeRequest(Base):
    __tablename__ = "change_requests"
    id: Mapped[uuid.UUID] = uid(); change_id: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), index=True); department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id")); technology_service_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hospitality_technology_services.id"))
    type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("change_types.id"), index=True); category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("change_categories.id"))
    title: Mapped[str] = mapped_column(String(240)); description: Mapped[str] = mapped_column(Text); business_justification: Mapped[str] = mapped_column(Text); technical_justification: Mapped[str] = mapped_column(Text)
    requested_by: Mapped[str] = mapped_column(String, ForeignKey("users.id")); requested_for: Mapped[str | None] = mapped_column(String, ForeignKey("users.id")); owner_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"))
    risk_level: Mapped[str] = mapped_column(String(20), default="unassessed", index=True); impact_level: Mapped[str] = mapped_column(String(20), default="medium", index=True); priority: Mapped[str] = mapped_column(String(20), default="normal", index=True)
    backout_plan: Mapped[str] = mapped_column(Text); validation_plan: Mapped[str] = mapped_column(Text); test_plan: Mapped[str] = mapped_column(Text); communication_plan: Mapped[str] = mapped_column(Text); implementation_plan: Mapped[str] = mapped_column(Text)
    approval_status: Mapped[str] = mapped_column(String(30), default="not_requested", index=True); status: Mapped[str] = mapped_column(String(30), default="draft", index=True); version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    maintenance_window_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True); scheduled_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True); scheduled_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); implemented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); created_at: Mapped[datetime] = now(); updated_at: Mapped[datetime] = now()
    __table_args__ = (Index("ix_change_requests_property_status", "property_id", "status"),)


class ChangeApproval(Base):
    __tablename__ = "change_approvals"
    id: Mapped[uuid.UUID] = uid(); change_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("change_requests.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(30), index=True); approver_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id")); status: Mapped[str] = mapped_column(String(30), default="pending", index=True); conditions: Mapped[str | None] = mapped_column(Text); comments: Mapped[str | None] = mapped_column(Text); requested_at: Mapped[datetime] = now(); decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChangeTask(Base):
    __tablename__ = "change_tasks"
    id: Mapped[uuid.UUID] = uid(); change_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("change_requests.id", ondelete="CASCADE"), index=True); sequence_order: Mapped[int] = mapped_column(Integer); title: Mapped[str] = mapped_column(String(220)); description: Mapped[str | None] = mapped_column(Text); assigned_to: Mapped[str | None] = mapped_column(String, ForeignKey("users.id")); status: Mapped[str] = mapped_column(String(30), default="pending"); checkpoint: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false"); evidence_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false"); due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); __table_args__ = (UniqueConstraint("change_request_id", "sequence_order", name="uq_change_task_order"),)


class ChangeComment(Base):
    __tablename__ = "change_comments"
    id: Mapped[uuid.UUID] = uid(); change_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("change_requests.id", ondelete="CASCADE"), index=True); user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id")); body: Mapped[str] = mapped_column(Text); internal: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true"); created_at: Mapped[datetime] = now()


class ChangeAttachment(Base):
    __tablename__ = "change_attachments"
    id: Mapped[uuid.UUID] = uid(); change_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("change_requests.id", ondelete="CASCADE"), index=True); filename: Mapped[str] = mapped_column(String(255)); media_type: Mapped[str] = mapped_column(String(120)); size_bytes: Mapped[int] = mapped_column(Integer); storage_reference: Mapped[str] = mapped_column(String(500)); checksum_sha256: Mapped[str] = mapped_column(String(64)); uploaded_by: Mapped[str] = mapped_column(String, ForeignKey("users.id")); created_at: Mapped[datetime] = now()


class ChangeRevision(Base):
    __tablename__ = "change_revisions"
    id: Mapped[uuid.UUID] = uid(); change_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("change_requests.id", ondelete="CASCADE"), index=True); version: Mapped[int] = mapped_column(Integer); snapshot: Mapped[str] = mapped_column(Text); checksum_sha256: Mapped[str] = mapped_column(String(64)); change_summary: Mapped[str | None] = mapped_column(Text); created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id")); created_at: Mapped[datetime] = now(); __table_args__ = (UniqueConstraint("change_request_id", "version", name="uq_change_revision"),)


class CABMeeting(Base):
    __tablename__ = "cab_meetings"
    id: Mapped[uuid.UUID] = uid(); property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), index=True); title: Mapped[str] = mapped_column(String(200)); meeting_type: Mapped[str] = mapped_column(String(30), default="regular"); scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True); scheduled_end: Mapped[datetime] = mapped_column(DateTime(timezone=True)); timezone: Mapped[str] = mapped_column(String(64), default="UTC"); quorum_required: Mapped[int] = mapped_column(Integer, default=2); status: Mapped[str] = mapped_column(String(30), default="scheduled", index=True); meeting_notes: Mapped[str | None] = mapped_column(Text); created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id")); created_at: Mapped[datetime] = now()


class CABMember(Base):
    __tablename__ = "cab_members"
    id: Mapped[uuid.UUID] = uid(); meeting_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cab_meetings.id", ondelete="CASCADE"), index=True); user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id")); member_role: Mapped[str] = mapped_column(String(40), default="member"); voting: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true"); __table_args__ = (UniqueConstraint("meeting_id", "user_id", name="uq_cab_member"),)


class CABAgenda(Base):
    __tablename__ = "cab_agenda_items"
    id: Mapped[uuid.UUID] = uid(); meeting_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cab_meetings.id", ondelete="CASCADE"), index=True); change_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("change_requests.id"), index=True); sequence_order: Mapped[int] = mapped_column(Integer); presenter_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id")); notes: Mapped[str | None] = mapped_column(Text); status: Mapped[str] = mapped_column(String(30), default="pending"); __table_args__ = (UniqueConstraint("meeting_id", "change_request_id", name="uq_cab_agenda_change"),)


class CABAttendance(Base):
    __tablename__ = "cab_attendance"
    id: Mapped[uuid.UUID] = uid(); meeting_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cab_meetings.id", ondelete="CASCADE"), index=True); user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id")); attended: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false"); joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); __table_args__ = (UniqueConstraint("meeting_id", "user_id", name="uq_cab_attendance"),)


class CABVote(Base):
    __tablename__ = "cab_votes"
    id: Mapped[uuid.UUID] = uid(); meeting_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cab_meetings.id", ondelete="CASCADE"), index=True); change_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("change_requests.id"), index=True); voter_id: Mapped[str] = mapped_column(String, ForeignKey("users.id")); vote: Mapped[str] = mapped_column(String(30)); conditions: Mapped[str | None] = mapped_column(Text); comments: Mapped[str | None] = mapped_column(Text); voted_at: Mapped[datetime] = now(); __table_args__ = (UniqueConstraint("meeting_id", "change_request_id", "voter_id", name="uq_cab_vote"),)


class CABDecision(Base):
    __tablename__ = "cab_decisions"
    id: Mapped[uuid.UUID] = uid(); meeting_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cab_meetings.id", ondelete="CASCADE"), index=True); change_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("change_requests.id"), index=True); decision: Mapped[str] = mapped_column(String(30)); conditions: Mapped[str | None] = mapped_column(Text); rationale: Mapped[str] = mapped_column(Text); quorum_met: Mapped[bool] = mapped_column(Boolean); decided_by: Mapped[str] = mapped_column(String, ForeignKey("users.id")); decided_at: Mapped[datetime] = now(); __table_args__ = (UniqueConstraint("meeting_id", "change_request_id", name="uq_cab_decision"),)


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"
    id: Mapped[uuid.UUID] = uid(); change_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("change_requests.id", ondelete="CASCADE"), index=True); version: Mapped[int] = mapped_column(Integer); total_score: Mapped[int] = mapped_column(Integer); risk_level: Mapped[str] = mapped_column(String(20), index=True); rationale: Mapped[str] = mapped_column(Text); assessed_by: Mapped[str] = mapped_column(String, ForeignKey("users.id")); created_at: Mapped[datetime] = now(); __table_args__ = (UniqueConstraint("change_request_id", "version", name="uq_risk_assessment_version"),)


class RiskFactor(Base):
    __tablename__ = "risk_factors"
    id: Mapped[uuid.UUID] = uid(); assessment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("risk_assessments.id", ondelete="CASCADE"), index=True); factor_type: Mapped[str] = mapped_column(String(50)); score: Mapped[int] = mapped_column(Integer); weight: Mapped[float] = mapped_column(Float, default=1); evidence: Mapped[str | None] = mapped_column(Text); __table_args__ = (UniqueConstraint("assessment_id", "factor_type", name="uq_risk_factor"),)


class MitigationPlan(Base):
    __tablename__ = "mitigation_plans"
    id: Mapped[uuid.UUID] = uid(); assessment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("risk_assessments.id", ondelete="CASCADE"), index=True); factor_type: Mapped[str] = mapped_column(String(50)); action: Mapped[str] = mapped_column(Text); owner_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id")); status: Mapped[str] = mapped_column(String(30), default="planned"); due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BusinessImpact(Base):
    __tablename__ = "change_business_impacts"
    id: Mapped[uuid.UUID] = uid(); assessment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("risk_assessments.id", ondelete="CASCADE"), index=True); guest_impact: Mapped[int] = mapped_column(Integer, default=0); revenue_impact: Mapped[int] = mapped_column(Integer, default=0); operational_impact: Mapped[int] = mapped_column(Integer, default=0); compliance_impact: Mapped[int] = mapped_column(Integer, default=0); details: Mapped[str | None] = mapped_column(Text)


class TechnicalImpact(Base):
    __tablename__ = "change_technical_impacts"
    id: Mapped[uuid.UUID] = uid(); assessment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("risk_assessments.id", ondelete="CASCADE"), index=True); security_impact: Mapped[int] = mapped_column(Integer, default=0); downtime_minutes: Mapped[int] = mapped_column(Integer, default=0); rollback_complexity: Mapped[int] = mapped_column(Integer, default=0); service_dependencies: Mapped[int] = mapped_column(Integer, default=0); vendor_dependency: Mapped[int] = mapped_column(Integer, default=0); maintenance_duration_minutes: Mapped[int] = mapped_column(Integer, default=0); details: Mapped[str | None] = mapped_column(Text)


class MaintenanceCalendar(Base):
    __tablename__ = "maintenance_calendars"
    id: Mapped[uuid.UUID] = uid(); property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), index=True); name: Mapped[str] = mapped_column(String(180)); timezone: Mapped[str] = mapped_column(String(64), default="UTC"); holiday_restrictions: Mapped[str] = mapped_column(Text, default="[]"); enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true"); created_at: Mapped[datetime] = now()


class MaintenanceWindow(Base):
    __tablename__ = "maintenance_windows"
    id: Mapped[uuid.UUID] = uid(); calendar_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("maintenance_calendars.id")); property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), index=True); name: Mapped[str] = mapped_column(String(180)); window_type: Mapped[str] = mapped_column(String(30), default="standard", index=True); start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True); end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True)); timezone: Mapped[str] = mapped_column(String(64), default="UTC"); recurrence_rule: Mapped[str | None] = mapped_column(String(255)); blackout: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false"); emergency: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false"); status: Mapped[str] = mapped_column(String(30), default="draft", index=True); created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id")); created_at: Mapped[datetime] = now(); updated_at: Mapped[datetime] = now()


class MaintenanceApproval(Base):
    __tablename__ = "maintenance_approvals"
    id: Mapped[uuid.UUID] = uid(); window_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("maintenance_windows.id", ondelete="CASCADE"), index=True); approver_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id")); status: Mapped[str] = mapped_column(String(30), default="pending"); comments: Mapped[str | None] = mapped_column(Text); requested_at: Mapped[datetime] = now(); decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MaintenanceConflict(Base):
    __tablename__ = "maintenance_conflicts"
    id: Mapped[uuid.UUID] = uid(); window_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("maintenance_windows.id", ondelete="CASCADE"), index=True); conflicting_window_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("maintenance_windows.id")); change_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("change_requests.id")); conflict_type: Mapped[str] = mapped_column(String(40)); severity: Mapped[str] = mapped_column(String(20)); details: Mapped[str] = mapped_column(Text); status: Mapped[str] = mapped_column(String(20), default="open"); detected_at: Mapped[datetime] = now(); resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChangeExecution(Base):
    __tablename__ = "change_executions"
    id: Mapped[uuid.UUID] = uid(); change_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("change_requests.id"), index=True); status: Mapped[str] = mapped_column(String(30), default="pending", index=True); started_by: Mapped[str] = mapped_column(String, ForeignKey("users.id")); started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); progress_percent: Mapped[int] = mapped_column(Integer, default=0); verification_status: Mapped[str] = mapped_column(String(30), default="pending"); failure_summary: Mapped[str | None] = mapped_column(Text); created_at: Mapped[datetime] = now()


class ExecutionTask(Base):
    __tablename__ = "change_execution_tasks"
    id: Mapped[uuid.UUID] = uid(); execution_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("change_executions.id", ondelete="CASCADE"), index=True); change_task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("change_tasks.id")); sequence_order: Mapped[int] = mapped_column(Integer); title: Mapped[str] = mapped_column(String(220)); status: Mapped[str] = mapped_column(String(30), default="pending"); notes: Mapped[str | None] = mapped_column(Text); completed_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id")); started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExecutionEvidence(Base):
    __tablename__ = "change_execution_evidence"
    id: Mapped[uuid.UUID] = uid(); execution_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("change_executions.id", ondelete="CASCADE"), index=True); execution_task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("change_execution_tasks.id")); evidence_type: Mapped[str] = mapped_column(String(40)); reference: Mapped[str] = mapped_column(String(500)); checksum_sha256: Mapped[str | None] = mapped_column(String(64)); notes: Mapped[str | None] = mapped_column(Text); added_by: Mapped[str] = mapped_column(String, ForeignKey("users.id")); created_at: Mapped[datetime] = now()


class ExecutionLog(Base):
    __tablename__ = "change_execution_logs"
    id: Mapped[uuid.UUID] = uid(); execution_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("change_executions.id", ondelete="CASCADE"), index=True); event_type: Mapped[str] = mapped_column(String(40)); message: Mapped[str] = mapped_column(Text); actor_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id")); created_at: Mapped[datetime] = now()


class RollbackExecution(Base):
    __tablename__ = "rollback_executions"
    id: Mapped[uuid.UUID] = uid(); execution_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("change_executions.id"), index=True); reason: Mapped[str] = mapped_column(Text); plan_snapshot: Mapped[str] = mapped_column(Text); status: Mapped[str] = mapped_column(String(30), default="pending", index=True); initiated_by: Mapped[str] = mapped_column(String, ForeignKey("users.id")); approved_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id")); started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); verification_notes: Mapped[str | None] = mapped_column(Text); created_at: Mapped[datetime] = now()


class Release(Base):
    __tablename__ = "releases"
    id: Mapped[uuid.UUID] = uid(); release_id: Mapped[str] = mapped_column(String(30), unique=True, index=True); property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), index=True); name: Mapped[str] = mapped_column(String(200)); release_type: Mapped[str] = mapped_column(String(30)); description: Mapped[str] = mapped_column(Text); owner_id: Mapped[str] = mapped_column(String, ForeignKey("users.id")); status: Mapped[str] = mapped_column(String(30), default="draft", index=True); planned_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); planned_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); release_notes: Mapped[str | None] = mapped_column(Text); rollback_plan: Mapped[str] = mapped_column(Text); created_at: Mapped[datetime] = now(); updated_at: Mapped[datetime] = now()


class ReleasePackage(Base):
    __tablename__ = "release_packages"
    id: Mapped[uuid.UUID] = uid(); release_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("releases.id", ondelete="CASCADE"), index=True); name: Mapped[str] = mapped_column(String(180)); description: Mapped[str | None] = mapped_column(Text); checksum_sha256: Mapped[str | None] = mapped_column(String(64)); status: Mapped[str] = mapped_column(String(30), default="draft")


class ReleaseVersion(Base):
    __tablename__ = "release_versions"
    id: Mapped[uuid.UUID] = uid(); release_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("releases.id", ondelete="CASCADE"), index=True); version: Mapped[str] = mapped_column(String(80)); notes: Mapped[str | None] = mapped_column(Text); immutable: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false"); created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id")); created_at: Mapped[datetime] = now(); __table_args__ = (UniqueConstraint("release_id", "version", name="uq_release_version"),)


class ReleaseDeployment(Base):
    __tablename__ = "release_deployments"
    id: Mapped[uuid.UUID] = uid(); release_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("releases.id"), index=True); change_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("change_requests.id")); wave_number: Mapped[int] = mapped_column(Integer, default=1); property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id")); status: Mapped[str] = mapped_column(String(30), default="planned", index=True); scheduled_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); verification_notes: Mapped[str | None] = mapped_column(Text); rollback_status: Mapped[str | None] = mapped_column(String(30))


class ReleaseArtifact(Base):
    __tablename__ = "release_artifacts"
    id: Mapped[uuid.UUID] = uid(); package_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("release_packages.id", ondelete="CASCADE"), index=True); filename: Mapped[str] = mapped_column(String(255)); storage_reference: Mapped[str] = mapped_column(String(500)); media_type: Mapped[str] = mapped_column(String(120)); size_bytes: Mapped[int] = mapped_column(Integer); checksum_sha256: Mapped[str] = mapped_column(String(64)); created_at: Mapped[datetime] = now()


class ChangeCommunication(Base):
    __tablename__ = "change_communications"
    id: Mapped[uuid.UUID] = uid(); change_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("change_requests.id"), index=True); release_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("releases.id")); communication_type: Mapped[str] = mapped_column(String(40)); audience: Mapped[str] = mapped_column(String(80)); subject: Mapped[str] = mapped_column(String(240)); body: Mapped[str] = mapped_column(Text); channel: Mapped[str] = mapped_column(String(30), default="email"); status: Mapped[str] = mapped_column(String(30), default="draft", index=True); scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); delivery_summary: Mapped[str | None] = mapped_column(Text); created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id")); created_at: Mapped[datetime] = now()


class ChangeRelationship(Base):
    __tablename__ = "change_relationships"
    id: Mapped[uuid.UUID] = uid(); change_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("change_requests.id", ondelete="CASCADE"), index=True); target_type: Mapped[str] = mapped_column(String(40), index=True); target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True); relationship_type: Mapped[str] = mapped_column(String(40), default="related"); notes: Mapped[str | None] = mapped_column(Text); created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id")); created_at: Mapped[datetime] = now(); __table_args__ = (UniqueConstraint("change_request_id", "target_type", "target_id", "relationship_type", name="uq_change_relationship"),)
