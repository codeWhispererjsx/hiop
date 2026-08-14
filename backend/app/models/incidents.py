import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def uid():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def created():
    return mapped_column(DateTime(timezone=True), server_default="now()", nullable=False)


class OperationalIncident(Base):
    __tablename__ = "operational_incidents"
    id: Mapped[uuid.UUID] = uid()
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    incident_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    incident_type: Mapped[str] = mapped_column(String(50), default="unknown", index=True)
    status: Mapped[str] = mapped_column(String(20), default="detected", index=True)
    severity: Mapped[str] = mapped_column(String(20), default="medium", index=True)
    priority: Mapped[str] = mapped_column(String(4), default="P3", index=True)
    source_type: Mapped[str | None] = mapped_column(String(40))
    source_reference_type: Mapped[str | None] = mapped_column(String(60))
    source_reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    technology_service_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hospitality_technology_services.id"))
    asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("managed_assets.id"), index=True)
    device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id"))
    category: Mapped[str] = mapped_column(String(40), default="other", server_default="other", index=True)
    assigned_team: Mapped[str | None] = mapped_column(String(160))
    assigned_technician_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), index=True)
    requester_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"))
    building_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("buildings.id"))
    floor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("floors.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("zones.id"))
    room_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.id"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id"))
    guest_impact_level: Mapped[str] = mapped_column(String(20), default="unknown")
    revenue_impact_level: Mapped[str] = mapped_column(String(20), default="unknown")
    security_impact_level: Mapped[str] = mapped_column(String(20), default="unknown")
    life_safety_impact_level: Mapped[str] = mapped_column(String(20), default="unknown")
    incident_commander_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"))
    owner_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"))
    playbook_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    playbook_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    workflow_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    linked_ticket_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("operational_incidents.id"))
    correlation_key: Mapped[str | None] = mapped_column(String(160), index=True)
    closure_summary: Mapped[str | None] = mapped_column(Text)
    closure_reason: Mapped[str | None] = mapped_column(Text)
    resolution_summary: Mapped[str | None] = mapped_column(Text)
    root_cause_notes: Mapped[str | None] = mapped_column(Text)
    follow_up_notes: Mapped[str | None] = mapped_column(Text)
    closure_notes: Mapped[str | None] = mapped_column(Text)
    recovery_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    data_quality: Mapped[str] = mapped_column(String(20), default="unknown")
    detected_at: Mapped[datetime] = created()
    declared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    contained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mitigated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_communication_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=False, onupdate=datetime.utcnow)
    __table_args__ = (
        CheckConstraint("duplicate_of_id IS NULL OR duplicate_of_id <> id", name="ck_incident_not_self_duplicate"),
        Index("ix_incident_property_status_created", "property_id", "status", "created_at"),
    )


class OperationalIncidentSource(Base):
    __tablename__ = "operational_incident_sources"
    id: Mapped[uuid.UUID] = uid()
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("operational_incidents.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(40))
    source_entity_type: Mapped[str | None] = mapped_column(String(60))
    source_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    relationship_type: Mapped[str] = mapped_column(String(30), default="related")
    source_status: Mapped[str | None] = mapped_column(String(30))
    linked_at: Mapped[datetime] = created()
    linked_by: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = created()


class OperationalPlaybook(Base):
    __tablename__ = "operational_playbooks"
    id: Mapped[uuid.UUID] = uid()
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(160))
    code: Mapped[str] = mapped_column(String(60))
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40), default="general_incident_response")
    incident_types: Mapped[str] = mapped_column(Text, default="[]")
    minimum_severity: Mapped[str] = mapped_column(String(20), default="informational")
    maximum_severity: Mapped[str] = mapped_column(String(20), default="critical")
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    requires_incident_commander: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    requires_communications_lead: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    requires_technical_lead: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    maximum_runtime_seconds: Mapped[int] = mapped_column(Integer, default=14400)
    created_by: Mapped[str] = mapped_column(String)
    updated_by: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=False, onupdate=datetime.utcnow)
    __table_args__ = (Index("uq_operational_playbook_scope_code", "property_id", "code", unique=True),)


class OperationalPlaybookVersion(Base):
    __tablename__ = "operational_playbook_versions"
    id: Mapped[uuid.UUID] = uid()
    playbook_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("operational_playbooks.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    objective: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(Text, default="{}")
    prerequisites: Mapped[str] = mapped_column(Text, default="[]")
    activation_criteria: Mapped[str] = mapped_column(Text, default="{}")
    escalation_policy: Mapped[str] = mapped_column(Text, default="{}")
    communication_plan: Mapped[str] = mapped_column(Text, default="{}")
    evidence_requirements: Mapped[str] = mapped_column(Text, default="[]")
    verification_requirements: Mapped[str] = mapped_column(Text, default="[]")
    recovery_criteria: Mapped[str] = mapped_column(Text, default="[]")
    closure_criteria: Mapped[str] = mapped_column(Text, default="[]")
    post_incident_requirements: Mapped[str] = mapped_column(Text, default="{}")
    workflow_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("automation_workflow_versions.id"))
    checksum: Mapped[str | None] = mapped_column(String(64))
    change_summary: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String)
    reviewed_by: Mapped[str | None] = mapped_column(String)
    approved_by: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = created()
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("uq_operational_playbook_version", "playbook_id", "version_number", unique=True),)


class OperationalPlaybookStep(Base):
    __tablename__ = "operational_playbook_steps"
    id: Mapped[uuid.UUID] = uid()
    playbook_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("operational_playbook_versions.id", ondelete="CASCADE"), index=True)
    step_key: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    phase: Mapped[str] = mapped_column(String(30))
    step_type: Mapped[str] = mapped_column(String(30))
    sequence_order: Mapped[int] = mapped_column(Integer, default=0)
    required: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    owner_role: Mapped[str | None] = mapped_column(String(40))
    expected_duration_seconds: Mapped[int | None] = mapped_column(Integer)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=3600)
    maximum_retries: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    action_key: Mapped[str | None] = mapped_column(String(80), ForeignKey("automation_actions.action_key"))
    compensation_action_key: Mapped[str | None] = mapped_column(String(80), ForeignKey("automation_actions.action_key"))
    checklist_definition: Mapped[str] = mapped_column(Text, default="[]")
    input_definition: Mapped[str] = mapped_column(Text, default="{}")
    output_definition: Mapped[str] = mapped_column(Text, default="{}")
    evidence_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    verification_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    continue_on_failure: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=False, onupdate=datetime.utcnow)
    __table_args__ = (Index("uq_playbook_step_key", "playbook_version_id", "step_key", unique=True),)


class IncidentPlaybookRun(Base):
    __tablename__ = "incident_playbook_runs"
    id: Mapped[uuid.UUID] = uid()
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("operational_incidents.id", ondelete="CASCADE"), index=True)
    playbook_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("operational_playbooks.id"))
    playbook_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("operational_playbook_versions.id"))
    workflow_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("automation_workflow_runs.id"))
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    current_phase: Mapped[str | None] = mapped_column(String(30))
    current_step_key: Mapped[str | None] = mapped_column(String(80))
    steps_total: Mapped[int] = mapped_column(Integer, default=0)
    steps_completed: Mapped[int] = mapped_column(Integer, default=0)
    steps_failed: Mapped[int] = mapped_column(Integer, default=0)
    steps_skipped: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_by: Mapped[str] = mapped_column(String)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_requested: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    error_category: Mapped[str | None] = mapped_column(String(40))
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=False, onupdate=datetime.utcnow)


class IncidentPlaybookStepRun(Base):
    __tablename__ = "incident_playbook_step_runs"
    id: Mapped[uuid.UUID] = uid()
    incident_playbook_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("incident_playbook_runs.id", ondelete="CASCADE"), index=True)
    playbook_step_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("operational_playbook_steps.id"))
    step_key: Mapped[str] = mapped_column(String(80))
    phase: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    assigned_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"))
    assigned_role: Mapped[str | None] = mapped_column(String(40))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by: Mapped[str | None] = mapped_column(String)
    input_snapshot: Mapped[str] = mapped_column(Text, default="{}")
    output_snapshot: Mapped[str] = mapped_column(Text, default="{}")
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    verification_status: Mapped[str] = mapped_column(String(24), default="pending")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    escalation_count: Mapped[int] = mapped_column(Integer, default=0)
    error_category: Mapped[str | None] = mapped_column(String(40))
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=False, onupdate=datetime.utcnow)


class IncidentParticipant(Base):
    __tablename__ = "incident_participants"
    id: Mapped[uuid.UUID] = uid()
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("operational_incidents.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    participant_role: Mapped[str] = mapped_column(String(40))
    responsibility: Mapped[str | None] = mapped_column(Text)
    joined_at: Mapped[datetime] = created()
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    assigned_by: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=False, onupdate=datetime.utcnow)
    __table_args__ = (Index("uq_active_incident_participant_role", "incident_id", "user_id", "participant_role", unique=True),)


class IncidentTask(Base):
    __tablename__ = "incident_tasks"
    id: Mapped[uuid.UUID] = uid()
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("operational_incidents.id", ondelete="CASCADE"), index=True)
    playbook_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("incident_playbook_runs.id"))
    step_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("incident_playbook_step_runs.id"))
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text)
    task_type: Mapped[str] = mapped_column(String(30), default="investigation")
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    priority: Mapped[str] = mapped_column(String(4), default="P3")
    assigned_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"))
    assigned_role: Mapped[str | None] = mapped_column(String(40))
    created_by: Mapped[str | None] = mapped_column(String)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by: Mapped[str | None] = mapped_column(String)
    verification_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    verified_by: Mapped[str | None] = mapped_column(String)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    output_summary: Mapped[str | None] = mapped_column(Text)
    blocked_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=False, onupdate=datetime.utcnow)


class IncidentChecklistItem(Base):
    __tablename__ = "incident_checklist_items"
    id: Mapped[uuid.UUID] = uid()
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("operational_incidents.id", ondelete="CASCADE"), index=True)
    playbook_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("incident_playbook_runs.id"))
    step_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("incident_playbook_step_runs.id"))
    item_key: Mapped[str] = mapped_column(String(80))
    text: Mapped[str] = mapped_column(String(500))
    required: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    status: Mapped[str] = mapped_column(String(24), default="pending")
    completed_by: Mapped[str | None] = mapped_column(String)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    evidence_reference: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=False, onupdate=datetime.utcnow)


class IncidentTimelineEntry(Base):
    __tablename__ = "incident_timeline_entries"
    id: Mapped[uuid.UUID] = uid()
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("operational_incidents.id", ondelete="CASCADE"), index=True)
    entry_type: Mapped[str] = mapped_column(String(40), index=True)
    source_type: Mapped[str | None] = mapped_column(String(40))
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    title: Mapped[str] = mapped_column(String(180))
    summary: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str | None] = mapped_column(String(20))
    actor_user_id: Mapped[str | None] = mapped_column(String)
    property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"))
    safe_metadata: Mapped[str] = mapped_column(Text, default="{}")
    occurred_at: Mapped[datetime] = created()
    created_at: Mapped[datetime] = created()
    __table_args__ = (Index("ix_incident_timeline_incident_time", "incident_id", "occurred_at"),)


class IncidentEvidence(Base):
    __tablename__ = "incident_evidence"
    id: Mapped[uuid.UUID] = uid()
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("operational_incidents.id", ondelete="CASCADE"), index=True)
    evidence_type: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str | None] = mapped_column(String(40))
    source_entity_type: Mapped[str | None] = mapped_column(String(60))
    source_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    artifact_reference: Mapped[str | None] = mapped_column(String(500))
    checksum: Mapped[str | None] = mapped_column(String(64))
    captured_at: Mapped[datetime] = created()
    captured_by: Mapped[str | None] = mapped_column(String)
    sensitivity: Mapped[str] = mapped_column(String(30), default="normal")
    retention_class: Mapped[str] = mapped_column(String(30), default="incident")
    evidence_metadata: Mapped[str] = mapped_column("metadata", Text, default="{}")
    created_at: Mapped[datetime] = created()


class IncidentDecision(Base):
    __tablename__ = "incident_decisions"
    id: Mapped[uuid.UUID] = uid()
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("operational_incidents.id", ondelete="CASCADE"), index=True)
    playbook_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("incident_playbook_runs.id"))
    step_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("incident_playbook_step_runs.id"))
    title: Mapped[str] = mapped_column(String(180))
    question: Mapped[str] = mapped_column(Text)
    options: Mapped[str] = mapped_column(Text, default="[]")
    decision: Mapped[str | None] = mapped_column(String(120))
    rationale: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[str | None] = mapped_column(String)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    evidence: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=False, onupdate=datetime.utcnow)


class IncidentCommunicationTemplate(Base):
    __tablename__ = "incident_communication_templates"
    id: Mapped[uuid.UUID] = uid()
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    code: Mapped[str] = mapped_column(String(60))
    communication_type: Mapped[str] = mapped_column(String(40))
    audience_type: Mapped[str] = mapped_column(String(40))
    subject_template: Mapped[str] = mapped_column(String(240))
    body_template: Mapped[str] = mapped_column(Text)
    allowed_fields: Mapped[str] = mapped_column(Text, default="[]")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_by: Mapped[str] = mapped_column(String)
    updated_by: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=False, onupdate=datetime.utcnow)
    __table_args__ = (Index("uq_incident_template_scope_code", "property_id", "code", unique=True),)


class IncidentCommunication(Base):
    __tablename__ = "incident_communications"
    id: Mapped[uuid.UUID] = uid()
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("operational_incidents.id", ondelete="CASCADE"), index=True)
    communication_type: Mapped[str] = mapped_column(String(40))
    audience_type: Mapped[str] = mapped_column(String(40))
    audience_reference: Mapped[str | None] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(240))
    message_template_key: Mapped[str | None] = mapped_column(String(60))
    rendered_message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="draft")
    severity: Mapped[str | None] = mapped_column(String(20))
    sent_by: Mapped[str | None] = mapped_column(String)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=False, onupdate=datetime.utcnow)


class IncidentEscalationRule(Base):
    __tablename__ = "incident_escalation_rules"
    id: Mapped[uuid.UUID] = uid()
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    incident_type: Mapped[str | None] = mapped_column(String(50))
    minimum_severity: Mapped[str] = mapped_column(String(20), default="medium")
    priority: Mapped[str | None] = mapped_column(String(4))
    trigger_condition: Mapped[str] = mapped_column(Text, default="{}")
    elapsed_minutes: Mapped[int | None] = mapped_column(Integer)
    task_overdue_minutes: Mapped[int | None] = mapped_column(Integer)
    target_role: Mapped[str | None] = mapped_column(String(40))
    target_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"))
    escalation_action: Mapped[str] = mapped_column(String(40), default="notify")
    repeat_interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    maximum_escalations: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", index=True)
    created_by: Mapped[str] = mapped_column(String)
    updated_by: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=False, onupdate=datetime.utcnow)


class IncidentEscalation(Base):
    __tablename__ = "incident_escalations"
    id: Mapped[uuid.UUID] = uid()
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("operational_incidents.id", ondelete="CASCADE"), index=True)
    rule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("incident_escalation_rules.id"))
    action: Mapped[str] = mapped_column(String(40))
    escalation_count: Mapped[int] = mapped_column(Integer, default=1)
    reason: Mapped[str] = mapped_column(Text)
    escalated_at: Mapped[datetime] = created()
    created_at: Mapped[datetime] = created()


class IncidentResponseTarget(Base):
    __tablename__ = "incident_response_targets"
    id: Mapped[uuid.UUID] = uid()
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), index=True)
    incident_type: Mapped[str] = mapped_column(String(50), default="unknown")
    severity: Mapped[str] = mapped_column(String(20))
    acknowledgement_target_minutes: Mapped[int] = mapped_column(Integer, default=15)
    triage_target_minutes: Mapped[int] = mapped_column(Integer, default=30)
    containment_target_minutes: Mapped[int] = mapped_column(Integer, default=60)
    recovery_target_minutes: Mapped[int] = mapped_column(Integer, default=240)
    resolution_target_minutes: Mapped[int] = mapped_column(Integer, default=480)
    update_frequency_minutes: Mapped[int] = mapped_column(Integer, default=60)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=False, onupdate=datetime.utcnow)
    __table_args__ = (Index("uq_incident_response_target", "property_id", "incident_type", "severity", unique=True),)


class IncidentImpactAssessment(Base):
    __tablename__ = "incident_impact_assessments"
    id: Mapped[uuid.UUID] = uid()
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("operational_incidents.id", ondelete="CASCADE"), unique=True)
    guest_impact_level: Mapped[str] = mapped_column(String(20), default="unknown")
    revenue_impact_level: Mapped[str] = mapped_column(String(20), default="unknown")
    security_impact_level: Mapped[str] = mapped_column(String(20), default="unknown")
    operational_impact_level: Mapped[str] = mapped_column(String(20), default="unknown")
    life_safety_impact_level: Mapped[str] = mapped_column(String(20), default="unknown")
    affected_guest_rooms: Mapped[int | None] = mapped_column(Integer)
    affected_scope: Mapped[str] = mapped_column(Text, default="{}")
    estimated_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estimated_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidence_score: Mapped[int] = mapped_column(Integer, default=0)
    assessment_source: Mapped[str] = mapped_column(String(30), default="manual")
    assessed_by: Mapped[str] = mapped_column(String)
    assessed_at: Mapped[datetime] = created()
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=False, onupdate=datetime.utcnow)
    __table_args__ = (CheckConstraint("confidence_score >= 0 AND confidence_score <= 100", name="ck_incident_impact_confidence"),)


class IncidentRemediationRecommendation(Base):
    __tablename__ = "incident_remediation_recommendations"
    id: Mapped[uuid.UUID] = uid()
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("operational_incidents.id", ondelete="CASCADE"), index=True)
    recommendation_type: Mapped[str] = mapped_column(String(40))
    action_key: Mapped[str] = mapped_column(String(80), ForeignKey("automation_actions.action_key"))
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    confidence_score: Mapped[int] = mapped_column(Integer)
    risk_level: Mapped[str] = mapped_column(String(20))
    required_permission: Mapped[str | None] = mapped_column(String(80))
    approval_required: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    source_rule: Mapped[str] = mapped_column(String(120))
    evidence: Mapped[str] = mapped_column(Text, default="[]")
    verification_definition: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(24), default="proposed", index=True)
    reviewed_by: Mapped[str | None] = mapped_column(String)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_workflow_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("automation_workflow_runs.id"))
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=False, onupdate=datetime.utcnow)
    __table_args__ = (CheckConstraint("confidence_score >= 0 AND confidence_score <= 100", name="ck_incident_recommendation_confidence"),)


class IncidentCauseAssessment(Base):
    __tablename__ = "incident_cause_assessments"
    id: Mapped[uuid.UUID] = uid()
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("operational_incidents.id", ondelete="CASCADE"), unique=True)
    cause_status: Mapped[str] = mapped_column(String(24), default="unknown")
    cause_category: Mapped[str] = mapped_column(String(30), default="unknown")
    primary_entity_type: Mapped[str | None] = mapped_column(String(60))
    primary_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    summary: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text, default="[]")
    confidence_score: Mapped[int] = mapped_column(Integer, default=0)
    assessed_by: Mapped[str | None] = mapped_column(String)
    assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(String)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=False, onupdate=datetime.utcnow)
    __table_args__ = (CheckConstraint("confidence_score >= 0 AND confidence_score <= 100", name="ck_incident_cause_confidence"),)


class PostIncidentReview(Base):
    __tablename__ = "post_incident_reviews"
    id: Mapped[uuid.UUID] = uid()
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("operational_incidents.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="required", index=True)
    facilitator_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_content: Mapped[str] = mapped_column(Text, default="{}")
    approved_by: Mapped[str | None] = mapped_column(String)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=False, onupdate=datetime.utcnow)


class IncidentFollowUpAction(Base):
    __tablename__ = "incident_follow_up_actions"
    id: Mapped[uuid.UUID] = uid()
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("operational_incidents.id", ondelete="CASCADE"), index=True)
    post_incident_review_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("post_incident_reviews.id"))
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text)
    action_type: Mapped[str] = mapped_column(String(30), default="corrective")
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    priority: Mapped[str] = mapped_column(String(4), default="P3")
    assigned_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[str | None] = mapped_column(String)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=False, onupdate=datetime.utcnow)
