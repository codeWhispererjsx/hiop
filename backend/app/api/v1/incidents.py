import json
import secrets
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.core.tenant import organization_context
from app.models.incidents import (
    IncidentCauseAssessment, IncidentChecklistItem, IncidentCommunication,
    IncidentCommunicationTemplate, IncidentDecision, IncidentEscalation,
    IncidentEscalationRule, IncidentEvidence, IncidentFollowUpAction,
    IncidentImpactAssessment, IncidentParticipant, IncidentPlaybookRun,
    IncidentPlaybookStepRun, IncidentRemediationRecommendation,
    IncidentResponseTarget, IncidentTask, IncidentTimelineEntry,
    OperationalIncident, OperationalIncidentSource, OperationalPlaybook,
    OperationalPlaybookStep, OperationalPlaybookVersion, PostIncidentReview,
)
from app.models.property_access import UserPropertyAccess
from app.models.hierarchy import Property
from app.models.user import User
from app.models.alert import Alert
from app.models.ticket import Ticket
from app.models.device import Device
from app.models.automation_triggers import AutomationEventRecord
from app.models.hospitality_operations import HospitalityTechnologyService
from app.services.audit_service import create_audit_log
from app.services.incident_communication_service import render_template
from app.services.incident_escalation_service import evaluate_incident
from app.services.incident_orchestration_service import (
    compensate_playbook_step, complete_playbook_step, ensure_post_incident_review,
    publish, recovery_readiness, retry_playbook_step as retry_step_service,
    start_playbook, timeline as add_timeline, transition,
)
from app.services.incident_playbook_selection_service import select_playbooks
from app.services.incident_playbook_validation_service import validate_playbook, version_checksum
from app.services.incident_recommendation_service import generate_recommendations

router = APIRouter(prefix="/incidents", tags=["Incidents"])
reader = require_roles(["platformadmin", "admin", "technician", "viewer"])
operator = require_roles(["admin", "technician"])
admin = require_roles(["admin"])

INCIDENT_TYPES = {
    "network_outage", "service_degradation", "device_failure", "security_system_failure",
    "guest_technology_failure", "revenue_system_failure", "property_management_system_failure",
    "telephony_failure", "CCTV_failure", "access_control_failure", "wireless_failure",
    "server_failure", "configuration_change_failure", "compliance_incident",
    "monitoring_failure", "data_quality_incident", "power_environmental_incident",
    "vendor_incident", "unknown",
}
SEVERITIES = {"informational", "low", "medium", "high", "critical"}
PRIORITIES = {"P1", "P2", "P3", "P4"}
IMPACTS = {"none", "low", "moderate", "high", "property_wide", "unknown"}
PARTICIPANT_ROLES = {
    "incident_commander", "technical_lead", "communications_lead", "scribe",
    "service_owner", "property_admin", "network_engineer", "systems_engineer",
    "security_representative", "vendor_contact", "observer", "approver",
}


class IncidentWrite(BaseModel):
    property_id: UUID
    title: str = Field(min_length=3, max_length=180)
    description: str | None = Field(None, max_length=10000)
    incident_type: str = "unknown"
    severity: str = "medium"
    priority: str = "P3"
    correlation_key: str | None = Field(None, max_length=160)
    source_type: str | None = Field(None, max_length=40)
    source_reference_type: str | None = Field(None, max_length=60)
    source_reference_id: UUID | None = None
    guest_impact_level: str = "unknown"
    revenue_impact_level: str = "unknown"
    security_impact_level: str = "unknown"
    life_safety_impact_level: str = "unknown"

    @field_validator("incident_type")
    @classmethod
    def valid_type(cls, value):
        if value not in INCIDENT_TYPES:
            raise ValueError("Unsupported incident type")
        return value

    @field_validator("severity")
    @classmethod
    def valid_severity(cls, value):
        if value not in SEVERITIES:
            raise ValueError("Unsupported severity")
        return value

    @field_validator("priority")
    @classmethod
    def valid_priority(cls, value):
        if value not in PRIORITIES:
            raise ValueError("Unsupported priority")
        return value

    @field_validator("guest_impact_level", "revenue_impact_level", "security_impact_level", "life_safety_impact_level")
    @classmethod
    def valid_impact(cls, value):
        if value not in IMPACTS:
            raise ValueError("Unsupported impact level")
        return value


class IncidentPatch(BaseModel):
    title: str | None = Field(None, min_length=3, max_length=180)
    description: str | None = Field(None, max_length=10000)
    closure_summary: str | None = Field(None, max_length=10000)
    closure_reason: str | None = Field(None, max_length=5000)


class ReasonWrite(BaseModel):
    reason: str | None = Field(None, max_length=2000)


class IncidentEmailWrite(BaseModel):
    summary: str | None = Field(None, max_length=5000)


class ChangeWrite(BaseModel):
    value: str
    reason: str = Field(min_length=3, max_length=2000)


class ParticipantWrite(BaseModel):
    user_id: str
    participant_role: str
    responsibility: str | None = Field(None, max_length=2000)


class TaskWrite(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    description: str | None = Field(None, max_length=5000)
    task_type: str = "investigation"
    priority: str = "P3"
    assigned_user_id: str | None = None
    assigned_role: str | None = None
    due_at: datetime | None = None
    verification_required: bool = False


class TaskAction(BaseModel):
    output_summary: str | None = Field(None, max_length=5000)
    reason: str | None = Field(None, max_length=2000)
    assigned_user_id: str | None = None


class ChecklistAction(BaseModel):
    reason: str | None = Field(None, max_length=2000)
    evidence_reference: str | None = Field(None, max_length=500)
    notes: str | None = Field(None, max_length=2000)


class SourceWrite(BaseModel):
    source_type: str = Field(max_length=40)
    source_entity_type: str | None = Field(None, max_length=60)
    source_entity_id: UUID | None = None
    relationship_type: str = "related"
    source_status: str | None = Field(None, max_length=30)


class EvidenceWrite(BaseModel):
    evidence_type: str
    title: str = Field(min_length=2, max_length=180)
    description: str | None = Field(None, max_length=5000)
    source_type: str | None = None
    source_entity_type: str | None = None
    source_entity_id: UUID | None = None
    artifact_reference: str | None = Field(None, max_length=500)
    checksum: str | None = Field(None, max_length=64)
    sensitivity: str = "normal"
    metadata: dict = Field(default_factory=dict)

    @field_validator("artifact_reference")
    @classmethod
    def safe_reference(cls, value):
        if value and (value.startswith(("/", "\\")) or ".." in value or ":\\" in value):
            raise ValueError("Artifact references must use an approved logical identifier")
        return value


class PlaybookWrite(BaseModel):
    property_id: UUID
    name: str = Field(min_length=2, max_length=160)
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{2,60}$")
    description: str | None = Field(None, max_length=10000)
    category: str = "general_incident_response"
    incident_types: list[str] = Field(default_factory=list, max_length=30)
    minimum_severity: str = "informational"
    maximum_severity: str = "critical"
    requires_incident_commander: bool = True
    requires_communications_lead: bool = False
    requires_technical_lead: bool = True
    maximum_runtime_seconds: int = Field(14400, ge=300, le=86400)


class VersionWrite(BaseModel):
    objective: str | None = Field(None, max_length=10000)
    scope: dict = Field(default_factory=dict)
    prerequisites: list = Field(default_factory=list)
    activation_criteria: dict = Field(default_factory=dict)
    escalation_policy: dict = Field(default_factory=dict)
    communication_plan: dict = Field(default_factory=dict)
    evidence_requirements: list = Field(default_factory=list)
    verification_requirements: list = Field(default_factory=list)
    recovery_criteria: list = Field(default_factory=list)
    closure_criteria: list = Field(default_factory=list)
    post_incident_requirements: dict = Field(default_factory=dict)
    workflow_version_id: UUID | None = None
    change_summary: str | None = Field(None, max_length=5000)


class StepWrite(BaseModel):
    step_key: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(None, max_length=5000)
    phase: str
    step_type: str
    sequence_order: int = Field(0, ge=0, le=1000)
    required: bool = True
    owner_role: str | None = None
    expected_duration_seconds: int | None = Field(None, ge=0, le=86400)
    timeout_seconds: int = Field(3600, ge=30, le=86400)
    maximum_retries: int = Field(1, ge=0, le=3)
    action_key: str | None = None
    compensation_action_key: str | None = None
    checklist_definition: list = Field(default_factory=list)
    input_definition: dict = Field(default_factory=dict)
    output_definition: dict = Field(default_factory=dict)
    evidence_required: bool = False
    approval_required: bool = False
    verification_required: bool = False
    continue_on_failure: bool = False


class DecisionWrite(BaseModel):
    title: str = Field(max_length=180)
    question: str = Field(max_length=2000)
    options: list[str] = Field(min_length=2, max_length=20)
    approval_required: bool = False


class DecideWrite(BaseModel):
    decision: str = Field(max_length=120)
    rationale: str = Field(min_length=3, max_length=5000)


class TemplateWrite(BaseModel):
    property_id: UUID
    name: str = Field(max_length=160)
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{2,60}$")
    communication_type: str
    audience_type: str
    subject_template: str = Field(max_length=240)
    body_template: str = Field(max_length=10000)
    allowed_fields: list[str] = Field(default_factory=list)
    enabled: bool = True


class CommunicationWrite(BaseModel):
    template_id: UUID
    audience_reference: str | None = Field(None, max_length=200)
    extra_fields: dict = Field(default_factory=dict)
    severity: str | None = None


class EscalationRuleWrite(BaseModel):
    property_id: UUID
    name: str = Field(max_length=160)
    incident_type: str | None = None
    minimum_severity: str = "medium"
    priority: str | None = None
    trigger_condition: dict = Field(default_factory=dict)
    elapsed_minutes: int | None = Field(None, ge=1, le=10080)
    task_overdue_minutes: int | None = Field(None, ge=1, le=10080)
    target_role: str | None = None
    target_user_id: str | None = None
    escalation_action: str = "notify"
    repeat_interval_minutes: int = Field(60, ge=5, le=10080)
    maximum_escalations: int = Field(1, ge=1, le=20)
    enabled: bool = True


class ImpactWrite(BaseModel):
    guest_impact_level: str = "unknown"
    revenue_impact_level: str = "unknown"
    security_impact_level: str = "unknown"
    operational_impact_level: str = "unknown"
    life_safety_impact_level: str = "unknown"
    affected_guest_rooms: int | None = Field(None, ge=0)
    affected_scope: dict = Field(default_factory=dict)
    confidence_score: int = Field(0, ge=0, le=100)
    life_safety_confirmed: bool = False


class CauseWrite(BaseModel):
    cause_status: str
    cause_category: str
    primary_entity_type: str | None = None
    primary_entity_id: UUID | None = None
    summary: str | None = Field(None, max_length=10000)
    evidence: list = Field(default_factory=list)
    confidence_score: int = Field(0, ge=0, le=100)


class ReviewWrite(BaseModel):
    facilitator_id: str | None = None
    scheduled_at: datetime | None = None
    review_content: dict = Field(default_factory=dict)


class FollowUpWrite(BaseModel):
    title: str = Field(max_length=180)
    description: str | None = Field(None, max_length=5000)
    action_type: str = "corrective"
    priority: str = "P3"
    assigned_user_id: str | None = None
    due_at: datetime | None = None


class StepCompleteWrite(BaseModel):
    verification_status: str | None = None
    approval_outcome: str | None = Field(None, pattern=r"^(approved|rejected)$")
    evidence_reference: str | None = Field(None, max_length=500)


def _authorized_ids(db, user):
    if user.role in {"admin"}:
        return None
    return [row.property_id for row in db.query(UserPropertyAccess).filter_by(user_id=user.id, enabled=True).all()]


def _scope(query, column, db, user):
    allowed = _authorized_ids(db, user)
    return query if allowed is None else query.filter(column.in_(allowed))


def _property_access(db, user, property_id):
    if not db.get(Property, property_id):
        raise HTTPException(404, "Property not found")
    allowed = _authorized_ids(db, user)
    if allowed is not None and property_id not in allowed:
        raise HTTPException(403, "Incident property is not authorized")


def _incident(db, user, incident_id):
    row = _scope(db.query(OperationalIncident).filter_by(id=incident_id), OperationalIncident.property_id, db, user).first()
    if not row:
        raise HTTPException(404, "Incident not found")
    return row


def _playbook(db, user, playbook_id):
    row = _scope(db.query(OperationalPlaybook).filter_by(id=playbook_id), OperationalPlaybook.property_id, db, user).first()
    if not row:
        raise HTTPException(404, "Playbook not found")
    return row


def _page(query, page, page_size, order):
    total = query.count()
    return {"items": query.order_by(order).offset((page - 1) * page_size).limit(page_size).all(), "total": total, "page": page, "page_size": page_size}


def _audit_commit(db, user, action, entity, row, description):
    create_audit_log(db, user.username, action, entity, str(row.id), description)
    db.commit()
    db.refresh(row)
    return row


def _similar(db, payload):
    query = db.query(OperationalIncident).filter(
        OperationalIncident.property_id == payload.property_id,
        OperationalIncident.status.notin_(("closed", "cancelled", "duplicate", "merged")),
        OperationalIncident.incident_type == payload.incident_type,
    )
    if payload.correlation_key:
        query = query.filter(or_(OperationalIncident.correlation_key == payload.correlation_key, OperationalIncident.title.ilike(f"%{payload.title[:40]}%")))
    else:
        query = query.filter(OperationalIncident.title.ilike(f"%{payload.title[:40]}%"))
    return query.limit(10).all()


def _source_property(db, source_type, source_id):
    if source_type == "alert":
        source = db.get(Alert, source_id)
        device = db.get(Device, source.device_id) if source else None
        return getattr(device, "property_id", None) if device else None
    if source_type == "ticket":
        source = db.get(Ticket, source_id)
        device = db.get(Device, source.device_id) if source and source.device_id else None
        return getattr(device, "property_id", None) if device else None
    if source_type == "internal_event":
        source = db.query(AutomationEventRecord).filter(
            or_(AutomationEventRecord.id == source_id, AutomationEventRecord.event_id == source_id)
        ).first()
        return source.property_id if source else None
    if source_type == "technology_service":
        source = db.get(HospitalityTechnologyService, source_id)
        return source.property_id if source else None
    return None


# Playbook routes are declared before /{incident_id} to avoid dynamic-route ambiguity.
@router.get("/playbooks")
def playbooks(property_id: UUID | None = None, db: Session = Depends(get_db), user=Depends(reader)):
    query = _scope(db.query(OperationalPlaybook), OperationalPlaybook.property_id, db, user)
    if property_id:
        _property_access(db, user, property_id)
        query = query.filter_by(property_id=property_id)
    return {"items": query.order_by(OperationalPlaybook.name).limit(100).all()}


@router.post("/playbooks", status_code=201)
def create_playbook(payload: PlaybookWrite, db: Session = Depends(get_db), user=Depends(admin)):
    _property_access(db, user, payload.property_id)
    if db.query(OperationalPlaybook).filter_by(property_id=payload.property_id, code=payload.code).first():
        raise HTTPException(409, "Playbook code already exists for this property")
    values = payload.model_dump()
    values["incident_types"] = json.dumps(values["incident_types"], separators=(",", ":"))
    row = OperationalPlaybook(**values, created_by=user.username)
    db.add(row)
    db.flush()
    return _audit_commit(db, user, "INCIDENT_PLAYBOOK_CREATED", "OperationalPlaybook", row, f"Created playbook {row.code}")


@router.get("/playbooks/{playbook_id}")
def get_playbook(playbook_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    return _playbook(db, user, playbook_id)


@router.patch("/playbooks/{playbook_id}")
def update_playbook(playbook_id: UUID, payload: PlaybookWrite, db: Session = Depends(get_db), user=Depends(admin)):
    row = _playbook(db, user, playbook_id)
    if row.property_id != payload.property_id:
        raise HTTPException(422, "Playbook property cannot be changed")
    for key, value in payload.model_dump().items():
        setattr(row, key, json.dumps(value, separators=(",", ":")) if key == "incident_types" else value)
    row.updated_by = user.username
    return _audit_commit(db, user, "INCIDENT_PLAYBOOK_UPDATED", "OperationalPlaybook", row, f"Updated playbook {row.code}")


@router.post("/playbooks/{playbook_id}/{action}")
def playbook_toggle(playbook_id: UUID, action: str, db: Session = Depends(get_db), user=Depends(admin)):
    if action not in {"enable", "disable"}:
        raise HTTPException(404, "Unsupported playbook action")
    row = _playbook(db, user, playbook_id)
    if action == "enable" and not row.current_version_id:
        raise HTTPException(409, "An approved version must be active first")
    row.enabled = action == "enable"
    row.status = "active" if row.enabled else "paused"
    return _audit_commit(db, user, f"INCIDENT_PLAYBOOK_{action.upper()}D", "OperationalPlaybook", row, f"{action.title()}d playbook {row.code}")


@router.get("/playbooks/{playbook_id}/versions")
def playbook_versions(playbook_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    row = _playbook(db, user, playbook_id)
    return {"items": db.query(OperationalPlaybookVersion).filter_by(playbook_id=row.id).order_by(OperationalPlaybookVersion.version_number.desc()).all()}


@router.post("/playbooks/{playbook_id}/versions", status_code=201)
def create_playbook_version(playbook_id: UUID, payload: VersionWrite, db: Session = Depends(get_db), user=Depends(admin)):
    playbook = _playbook(db, user, playbook_id)
    number = (db.query(OperationalPlaybookVersion).filter_by(playbook_id=playbook.id).count() + 1)
    values = payload.model_dump()
    for key in ("scope", "prerequisites", "activation_criteria", "escalation_policy", "communication_plan", "evidence_requirements", "verification_requirements", "recovery_criteria", "closure_criteria", "post_incident_requirements"):
        values[key] = json.dumps(values[key], separators=(",", ":"))
    row = OperationalPlaybookVersion(playbook_id=playbook.id, version_number=number, created_by=user.username, **values)
    db.add(row)
    db.flush()
    return _audit_commit(db, user, "INCIDENT_PLAYBOOK_VERSION_CREATED", "OperationalPlaybookVersion", row, f"Created version {number}")


def _version_scope(db, user, version_id):
    version = db.get(OperationalPlaybookVersion, version_id)
    if not version:
        raise HTTPException(404, "Playbook version not found")
    return version, _playbook(db, user, version.playbook_id)


@router.get("/playbook-versions/{version_id}")
def get_playbook_version(version_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    return _version_scope(db, user, version_id)[0]


@router.get("/playbook-versions/{version_id}/steps")
def playbook_steps(version_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    version, _ = _version_scope(db, user, version_id)
    return {"items": db.query(OperationalPlaybookStep).filter_by(playbook_version_id=version.id).order_by(OperationalPlaybookStep.sequence_order).all()}


@router.post("/playbook-versions/{version_id}/steps", status_code=201)
def create_playbook_step(version_id: UUID, payload: StepWrite, db: Session = Depends(get_db), user=Depends(admin)):
    version, _ = _version_scope(db, user, version_id)
    if version.status in {"approved", "superseded", "retired"}:
        raise HTTPException(409, "Approved playbook versions are immutable")
    values = payload.model_dump()
    for key in ("checklist_definition", "input_definition", "output_definition"):
        values[key] = json.dumps(values[key], separators=(",", ":"))
    row = OperationalPlaybookStep(playbook_version_id=version.id, **values)
    db.add(row)
    db.flush()
    return _audit_commit(db, user, "INCIDENT_PLAYBOOK_STEP_CREATED", "OperationalPlaybookStep", row, f"Created step {row.step_key}")


@router.patch("/playbook-versions/{version_id}/steps/{step_id}")
def update_playbook_step(version_id: UUID, step_id: UUID, payload: StepWrite, db: Session = Depends(get_db), user=Depends(admin)):
    version, _ = _version_scope(db, user, version_id)
    if version.status in {"approved", "superseded", "retired"}:
        raise HTTPException(409, "Approved playbook versions are immutable")
    row = db.query(OperationalPlaybookStep).filter_by(id=step_id, playbook_version_id=version.id).first()
    if not row:
        raise HTTPException(404, "Playbook step not found")
    values = payload.model_dump()
    for key in ("checklist_definition", "input_definition", "output_definition"):
        values[key] = json.dumps(values[key], separators=(",", ":"))
    for key, value in values.items():
        setattr(row, key, value)
    return _audit_commit(db, user, "INCIDENT_PLAYBOOK_STEP_UPDATED", "OperationalPlaybookStep", row, f"Updated step {row.step_key}")


@router.delete("/playbook-versions/{version_id}/steps/{step_id}", status_code=204)
def delete_playbook_step(version_id: UUID, step_id: UUID, db: Session = Depends(get_db), user=Depends(admin)):
    version, _ = _version_scope(db, user, version_id)
    if version.status != "draft":
        raise HTTPException(409, "Only draft playbook steps can be removed")
    row = db.query(OperationalPlaybookStep).filter_by(id=step_id, playbook_version_id=version.id).first()
    if not row:
        raise HTTPException(404, "Playbook step not found")
    db.delete(row)
    db.commit()


@router.post("/playbook-versions/{version_id}/{action}")
def version_action(version_id: UUID, action: str, reason: ReasonWrite | None = None, db: Session = Depends(get_db), user=Depends(admin)):
    version, playbook = _version_scope(db, user, version_id)
    steps = db.query(OperationalPlaybookStep).filter_by(playbook_version_id=version.id).all()
    if action == "validate":
        result = validate_playbook(db, playbook, version, steps)
        version.checksum = version_checksum(version, steps)
        version.status = "validated" if result["valid"] else "validation_failed"
        db.commit()
        return {**result, "checksum": version.checksum, "status": version.status}
    allowed = {
        "submit-review": ({"validated"}, "under_review"),
        "approve": ({"under_review"}, "approved"),
        "reject": ({"under_review"}, "rejected"),
        "activate": ({"approved"}, "approved"),
    }
    if action not in allowed:
        raise HTTPException(404, "Unsupported version action")
    sources, target = allowed[action]
    if version.status not in sources:
        raise HTTPException(409, f"Cannot {action} version in {version.status} state")
    if action == "reject" and (not reason or not reason.reason):
        raise HTTPException(422, "A rejection reason is required")
    version.status = target
    now = datetime.now(timezone.utc)
    if action == "approve":
        version.approved_by, version.approved_at = user.username, now
    elif action == "submit-review":
        version.reviewed_by, version.reviewed_at = user.username, now
    elif action == "activate":
        previous = db.query(OperationalPlaybookVersion).filter(
            OperationalPlaybookVersion.playbook_id == playbook.id,
            OperationalPlaybookVersion.id != version.id,
            OperationalPlaybookVersion.status == "approved",
        ).all()
        for item in previous:
            item.status = "superseded"
        playbook.current_version_id = version.id
    return _audit_commit(db, user, f"INCIDENT_PLAYBOOK_VERSION_{action.upper().replace('-', '_')}", "OperationalPlaybookVersion", version, f"{action} version {version.version_number}")


@router.get("/communication-templates")
def communication_templates(property_id: UUID | None = None, db: Session = Depends(get_db), user=Depends(reader)):
    query = _scope(db.query(IncidentCommunicationTemplate), IncidentCommunicationTemplate.property_id, db, user)
    if property_id:
        _property_access(db, user, property_id)
        query = query.filter_by(property_id=property_id)
    return {"items": query.order_by(IncidentCommunicationTemplate.name).limit(100).all()}


@router.post("/communication-templates", status_code=201)
def create_communication_template(payload: TemplateWrite, db: Session = Depends(get_db), user=Depends(admin)):
    _property_access(db, user, payload.property_id)
    values = payload.model_dump()
    values["allowed_fields"] = json.dumps(values["allowed_fields"], separators=(",", ":"))
    row = IncidentCommunicationTemplate(**values, created_by=user.username)
    db.add(row)
    db.flush()
    return _audit_commit(db, user, "INCIDENT_COMMUNICATION_TEMPLATE_CREATED", "IncidentCommunicationTemplate", row, f"Created template {row.code}")


@router.patch("/communication-templates/{template_id}")
def update_communication_template(template_id: UUID, payload: TemplateWrite, db: Session = Depends(get_db), user=Depends(admin)):
    row = _scope(db.query(IncidentCommunicationTemplate).filter_by(id=template_id), IncidentCommunicationTemplate.property_id, db, user).first()
    if not row:
        raise HTTPException(404, "Communication template not found")
    if row.property_id != payload.property_id:
        raise HTTPException(422, "Template property cannot change")
    values = payload.model_dump()
    values["allowed_fields"] = json.dumps(values["allowed_fields"], separators=(",", ":"))
    for key, value in values.items():
        setattr(row, key, value)
    row.updated_by = user.username
    return _audit_commit(db, user, "INCIDENT_COMMUNICATION_TEMPLATE_UPDATED", "IncidentCommunicationTemplate", row, f"Updated template {row.code}")


@router.get("/escalation-rules")
def escalation_rules(property_id: UUID | None = None, db: Session = Depends(get_db), user=Depends(reader)):
    query = _scope(db.query(IncidentEscalationRule), IncidentEscalationRule.property_id, db, user)
    if property_id:
        _property_access(db, user, property_id)
        query = query.filter_by(property_id=property_id)
    return {"items": query.order_by(IncidentEscalationRule.name).limit(100).all()}


@router.post("/escalation-rules", status_code=201)
def create_escalation_rule(payload: EscalationRuleWrite, db: Session = Depends(get_db), user=Depends(admin)):
    _property_access(db, user, payload.property_id)
    values = payload.model_dump()
    values["trigger_condition"] = json.dumps(values["trigger_condition"], separators=(",", ":"))
    row = IncidentEscalationRule(**values, created_by=user.username)
    db.add(row)
    db.flush()
    return _audit_commit(db, user, "INCIDENT_ESCALATION_RULE_CREATED", "IncidentEscalationRule", row, f"Created escalation rule {row.name}")


@router.patch("/escalation-rules/{rule_id}")
def update_escalation_rule(rule_id: UUID, payload: EscalationRuleWrite, db: Session = Depends(get_db), user=Depends(admin)):
    row = _scope(db.query(IncidentEscalationRule).filter_by(id=rule_id), IncidentEscalationRule.property_id, db, user).first()
    if not row:
        raise HTTPException(404, "Escalation rule not found")
    if row.property_id != payload.property_id:
        raise HTTPException(422, "Escalation rule property cannot change")
    values = payload.model_dump()
    values["trigger_condition"] = json.dumps(values["trigger_condition"], separators=(",", ":"))
    for key, value in values.items():
        setattr(row, key, value)
    row.updated_by = user.username
    return _audit_commit(db, user, "INCIDENT_ESCALATION_RULE_UPDATED", "IncidentEscalationRule", row, f"Updated escalation rule {row.name}")


@router.post("/escalation-rules/{rule_id}/{action}")
def toggle_escalation_rule(rule_id: UUID, action: str, db: Session = Depends(get_db), user=Depends(admin)):
    if action not in {"enable", "disable"}:
        raise HTTPException(404, "Unsupported escalation action")
    row = _scope(db.query(IncidentEscalationRule).filter_by(id=rule_id), IncidentEscalationRule.property_id, db, user).first()
    if not row:
        raise HTTPException(404, "Escalation rule not found")
    row.enabled = action == "enable"
    return _audit_commit(db, user, f"INCIDENT_ESCALATION_RULE_{action.upper()}D", "IncidentEscalationRule", row, f"{action.title()}d escalation rule")


@router.get("/playbook-runs/{run_id}")
def get_playbook_run(run_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    row = db.get(IncidentPlaybookRun, run_id)
    if not row:
        raise HTTPException(404, "Playbook run not found")
    _incident(db, user, row.incident_id)
    return row


@router.get("/playbook-runs/{run_id}/steps")
def get_playbook_run_steps(run_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    run = get_playbook_run(run_id, db, user)
    return {"items": db.query(IncidentPlaybookStepRun).filter_by(incident_playbook_run_id=run.id).order_by(IncidentPlaybookStepRun.created_at).all()}


@router.post("/playbook-runs/{run_id}/control/{action}")
def control_playbook_run(run_id: UUID, action: str, db: Session = Depends(get_db), user=Depends(operator)):
    run = get_playbook_run(run_id, db, user)
    incident = _incident(db, user, run.incident_id)
    now = datetime.now(timezone.utc)
    if action == "pause" and run.status in {"running", "waiting_for_human", "waiting_for_approval", "monitoring"}:
        run.status, run.paused_at = "paused", now
    elif action == "resume" and run.status == "paused":
        run.status, run.resumed_at = "running", now
    elif action == "cancel" and run.status not in {"completed", "failed", "cancelled"}:
        run.status, run.cancellation_requested, run.completed_at = "cancelled", True, now
    else:
        raise HTTPException(409, f"Cannot {action} this playbook run")
    add_timeline(db, incident, f"playbook_{action}", f"Playbook run {action}d", user.username, source_id=run.id)
    _audit_commit(db, user, f"INCIDENT_PLAYBOOK_RUN_{action.upper()}D", "IncidentPlaybookRun", run, f"{action.title()}d incident playbook run")
    publish("incident_playbook_progress", incident, playbook_run_id=str(run.id), run_status=run.status)
    return run


@router.post("/playbook-runs/{run_id}/retry-step")
def retry_playbook_step(run_id: UUID, step_run_id: UUID, db: Session = Depends(get_db), user=Depends(operator)):
    run = get_playbook_run(run_id, db, user)
    row = db.query(IncidentPlaybookStepRun).filter_by(id=step_run_id, incident_playbook_run_id=run.id).first()
    if not row:
        raise HTTPException(404, "Playbook step run not found")
    retry_step_service(db, run, row, user.username)
    incident = _incident(db, user, run.incident_id)
    add_timeline(db, incident, "playbook_step_retried", f"Playbook step retried: {row.step_key}", user.username, source_id=row.id)
    create_audit_log(db, user.username, "INCIDENT_PLAYBOOK_STEP_RETRIED", "IncidentPlaybookStepRun", str(row.id), f"Retried step {row.step_key}")
    db.commit()
    return row


@router.post("/playbook-runs/{run_id}/compensate-step")
def compensate_run_step(run_id: UUID, step_run_id: UUID, db: Session = Depends(get_db), user=Depends(admin)):
    run = get_playbook_run(run_id, db, user)
    row = db.query(IncidentPlaybookStepRun).filter_by(id=step_run_id, incident_playbook_run_id=run.id).first()
    if not row:
        raise HTTPException(404, "Playbook step run not found")
    compensate_playbook_step(db, run, row, user.username)
    incident = _incident(db, user, run.incident_id)
    add_timeline(db, incident, "playbook_step_compensated", f"Playbook step compensated: {row.step_key}", user.username, source_id=row.id)
    create_audit_log(db, user.username, "INCIDENT_PLAYBOOK_STEP_COMPENSATED", "IncidentPlaybookStepRun", str(row.id), f"Compensated step {row.step_key}")
    db.commit()
    return row


@router.post("/playbook-runs/{run_id}/steps/{step_run_id}/complete")
def complete_run_step(run_id: UUID, step_run_id: UUID, payload: StepCompleteWrite, db: Session = Depends(get_db), user=Depends(operator)):
    run = get_playbook_run(run_id, db, user)
    step = db.query(IncidentPlaybookStepRun).filter_by(id=step_run_id, incident_playbook_run_id=run.id).first()
    if not step:
        raise HTTPException(404, "Playbook step run not found")
    complete_playbook_step(
        db, run, step, user.username, payload.verification_status,
        payload.evidence_reference, payload.approval_outcome,
    )
    incident = _incident(db, user, run.incident_id)
    add_timeline(db, incident, "playbook_step_completed", f"Playbook step completed: {step.step_key}", user.username, source_id=step.id)
    create_audit_log(db, user.username, "INCIDENT_PLAYBOOK_STEP_COMPLETED", "IncidentPlaybookStepRun", str(step.id), f"Completed step {step.step_key}")
    db.commit()
    db.refresh(step)
    return step


@router.get("/reports/summary")
def report_summary(property_id: UUID | None = None, db: Session = Depends(get_db), user=Depends(reader),organization_id=Depends(organization_context)):
    query = _scope(db.query(OperationalIncident), OperationalIncident.property_id, db, user).filter(OperationalIncident.organization_id==organization_id)
    if property_id:
        _property_access(db, user, property_id)
        query = query.filter_by(property_id=property_id)
    rows = query.all()
    closed = [row for row in rows if row.closed_at]
    ack_seconds = [(row.acknowledged_at - row.detected_at).total_seconds() for row in rows if row.acknowledged_at]
    recovery_seconds = [(row.recovered_at - row.detected_at).total_seconds() for row in rows if row.recovered_at]
    return {
        "total": len(rows), "open": sum(row.status not in {"closed", "cancelled", "duplicate", "merged"} for row in rows),
        "P1": sum(row.priority == "P1" for row in rows), "P2": sum(row.priority == "P2" for row in rows),
        "critical": sum(row.severity == "critical" for row in rows),
        "without_commander": sum(row.status not in {"closed", "cancelled"} and not row.incident_commander_id for row in rows),
        "average_acknowledgement_seconds": sum(ack_seconds) / len(ack_seconds) if ack_seconds else None,
        "average_recovery_seconds": sum(recovery_seconds) / len(recovery_seconds) if recovery_seconds else None,
        "closed": len(closed),
    }


@router.get("")
def list_incidents(
    search: str | None = None, property_id: UUID | None = None, status: str | None = None,
    severity: str | None = None, incident_type: str | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db), user=Depends(reader),organization_id=Depends(organization_context),
):
    query = _scope(db.query(OperationalIncident), OperationalIncident.property_id, db, user).filter(OperationalIncident.organization_id==organization_id)
    if property_id:
        _property_access(db, user, property_id)
        query = query.filter_by(property_id=property_id)
    if status:
        query = query.filter_by(status=status)
    if severity:
        query = query.filter_by(severity=severity)
    if incident_type:
        query = query.filter_by(incident_type=incident_type)
    if search:
        query = query.filter(or_(OperationalIncident.title.ilike(f"%{search}%"), OperationalIncident.incident_number.ilike(f"%{search}%")))
    return _page(query, page, page_size, OperationalIncident.created_at.desc())


@router.post("/similar")
def similar_incidents(payload: IncidentWrite, db: Session = Depends(get_db), user=Depends(reader)):
    _property_access(db, user, payload.property_id)
    return {"items": _similar(db, payload)}


@router.post("", status_code=201)
def create_incident(payload: IncidentWrite, db: Session = Depends(get_db), user=Depends(operator),organization_id=Depends(organization_context)):
    _property_access(db, user, payload.property_id)
    if not isinstance(organization_id,UUID):organization_id=db.query(Property.organization_id).filter(Property.id==payload.property_id).scalar()
    similar = _similar(db, payload)
    if payload.correlation_key and any(row.correlation_key == payload.correlation_key for row in similar):
        raise HTTPException(409, {"message": "A correlated open incident already exists", "incident_id": str(similar[0].id)})
    row = OperationalIncident(
        **payload.model_dump(), incident_number=f"INC-{datetime.now(timezone.utc):%Y%m%d}-{secrets.token_hex(3).upper()}",
        status="declared", declared_at=datetime.now(timezone.utc), created_by=user.username,organization_id=organization_id,
    )
    db.add(row)
    db.flush()
    add_timeline(db, row, "incident_declared", "Incident declared", user.username, row.description, row.severity)
    if payload.source_type:
        db.add(OperationalIncidentSource(
            incident_id=row.id, source_type=payload.source_type,
            source_entity_type=payload.source_reference_type, source_entity_id=payload.source_reference_id,
            relationship_type="triggered", linked_by=user.username,
        ))
    generate_recommendations(db, row)
    _audit_commit(db, user, "INCIDENT_DECLARED", "OperationalIncident", row, f"Declared {row.incident_number}")
    publish("incident_declared", row)
    if row.priority in {"P1", "P2"}:
        from app.services.incident_notification_service import notify_incident
        notify_incident(db, row, "declared", "A high-priority incident requires reviewed command assignment.")
    return row


def _create_from_source(source_type, source_id, payload, db, user):
    source_property = _source_property(db, source_type, source_id)
    if source_property is None:
        raise HTTPException(404, "Incident source was not found or has no property context")
    if source_property != payload.property_id:
        raise HTTPException(422, "Incident and source property must match")
    values = payload.model_copy(update={
        "source_type": source_type,
        "source_reference_type": source_type,
        "source_reference_id": source_id,
    })
    return create_incident(values, db, user)


@router.post("/from-alert/{alert_id}", status_code=201)
def incident_from_alert(alert_id: UUID, payload: IncidentWrite, db: Session = Depends(get_db), user=Depends(operator)):
    return _create_from_source("alert", alert_id, payload, db, user)


@router.post("/from-ticket/{ticket_id}", status_code=201)
def incident_from_ticket(ticket_id: UUID, payload: IncidentWrite, db: Session = Depends(get_db), user=Depends(operator)):
    return _create_from_source("ticket", ticket_id, payload, db, user)


@router.post("/from-event/{event_id}", status_code=201)
def incident_from_event(event_id: UUID, payload: IncidentWrite, db: Session = Depends(get_db), user=Depends(operator)):
    return _create_from_source("internal_event", event_id, payload, db, user)


@router.post("/from-service/{service_id}", status_code=201)
def incident_from_service(service_id: UUID, payload: IncidentWrite, db: Session = Depends(get_db), user=Depends(operator)):
    return _create_from_source("technology_service", service_id, payload, db, user)


@router.get("/{incident_id}")
def get_incident(incident_id: UUID, db: Session = Depends(get_db), user=Depends(reader),organization_id=Depends(organization_context)):
    row=_incident(db,user,incident_id)
    if row.organization_id!=organization_id:raise HTTPException(404,"Incident not found")
    return row


@router.patch("/{incident_id}")
def update_incident(incident_id: UUID, payload: IncidentPatch, db: Session = Depends(get_db), user=Depends(operator)):
    row = _incident(db, user, incident_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    row.updated_by = user.username
    add_timeline(db, row, "note", "Incident details updated", user.username)
    return _audit_commit(db, user, "INCIDENT_UPDATED", "OperationalIncident", row, f"Updated {row.incident_number}")


def _state_action(db, user, incident_id, target, payload):
    row = _incident(db, user, incident_id)
    transition(db, row, target, user.username, payload.reason if payload else None)
    if target == "closed":
        ensure_post_incident_review(db, row)
    db.commit()
    db.refresh(row)
    return row


@router.post("/{incident_id}/acknowledge")
def acknowledge(incident_id: UUID, payload: ReasonWrite = ReasonWrite(), db: Session = Depends(get_db), user=Depends(operator)):
    return _state_action(db, user, incident_id, "acknowledged", payload)


@router.post("/{incident_id}/contain")
def contain(incident_id: UUID, payload: ReasonWrite, db: Session = Depends(get_db), user=Depends(operator)):
    return _state_action(db, user, incident_id, "contained", payload)


@router.post("/{incident_id}/mitigate")
def mitigate(incident_id: UUID, payload: ReasonWrite, db: Session = Depends(get_db), user=Depends(operator)):
    return _state_action(db, user, incident_id, "mitigating", payload)


@router.post("/{incident_id}/declare-recovery")
def declare_recovery(incident_id: UUID, payload: ReasonWrite, db: Session = Depends(get_db), user=Depends(operator)):
    return _state_action(db, user, incident_id, "recovered", payload)


@router.post("/{incident_id}/resolve")
def resolve(incident_id: UUID, payload: ReasonWrite, db: Session = Depends(get_db), user=Depends(operator)):
    return _state_action(db, user, incident_id, "resolved", payload)


@router.post("/{incident_id}/close")
def close(incident_id: UUID, payload: ReasonWrite, db: Session = Depends(get_db), user=Depends(admin)):
    return _state_action(db, user, incident_id, "closed", payload)


@router.post("/{incident_id}/reopen")
def reopen(incident_id: UUID, payload: ReasonWrite, db: Session = Depends(get_db), user=Depends(admin)):
    if not payload.reason:
        raise HTTPException(422, "A reopen reason is required")
    return _state_action(db, user, incident_id, "investigating", payload)


@router.post("/{incident_id}/cancel")
def cancel(incident_id: UUID, payload: ReasonWrite, db: Session = Depends(get_db), user=Depends(admin)):
    return _state_action(db, user, incident_id, "cancelled", payload)


@router.post("/{incident_id}/change-severity")
def change_severity(incident_id: UUID, payload: ChangeWrite, db: Session = Depends(get_db), user=Depends(operator)):
    if payload.value not in SEVERITIES:
        raise HTTPException(422, "Unsupported severity")
    row = _incident(db, user, incident_id)
    old, row.severity = row.severity, payload.value
    add_timeline(db, row, "severity_changed", f"Severity changed to {payload.value}", user.username, payload.reason, payload.value)
    _audit_commit(db, user, "INCIDENT_SEVERITY_CHANGED", "OperationalIncident", row, f"{old} to {row.severity}: {payload.reason}")
    publish("incident_severity_changed", row, previous_severity=old)
    return row


@router.post("/{incident_id}/change-priority")
def change_priority(incident_id: UUID, payload: ChangeWrite, db: Session = Depends(get_db), user=Depends(operator)):
    if payload.value not in PRIORITIES:
        raise HTTPException(422, "Unsupported priority")
    row = _incident(db, user, incident_id)
    old, row.priority = row.priority, payload.value
    add_timeline(db, row, "priority_changed", f"Priority changed to {payload.value}", user.username, payload.reason)
    return _audit_commit(db, user, "INCIDENT_PRIORITY_CHANGED", "OperationalIncident", row, f"{old} to {row.priority}: {payload.reason}")


@router.post("/{incident_id}/assign-commander")
def assign_commander(incident_id: UUID, user_id: str, db: Session = Depends(get_db), user=Depends(operator)):
    row = _incident(db, user, incident_id)
    commander = db.get(User, user_id)
    if not commander:
        raise HTTPException(404, "Commander user not found")
    allowed = _authorized_ids(db, commander)
    if allowed is not None and row.property_id not in allowed:
        raise HTTPException(422, "Commander does not have property access")
    row.incident_commander_id = user_id
    existing = db.query(IncidentParticipant).filter_by(incident_id=row.id, user_id=user_id, participant_role="incident_commander").first()
    if not existing:
        db.add(IncidentParticipant(incident_id=row.id, user_id=user_id, participant_role="incident_commander", assigned_by=user.username))
    add_timeline(db, row, "participant_joined", "Incident commander assigned", user.username)
    return _audit_commit(db, user, "INCIDENT_COMMANDER_ASSIGNED", "OperationalIncident", row, f"Assigned commander to {row.incident_number}")


@router.post("/{incident_id}/mark-duplicate")
def mark_duplicate(incident_id: UUID, canonical_incident_id: UUID, payload: ReasonWrite, db: Session = Depends(get_db), user=Depends(admin)):
    row, canonical = _incident(db, user, incident_id), _incident(db, user, canonical_incident_id)
    if row.id == canonical.id or row.property_id != canonical.property_id:
        raise HTTPException(422, "Duplicate incidents must be different and in the same property")
    row.duplicate_of_id = canonical.id
    transition(db, row, "duplicate", user.username, payload.reason)
    db.add(OperationalIncidentSource(incident_id=canonical.id, source_type="internal_event", source_entity_type="incident", source_entity_id=row.id, relationship_type="duplicate_of", linked_by=user.username))
    db.commit()
    return row


@router.post("/{incident_id}/merge")
def merge_incident(incident_id: UUID, canonical_incident_id: UUID, payload: ReasonWrite, db: Session = Depends(get_db), user=Depends(admin)):
    row, canonical = _incident(db, user, incident_id), _incident(db, user, canonical_incident_id)
    if row.id == canonical.id or row.property_id != canonical.property_id:
        raise HTTPException(422, "Merged incidents must be different and in the same property")
    for source in db.query(OperationalIncidentSource).filter_by(incident_id=row.id).all():
        duplicate = db.query(OperationalIncidentSource).filter_by(incident_id=canonical.id, source_type=source.source_type, source_entity_id=source.source_entity_id).first()
        if not duplicate:
            db.add(OperationalIncidentSource(incident_id=canonical.id, source_type=source.source_type, source_entity_type=source.source_entity_type, source_entity_id=source.source_entity_id, relationship_type="contributing", source_status=source.source_status, linked_by=user.username))
    row.duplicate_of_id = canonical.id
    transition(db, row, "merged", user.username, payload.reason)
    add_timeline(db, canonical, "source_linked", f"Merged incident {row.incident_number}", user.username, payload.reason, source_id=row.id)
    db.commit()
    return {"canonical_incident_id": canonical.id, "merged_incident_id": row.id, "status": "merged"}


@router.get("/{incident_id}/playbook-recommendations")
def playbook_recommendations(incident_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    row = _incident(db, user, incident_id)
    result = select_playbooks(db, row)
    return {"items": [{"playbook": item["playbook"], "score": item["score"], "reasons": item["reasons"]} for item in result["items"]], "requires_human_selection": result["requires_human_selection"], "conflict": result["conflict"]}


@router.post("/{incident_id}/playbooks/{playbook_id}/start", status_code=201)
def start_incident_playbook(incident_id: UUID, playbook_id: UUID, db: Session = Depends(get_db), user=Depends(operator)):
    incident, playbook = _incident(db, user, incident_id), _playbook(db, user, playbook_id)
    if incident.property_id != playbook.property_id:
        raise HTTPException(422, "Incident and playbook property must match")
    run = start_playbook(db, incident, playbook, user.username)
    db.commit()
    db.refresh(run)
    return run


@router.get("/{incident_id}/playbook-runs")
def incident_playbook_runs(incident_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    row = _incident(db, user, incident_id)
    return {"items": db.query(IncidentPlaybookRun).filter_by(incident_id=row.id).order_by(IncidentPlaybookRun.created_at.desc()).all()}


@router.get("/{incident_id}/participants")
def participants(incident_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    row = _incident(db, user, incident_id)
    return {"items": db.query(IncidentParticipant).filter_by(incident_id=row.id, active=True).all()}


@router.post("/{incident_id}/participants", status_code=201)
def add_participant(incident_id: UUID, payload: ParticipantWrite, db: Session = Depends(get_db), user=Depends(operator)):
    incident = _incident(db, user, incident_id)
    if payload.participant_role not in PARTICIPANT_ROLES:
        raise HTTPException(422, "Unsupported participant role")
    member = db.get(User, payload.user_id)
    if not member:
        raise HTTPException(404, "Participant user not found")
    allowed = _authorized_ids(db, member)
    if allowed is not None and incident.property_id not in allowed:
        raise HTTPException(422, "Participant does not have property access")
    if payload.participant_role == "incident_commander":
        active = db.query(IncidentParticipant).filter_by(incident_id=incident.id, participant_role="incident_commander", active=True).first()
        if active:
            raise HTTPException(409, "Incident already has an active commander")
        incident.incident_commander_id = payload.user_id
    row = IncidentParticipant(incident_id=incident.id, **payload.model_dump(), assigned_by=user.username)
    db.add(row)
    db.flush()
    add_timeline(db, incident, "participant_joined", f"Participant added as {row.participant_role}", user.username)
    return _audit_commit(db, user, "INCIDENT_PARTICIPANT_ADDED", "IncidentParticipant", row, f"Added participant to {incident.incident_number}")


@router.delete("/{incident_id}/participants/{participant_id}", status_code=204)
def remove_participant(incident_id: UUID, participant_id: UUID, db: Session = Depends(get_db), user=Depends(operator)):
    incident = _incident(db, user, incident_id)
    row = db.query(IncidentParticipant).filter_by(id=participant_id, incident_id=incident.id, active=True).first()
    if not row:
        raise HTTPException(404, "Participant not found")
    if row.participant_role == "incident_commander" and incident.status not in {"closed", "cancelled"}:
        raise HTTPException(409, "Assign a replacement incident commander first")
    row.active, row.left_at = False, datetime.now(timezone.utc)
    add_timeline(db, incident, "participant_left", f"Participant removed from {row.participant_role}", user.username)
    create_audit_log(db, user.username, "INCIDENT_PARTICIPANT_REMOVED", "IncidentParticipant", str(row.id), "Deactivated incident participant")
    db.commit()


@router.get("/{incident_id}/tasks")
def tasks(incident_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    row = _incident(db, user, incident_id)
    return {"items": db.query(IncidentTask).filter_by(incident_id=row.id).order_by(IncidentTask.created_at).limit(500).all()}


@router.post("/{incident_id}/tasks", status_code=201)
def create_task(incident_id: UUID, payload: TaskWrite, db: Session = Depends(get_db), user=Depends(operator)):
    incident = _incident(db, user, incident_id)
    row = IncidentTask(incident_id=incident.id, **payload.model_dump(), created_by=user.username)
    db.add(row)
    db.flush()
    add_timeline(db, incident, "task_created", f"Task created: {row.title}", user.username, source_id=row.id)
    return _audit_commit(db, user, "INCIDENT_TASK_CREATED", "IncidentTask", row, f"Created task for {incident.incident_number}")


def _task_action(db, user, incident_id, task_id, target, payload):
    incident = _incident(db, user, incident_id)
    row = db.query(IncidentTask).filter_by(id=task_id, incident_id=incident.id).first()
    if not row:
        raise HTTPException(404, "Incident task not found")
    allowed = {
        "start": {"open", "assigned", "waiting"},
        "complete": {"in_progress", "assigned", "open"},
        "verify": {"completed"},
        "block": {"open", "assigned", "in_progress", "waiting"},
        "reassign": {"open", "assigned", "in_progress", "blocked", "waiting"},
    }
    if row.status not in allowed[target]:
        raise HTTPException(409, f"Cannot {target} task in {row.status} state")
    now = datetime.now(timezone.utc)
    if target == "start":
        row.status, row.started_at = "in_progress", now
    elif target == "complete":
        row.status, row.completed_at, row.completed_by, row.output_summary = "completed", now, user.username, payload.output_summary
    elif target == "verify":
        if not row.verification_required:
            raise HTTPException(409, "Task does not require verification")
        row.status, row.verified_at, row.verified_by = "verified", now, user.username
    elif target == "block":
        if not payload.reason:
            raise HTTPException(422, "A block reason is required")
        row.status, row.blocked_reason = "blocked", payload.reason
    elif target == "reassign":
        if not payload.assigned_user_id:
            raise HTTPException(422, "A replacement assignee is required")
        row.status, row.assigned_user_id = "assigned", payload.assigned_user_id
    add_timeline(db, incident, "task_completed" if target in {"complete", "verify"} else "task_updated", f"Task {target}: {row.title}", user.username, payload.reason or payload.output_summary, source_id=row.id)
    _audit_commit(db, user, f"INCIDENT_TASK_{target.upper()}D", "IncidentTask", row, f"{target.title()} task for {incident.incident_number}")
    publish("incident_task_updated", incident, task_id=str(row.id), task_status=row.status)
    return row


for _action in ("start", "complete", "verify", "block", "reassign"):
    def _make(action):
        @router.post(f"/{{incident_id}}/tasks/{{task_id}}/{action}", name=f"incident_task_{action}")
        def endpoint(incident_id: UUID, task_id: UUID, payload: TaskAction = TaskAction(), db: Session = Depends(get_db), user=Depends(operator)):
            return _task_action(db, user, incident_id, task_id, action, payload)
        return endpoint
    _make(_action)


@router.get("/{incident_id}/checklists")
def checklists(incident_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    row = _incident(db, user, incident_id)
    return {"items": db.query(IncidentChecklistItem).filter_by(incident_id=row.id).order_by(IncidentChecklistItem.created_at).all()}


@router.post("/{incident_id}/checklists/{item_id}/{action}")
def checklist_action(incident_id: UUID, item_id: UUID, action: str, payload: ChecklistAction, db: Session = Depends(get_db), user=Depends(operator)):
    incident = _incident(db, user, incident_id)
    row = db.query(IncidentChecklistItem).filter_by(id=item_id, incident_id=incident.id).first()
    if not row or action not in {"complete", "skip", "fail"}:
        raise HTTPException(404, "Checklist item or action not found")
    if action in {"skip", "fail"} and not payload.reason:
        raise HTTPException(422, "A reason is required")
    if action == "skip" and row.required and user.role not in {"admin"}:
        raise HTTPException(403, "Only administrators may skip a required checklist item")
    if action == "complete" and row.evidence_required and not payload.evidence_reference:
        raise HTTPException(409, "Evidence is required for this checklist item")
    row.status = {"complete": "completed", "skip": "skipped", "fail": "failed"}[action]
    row.completed_by, row.completed_at = user.username, datetime.now(timezone.utc)
    row.evidence_reference, row.notes = payload.evidence_reference, payload.notes or payload.reason
    add_timeline(db, incident, "checklist_updated", f"Checklist {action}: {row.text}", user.username, payload.reason)
    return _audit_commit(db, user, f"INCIDENT_CHECKLIST_{action.upper()}D", "IncidentChecklistItem", row, f"Checklist item {action}")


@router.get("/{incident_id}/timeline")
def incident_timeline(
    incident_id: UUID, entry_type: str | None = None, page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200), db: Session = Depends(get_db), user=Depends(reader),
):
    row = _incident(db, user, incident_id)
    query = db.query(IncidentTimelineEntry).filter_by(incident_id=row.id)
    if entry_type:
        query = query.filter_by(entry_type=entry_type)
    return _page(query, page, page_size, IncidentTimelineEntry.occurred_at.desc())


@router.get("/{incident_id}/sources")
def sources(incident_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    row = _incident(db, user, incident_id)
    return {"items": db.query(OperationalIncidentSource).filter_by(incident_id=row.id).all()}


@router.post("/{incident_id}/sources", status_code=201)
def add_source(incident_id: UUID, payload: SourceWrite, db: Session = Depends(get_db), user=Depends(operator)):
    incident = _incident(db, user, incident_id)
    duplicate = db.query(OperationalIncidentSource).filter_by(incident_id=incident.id, source_type=payload.source_type, source_entity_id=payload.source_entity_id).first()
    if duplicate:
        return duplicate
    row = OperationalIncidentSource(incident_id=incident.id, **payload.model_dump(), linked_by=user.username)
    db.add(row)
    db.flush()
    add_timeline(db, incident, "source_linked", f"Source linked: {row.source_type}", user.username, source_id=row.id)
    return _audit_commit(db, user, "INCIDENT_SOURCE_LINKED", "OperationalIncidentSource", row, f"Linked source to {incident.incident_number}")


@router.get("/{incident_id}/evidence")
def evidence(incident_id: UUID, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), db: Session = Depends(get_db), user=Depends(reader)):
    incident = _incident(db, user, incident_id)
    query = db.query(IncidentEvidence).filter_by(incident_id=incident.id)
    if user.role == "viewer":
        query = query.filter(IncidentEvidence.sensitivity.in_(("normal", "internal")))
    return _page(query, page, page_size, IncidentEvidence.captured_at.desc())


@router.post("/{incident_id}/evidence", status_code=201)
def add_evidence(incident_id: UUID, payload: EvidenceWrite, db: Session = Depends(get_db), user=Depends(operator)):
    incident = _incident(db, user, incident_id)
    values = payload.model_dump()
    values["evidence_metadata"] = json.dumps(values.pop("metadata"), separators=(",", ":"))
    row = IncidentEvidence(incident_id=incident.id, **values, captured_by=user.username)
    db.add(row)
    db.flush()
    add_timeline(db, incident, "evidence_added", f"Evidence added: {row.title}", user.username, source_id=row.id)
    return _audit_commit(db, user, "INCIDENT_EVIDENCE_ADDED", "IncidentEvidence", row, f"Added {row.evidence_type} evidence")


@router.get("/{incident_id}/evidence/{evidence_id}")
def get_evidence(incident_id: UUID, evidence_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    incident = _incident(db, user, incident_id)
    row = db.query(IncidentEvidence).filter_by(id=evidence_id, incident_id=incident.id).first()
    if not row:
        raise HTTPException(404, "Evidence not found")
    if row.sensitivity in {"restricted", "highly_restricted"} and user.role not in {"admin", "technician"}:
        raise HTTPException(403, "Evidence sensitivity requires elevated access")
    return row


@router.get("/{incident_id}/decisions")
def decisions(incident_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    incident = _incident(db, user, incident_id)
    return {"items": db.query(IncidentDecision).filter_by(incident_id=incident.id).order_by(IncidentDecision.created_at).all()}


@router.post("/{incident_id}/decisions", status_code=201)
def create_decision(incident_id: UUID, payload: DecisionWrite, db: Session = Depends(get_db), user=Depends(operator)):
    incident = _incident(db, user, incident_id)
    row = IncidentDecision(incident_id=incident.id, **payload.model_dump(exclude={"options"}), options=json.dumps(payload.options, separators=(",", ":")))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.post("/{incident_id}/decisions/{decision_id}/decide")
def decide(incident_id: UUID, decision_id: UUID, payload: DecideWrite, db: Session = Depends(get_db), user=Depends(operator)):
    incident = _incident(db, user, incident_id)
    row = db.query(IncidentDecision).filter_by(id=decision_id, incident_id=incident.id).first()
    if not row or row.decided_at:
        raise HTTPException(409, "Decision is unavailable or already resolved")
    if payload.decision not in json.loads(row.options):
        raise HTTPException(422, "Decision is not one of the approved options")
    if row.approval_required and user.role not in {"admin"}:
        raise HTTPException(403, "This decision requires administrator approval")
    row.decision, row.rationale, row.decided_by, row.decided_at = payload.decision, payload.rationale, user.username, datetime.now(timezone.utc)
    add_timeline(db, incident, "decision_made", f"Decision: {row.title}", user.username, payload.rationale, source_id=row.id)
    return _audit_commit(db, user, "INCIDENT_DECISION_MADE", "IncidentDecision", row, f"Selected approved option {payload.decision}")


@router.get("/{incident_id}/communications")
def communications(incident_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    incident = _incident(db, user, incident_id)
    return {"items": db.query(IncidentCommunication).filter_by(incident_id=incident.id).order_by(IncidentCommunication.created_at.desc()).all()}


@router.post("/{incident_id}/notify-email")
def notify_incident_email(incident_id: UUID, payload: IncidentEmailWrite, db: Session = Depends(get_db), user=Depends(operator)):
    """Send an operator-requested status update to the configured notification recipient."""
    incident = _incident(db, user, incident_id)
    from app.services.incident_notification_service import notify_incident
    summary = payload.summary or "An operator requested an incident status update."
    if not notify_incident(db, incident, "status update", summary):
        raise HTTPException(503, "Email notifications are disabled, incomplete, or temporarily unavailable")
    add_timeline(db, incident, "communication_sent", "Incident email notification sent", user.username, summary)
    create_audit_log(db, user.username, "INCIDENT_EMAIL_SENT", "OperationalIncident", str(incident.id), f"Sent configured-recipient update for {incident.incident_number}")
    db.commit()
    return {"status": "sent", "message": "Email notification sent to the configured recipient."}


def _communication_preview(db, user, incident_id, payload):
    incident = _incident(db, user, incident_id)
    template = _scope(db.query(IncidentCommunicationTemplate).filter_by(id=payload.template_id, enabled=True), IncidentCommunicationTemplate.property_id, db, user).first()
    if not template or template.property_id != incident.property_id:
        raise HTTPException(404, "Approved communication template not found")
    try:
        rendered = render_template(template, incident, payload.extra_fields)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return incident, template, rendered


@router.post("/{incident_id}/communications/preview")
def communication_preview(incident_id: UUID, payload: CommunicationWrite, db: Session = Depends(get_db), user=Depends(operator)):
    _, template, rendered = _communication_preview(db, user, incident_id, payload)
    return {**rendered, "communication_type": template.communication_type, "audience_type": template.audience_type, "external_delivery_configured": False}


@router.post("/{incident_id}/communications/send", status_code=201)
def send_communication(incident_id: UUID, payload: CommunicationWrite, db: Session = Depends(get_db), user=Depends(operator)):
    incident, template, rendered = _communication_preview(db, user, incident_id, payload)
    row = IncidentCommunication(
        incident_id=incident.id, communication_type=template.communication_type,
        audience_type=template.audience_type, audience_reference=payload.audience_reference,
        subject=rendered["subject"], message_template_key=template.code,
        rendered_message=rendered["message"], status="sent", severity=payload.severity,
        sent_by=user.username, sent_at=datetime.now(timezone.utc),
        delivery_summary="Delivered through HIOP in-app notification only.",
    )
    incident.last_communication_at = row.sent_at
    db.add(row)
    db.flush()
    add_timeline(db, incident, "communication_sent", f"Communication sent: {row.subject}", user.username, source_id=row.id)
    _audit_commit(db, user, "INCIDENT_COMMUNICATION_SENT", "IncidentCommunication", row, f"Sent {row.communication_type} in-app update")
    publish("incident_communication_sent", incident, communication_id=str(row.id))
    return row


@router.get("/{incident_id}/impact")
def get_impact(incident_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    incident = _incident(db, user, incident_id)
    return db.query(IncidentImpactAssessment).filter_by(incident_id=incident.id).first()


@router.put("/{incident_id}/impact")
def update_impact(incident_id: UUID, payload: ImpactWrite, db: Session = Depends(get_db), user=Depends(operator)):
    incident = _incident(db, user, incident_id)
    if payload.life_safety_impact_level not in {"none", "unknown"} and not payload.life_safety_confirmed:
        raise HTTPException(422, "Elevated life-safety impact requires explicit confirmation")
    values = payload.model_dump(exclude={"life_safety_confirmed"})
    values["affected_scope"] = json.dumps(values["affected_scope"], separators=(",", ":"))
    row = db.query(IncidentImpactAssessment).filter_by(incident_id=incident.id).first()
    if row:
        for key, value in values.items():
            setattr(row, key, value)
        row.assessed_by, row.assessed_at = user.username, datetime.now(timezone.utc)
    else:
        row = IncidentImpactAssessment(incident_id=incident.id, **values, assessed_by=user.username)
        db.add(row)
    for field in ("guest_impact_level", "revenue_impact_level", "security_impact_level", "life_safety_impact_level"):
        setattr(incident, field, getattr(payload, field))
    db.flush()
    add_timeline(db, incident, "impact_assessed", "Hospitality impact assessment updated", user.username)
    return _audit_commit(db, user, "INCIDENT_IMPACT_UPDATED", "IncidentImpactAssessment", row, f"Updated impact for {incident.incident_number}")


@router.get("/{incident_id}/recommendations")
def recommendations(incident_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    incident = _incident(db, user, incident_id)
    return {"items": db.query(IncidentRemediationRecommendation).filter_by(incident_id=incident.id).order_by(IncidentRemediationRecommendation.created_at.desc()).all()}


@router.post("/{incident_id}/recommendations/generate")
def generate(incident_id: UUID, db: Session = Depends(get_db), user=Depends(operator)):
    incident = _incident(db, user, incident_id)
    rows = generate_recommendations(db, incident)
    db.commit()
    return {"created": len(rows), "human_approval_required": True}


@router.post("/{incident_id}/recommendations/{recommendation_id}/{action}")
def recommendation_action(incident_id: UUID, recommendation_id: UUID, action: str, payload: ReasonWrite, db: Session = Depends(get_db), user=Depends(operator)):
    incident = _incident(db, user, incident_id)
    row = db.query(IncidentRemediationRecommendation).filter_by(id=recommendation_id, incident_id=incident.id).first()
    if not row or row.status != "proposed" or action not in {"approve", "reject", "expire"}:
        raise HTTPException(409, "Recommendation is unavailable for this action")
    if action == "approve" and (row.risk_level in {"high", "critical"} or row.approval_required) and user.role not in {"admin"}:
        raise HTTPException(403, "High-risk remediation approval requires an administrator")
    if action in {"reject", "expire"} and not payload.reason:
        raise HTTPException(422, "A reason is required")
    row.status = {"approve": "approved", "reject": "rejected", "expire": "expired"}[action]
    row.reviewed_by, row.reviewed_at = user.username, datetime.now(timezone.utc)
    add_timeline(db, incident, "action_executed" if action == "approve" else "decision_made", f"Recommendation {action}d: {row.title}", user.username, payload.reason)
    return _audit_commit(db, user, f"INCIDENT_REMEDIATION_{action.upper()}D", "IncidentRemediationRecommendation", row, f"{action.title()}d deterministic recommendation")


@router.get("/{incident_id}/recovery-readiness")
def recovery_status(incident_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    return recovery_readiness(db, _incident(db, user, incident_id))


@router.post("/{incident_id}/verify-recovery")
def verify_recovery(incident_id: UUID, payload: ReasonWrite, db: Session = Depends(get_db), user=Depends(operator)):
    incident = _incident(db, user, incident_id)
    status = recovery_readiness(db, incident)
    if not status["ready"]:
        raise HTTPException(409, {"message": "Recovery criteria are incomplete", **status})
    if incident.severity in {"high", "critical"} and user.role not in {"admin"} and str(user.id) != incident.incident_commander_id:
        raise HTTPException(403, "Recovery for high/critical incidents requires commander or administrator confirmation")
    incident.recovery_verified = True
    add_timeline(db, incident, "verification_completed", "Recovery verification completed", user.username, payload.reason)
    return _audit_commit(db, user, "INCIDENT_RECOVERY_VERIFIED", "OperationalIncident", incident, f"Verified recovery for {incident.incident_number}")


@router.get("/{incident_id}/cause-assessment")
def cause_assessment(incident_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    incident = _incident(db, user, incident_id)
    return db.query(IncidentCauseAssessment).filter_by(incident_id=incident.id).first()


@router.put("/{incident_id}/cause-assessment")
def update_cause(incident_id: UUID, payload: CauseWrite, db: Session = Depends(get_db), user=Depends(operator)):
    incident = _incident(db, user, incident_id)
    if payload.cause_status == "confirmed" and payload.confidence_score < 90:
        raise HTTPException(422, "Confirmed cause requires at least 90 percent confidence and evidence")
    if payload.cause_status == "confirmed" and not payload.evidence:
        raise HTTPException(422, "Confirmed cause requires evidence")
    values = payload.model_dump()
    values["evidence"] = json.dumps(values["evidence"], separators=(",", ":"))
    row = db.query(IncidentCauseAssessment).filter_by(incident_id=incident.id).first()
    if row:
        for key, value in values.items():
            setattr(row, key, value)
    else:
        row = IncidentCauseAssessment(incident_id=incident.id, **values)
        db.add(row)
    row.assessed_by, row.assessed_at = user.username, datetime.now(timezone.utc)
    db.flush()
    return _audit_commit(db, user, "INCIDENT_CAUSE_UPDATED", "IncidentCauseAssessment", row, f"Cause marked {row.cause_status}")


@router.get("/{incident_id}/post-incident-review")
def get_review(incident_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    incident = _incident(db, user, incident_id)
    return db.query(PostIncidentReview).filter_by(incident_id=incident.id).first()


@router.post("/{incident_id}/post-incident-review", status_code=201)
def create_review(incident_id: UUID, payload: ReviewWrite, db: Session = Depends(get_db), user=Depends(operator)):
    incident = _incident(db, user, incident_id)
    if db.query(PostIncidentReview).filter_by(incident_id=incident.id).first():
        raise HTTPException(409, "Post-incident review already exists")
    row = PostIncidentReview(incident_id=incident.id, status="scheduled" if payload.scheduled_at else "required", facilitator_id=payload.facilitator_id, scheduled_at=payload.scheduled_at, review_content=json.dumps(payload.review_content, separators=(",", ":")))
    db.add(row)
    db.flush()
    return _audit_commit(db, user, "POST_INCIDENT_REVIEW_CREATED", "PostIncidentReview", row, f"Created review for {incident.incident_number}")


@router.patch("/{incident_id}/post-incident-review")
def update_review(incident_id: UUID, payload: ReviewWrite, db: Session = Depends(get_db), user=Depends(operator)):
    incident = _incident(db, user, incident_id)
    row = db.query(PostIncidentReview).filter_by(incident_id=incident.id).first()
    if not row or row.status in {"approved", "archived"}:
        raise HTTPException(409, "Post-incident review is unavailable or immutable")
    row.facilitator_id, row.scheduled_at = payload.facilitator_id, payload.scheduled_at
    row.review_content = json.dumps(payload.review_content, separators=(",", ":"))
    row.status = "in_progress"
    db.commit()
    db.refresh(row)
    return row


@router.post("/{incident_id}/post-incident-review/{action}")
def review_action(incident_id: UUID, action: str, db: Session = Depends(get_db), user=Depends(admin)):
    incident = _incident(db, user, incident_id)
    row = db.query(PostIncidentReview).filter_by(incident_id=incident.id).first()
    if not row or action not in {"complete", "approve"}:
        raise HTTPException(404, "Review or action not found")
    if action == "complete" and row.status not in {"scheduled", "in_progress", "required"}:
        raise HTTPException(409, "Review cannot be completed")
    if action == "approve" and row.status != "completed":
        raise HTTPException(409, "Only completed reviews can be approved")
    now = datetime.now(timezone.utc)
    if action == "complete":
        row.status, row.completed_at = "completed", now
    else:
        row.status, row.approved_by, row.approved_at = "approved", user.username, now
    return _audit_commit(db, user, f"POST_INCIDENT_REVIEW_{action.upper()}D", "PostIncidentReview", row, f"{action.title()}d review")


@router.get("/{incident_id}/follow-up-actions")
def follow_ups(incident_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    incident = _incident(db, user, incident_id)
    return {"items": db.query(IncidentFollowUpAction).filter_by(incident_id=incident.id).order_by(IncidentFollowUpAction.created_at).all()}


@router.post("/{incident_id}/follow-up-actions", status_code=201)
def create_follow_up(incident_id: UUID, payload: FollowUpWrite, db: Session = Depends(get_db), user=Depends(operator)):
    incident = _incident(db, user, incident_id)
    review = db.query(PostIncidentReview).filter_by(incident_id=incident.id).first()
    row = IncidentFollowUpAction(incident_id=incident.id, post_incident_review_id=review.id if review else None, **payload.model_dump())
    db.add(row)
    db.flush()
    add_timeline(db, incident, "follow_up_created", f"Follow-up created: {row.title}", user.username, source_id=row.id)
    _audit_commit(db, user, "INCIDENT_FOLLOW_UP_CREATED", "IncidentFollowUpAction", row, f"Created follow-up for {incident.incident_number}")
    publish("incident_follow_up_created", incident, follow_up_id=str(row.id))
    return row


@router.patch("/{incident_id}/follow-up-actions/{action_id}")
def update_follow_up(incident_id: UUID, action_id: UUID, payload: FollowUpWrite, db: Session = Depends(get_db), user=Depends(operator)):
    incident = _incident(db, user, incident_id)
    row = db.query(IncidentFollowUpAction).filter_by(id=action_id, incident_id=incident.id).first()
    if not row:
        raise HTTPException(404, "Follow-up action not found")
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


@router.get("/{incident_id}/escalations")
def incident_escalations(incident_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    incident = _incident(db, user, incident_id)
    return {"items": db.query(IncidentEscalation).filter_by(incident_id=incident.id).order_by(IncidentEscalation.escalated_at.desc()).all()}


@router.post("/{incident_id}/evaluate-escalations")
def evaluate_escalations(incident_id: UUID, db: Session = Depends(get_db), user=Depends(admin)):
    incident = _incident(db, user, incident_id)
    result = evaluate_incident(db, incident)
    create_audit_log(db, user.username, "INCIDENT_ESCALATION_EVALUATED", "OperationalIncident", str(incident.id), f"Created {result['created']} escalations")
    db.commit()
    return result


@router.get("/{incident_id}/evidence-bundle")
def evidence_bundle(incident_id: UUID, db: Session = Depends(get_db), user=Depends(operator)):
    incident = _incident(db, user, incident_id)
    def rows(model):
        return db.query(model).filter_by(incident_id=incident.id).limit(1000).all()
    bundle = {
        "incident": incident, "sources": rows(OperationalIncidentSource),
        "participants": rows(IncidentParticipant), "tasks": rows(IncidentTask),
        "checklist": rows(IncidentChecklistItem), "timeline": rows(IncidentTimelineEntry),
        "evidence": [item for item in rows(IncidentEvidence) if item.sensitivity != "highly_restricted" or user.role in {"admin"}],
        "decisions": rows(IncidentDecision), "communications": rows(IncidentCommunication),
        "recommendations": rows(IncidentRemediationRecommendation),
        "cause_assessment": db.query(IncidentCauseAssessment).filter_by(incident_id=incident.id).first(),
        "post_incident_review": db.query(PostIncidentReview).filter_by(incident_id=incident.id).first(),
        "follow_up_actions": rows(IncidentFollowUpAction),
        "redacted": True, "excluded": ["credentials", "secrets", "raw configuration", "private keys"],
    }
    create_audit_log(db, user.username, "INCIDENT_EVIDENCE_EXPORTED", "OperationalIncident", str(incident.id), "Exported redacted JSON evidence bundle")
    db.commit()
    return bundle
