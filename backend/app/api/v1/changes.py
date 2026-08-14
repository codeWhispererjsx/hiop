from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.core.tenant import organization_context
from app.models.asset_intelligence import ManagedAsset
from app.models.asset_management import Vendor
from app.models.change_management import ChangeComment, ChangeRelationship, ChangeRequest, ChangeTimelineEvent, ChangeType, MaintenanceWindow
from app.models.device import Device
from app.models.hierarchy import Building, Floor, Property, Room
from app.models.hospitality_operations import HospitalityTechnologyService
from app.models.incidents import IncidentImpactAssessment, OperationalIncident
from app.models.problem_management import Problem
from app.models.user import User
from app.services.audit_service import create_audit_log

router = APIRouter(prefix="/changes", tags=["Change Management"])
reader = require_roles(["platformadmin", "admin", "technician", "viewer"])
operator = require_roles(["admin"])
note_writer = require_roles(["admin", "technician"])
STATUSES = {"draft", "submitted", "under_review", "approved", "scheduled", "in_progress", "completed", "failed", "rolled_back", "cancelled", "closed"}
TYPES = {"standard", "normal", "emergency"}; LEVELS = {"low", "medium", "high", "critical"}; OUTCOMES = {"successful", "failed", "rolled_back", "cancelled"}


class ChangeWrite(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    description: str = Field("", max_length=20000)
    change_type: str = "normal"; priority: str = "medium"; risk: str = "medium"
    risk_explanation: str = Field(min_length=3, max_length=10000)
    reason: str = Field(min_length=3, max_length=10000)
    implementation_plan: str = Field(min_length=3, max_length=20000)
    validation_plan: str = Field(min_length=3, max_length=20000)
    rollback_plan: str = Field("", max_length=20000)
    owner_id: str | None = None; planned_start: datetime | None = None; planned_end: datetime | None = None
    asset_id: UUID | None = None; device_id: UUID | None = None; service_id: UUID | None = None; problem_id: UUID | None = None
    incident_id: UUID | None = None; vendor_id: UUID | None = None; location_type: str | None = None; location_id: UUID | None = None
    @field_validator("change_type")
    @classmethod
    def valid_type(cls, value):
        if value not in TYPES: raise ValueError("Unsupported change type")
        return value
    @field_validator("priority", "risk")
    @classmethod
    def valid_level(cls, value):
        if value not in LEVELS: raise ValueError("Unsupported level")
        return value


class ChangePatch(BaseModel):
    title: str | None = Field(None, min_length=3, max_length=240); description: str | None = Field(None, max_length=20000)
    priority: str | None = None; risk: str | None = None; risk_explanation: str | None = Field(None, max_length=10000)
    reason: str | None = Field(None, max_length=10000); implementation_plan: str | None = Field(None, max_length=20000)
    validation_plan: str | None = Field(None, max_length=20000); rollback_plan: str | None = Field(None, max_length=20000); owner_id: str | None = None


class ActionWrite(BaseModel):
    notes: str | None = Field(None, max_length=10000); planned_start: datetime | None = None; planned_end: datetime | None = None
    validation: str | None = Field(None, max_length=20000); outcome: str | None = None; closure_notes: str | None = Field(None, max_length=20000)
    rollback_reason: str | None = Field(None, max_length=10000); rollback_notes: str | None = Field(None, max_length=20000)


class LinkWrite(BaseModel):
    target_type: Literal["asset", "device", "service", "problem", "incident", "vendor", "location"]
    target_id: UUID


class NoteWrite(BaseModel): note: str = Field(min_length=2, max_length=10000)


def get_change(db, change_id, org):
    row = db.query(ChangeRequest).filter_by(id=change_id, organization_id=org).first()
    if not row: raise HTTPException(404, "Change not found")
    return row


TARGETS = {"asset": ManagedAsset, "device": Device, "service": HospitalityTechnologyService, "problem": Problem, "incident": OperationalIncident, "vendor": Vendor}
def validate_target(db, kind, target_id, org):
    if kind == "location":
        found = any(db.query(model).filter_by(id=target_id, organization_id=org).first() for model in (Building, Floor, Room))
    else:
        model = TARGETS[kind]; query = db.query(model).filter(model.id == target_id)
        if hasattr(model, "organization_id"): query = query.filter(model.organization_id == org)
        elif model is Device: query = query.join(Property, Device.property_id == Property.id).filter(Property.organization_id == org)
        found = query.first()
    if not found: raise HTTPException(422, f"{kind.title()} does not belong to this organization")
    return found


def add_event(db, row, actor, kind, summary):
    db.add(ChangeTimelineEvent(change_request_id=row.id, organization_id=row.organization_id, event_type=kind, summary=summary, actor_id=actor.id, actor_name=actor.username))
    create_audit_log(db, actor.username, f"CHANGE_{kind.upper()}", "Change", str(row.id), f"Organization {row.organization_id}: {summary}")


def add_link(db, row, kind, target_id, actor):
    validate_target(db, kind, target_id, row.organization_id)
    existing = db.query(ChangeRelationship).filter_by(change_request_id=row.id, target_type=kind, target_id=target_id, relationship_type="affected").first()
    if not existing:
        db.add(ChangeRelationship(change_request_id=row.id, target_type=kind, target_id=target_id, relationship_type="affected", created_by=actor.id))
        add_event(db, row, actor, f"{kind}_linked", f"Linked {kind} {target_id}")


def relationships(db, row, kind): return db.query(ChangeRelationship).filter_by(change_request_id=row.id, target_type=kind).all()


def display(db, row, detail=False):
    rels = {kind: relationships(db, row, kind) for kind in [*TARGETS, "location"]}
    incidents = [validate_target(db, "incident", rel.target_id, row.organization_id) for rel in rels["incident"]]
    assets = [validate_target(db, "asset", rel.target_id, row.organization_id) for rel in rels["asset"]]
    services = [validate_target(db, "service", rel.target_id, row.organization_id) for rel in rels["service"]]
    problems = [validate_target(db, "problem", rel.target_id, row.organization_id) for rel in rels["problem"]]
    vendors = [validate_target(db, "vendor", rel.target_id, row.organization_id) for rel in rels["vendor"]]
    impacts = db.query(IncidentImpactAssessment).filter(IncidentImpactAssessment.incident_id.in_([x.id for x in incidents])).all() if incidents else []
    conflicts = []
    if row.scheduled_start and row.scheduled_end:
        conflicts = db.query(ChangeRequest).filter(ChangeRequest.organization_id == row.organization_id, ChangeRequest.id != row.id, ChangeRequest.status.in_(["scheduled", "in_progress"]), ChangeRequest.scheduled_start < row.scheduled_end, ChangeRequest.scheduled_end > row.scheduled_start).all()
    window = None
    if row.scheduled_start and row.scheduled_end:
        window = db.query(MaintenanceWindow).join(Property, MaintenanceWindow.property_id == Property.id).filter(Property.organization_id == row.organization_id, MaintenanceWindow.start_at <= row.scheduled_start, MaintenanceWindow.end_at >= row.scheduled_end, MaintenanceWindow.status == "approved").first()
    result = {"id": row.id, "change_id": row.change_id, "title": row.title, "description": row.description, "type": row.change_type, "status": row.status, "priority": row.priority, "risk": row.risk_level, "risk_explanation": row.risk_explanation, "reason": row.business_justification, "implementation_plan": row.implementation_plan, "validation_plan": row.validation_plan, "rollback_plan": row.backout_plan, "validation_outcome": row.test_plan, "requested_by": row.requested_by, "owner_id": row.owner_id, "approver_id": row.approver_id, "planned_start": row.scheduled_start, "planned_end": row.scheduled_end, "actual_start": row.actual_start, "actual_end": row.actual_end, "outcome": row.outcome, "closure_notes": row.closure_notes, "created_at": row.created_at, "updated_at": row.updated_at, "related_counts": {k: len(v) for k, v in rels.items()}, "conflicts": [{"id": x.id, "change_id": x.change_id, "title": x.title} for x in conflicts], "maintenance_window": {"id": window.id, "name": window.name} if window else None, "impact": {"confirmed_affected": 0, "potentially_affected": sum(x.affected_guest_rooms or 0 for x in impacts), "source": "existing_incident_impact"} if impacts else None}
    if detail:
        result.update({"assets": [{"id": x.id, "asset_number": x.asset_number, "name": x.name} for x in assets], "services": [{"id": x.id, "name": x.name} for x in services], "problems": [{"id": x.id, "problem_number": x.problem_number, "title": x.title} for x in problems], "incidents": [{"id": x.id, "incident_number": x.incident_number, "title": x.title} for x in incidents], "vendors": [{"id": x.id, "name": x.legal_name} for x in vendors], "timeline": [{"id": x.id, "type": x.event_type, "summary": x.summary, "author": x.actor_name, "timestamp": x.created_at} for x in db.query(ChangeTimelineEvent).filter_by(change_request_id=row.id, organization_id=row.organization_id).order_by(ChangeTimelineEvent.created_at).all()]})
    return result


@router.get("/summary")
def summary(db: Session = Depends(get_db), _=Depends(reader), org=Depends(organization_context)):
    rows = db.query(ChangeRequest).filter_by(organization_id=org).all(); now = datetime.now(timezone.utc)
    return {"total": len(rows), **{s: sum(x.status == s for x in rows) for s in STATUSES}, "high_risk": sum(x.risk_level in {"high", "critical"} and x.status not in {"closed", "cancelled"} for x in rows), "emergency": sum(x.change_type == "emergency" for x in rows), "upcoming": sum(bool(x.scheduled_start and x.scheduled_start >= now and x.status == "scheduled") for x in rows)}


@router.get("/calendar")
def calendar(start: datetime | None = None, end: datetime | None = None, db: Session = Depends(get_db), _=Depends(reader), org=Depends(organization_context)):
    q = db.query(ChangeRequest).filter(ChangeRequest.organization_id == org, ChangeRequest.scheduled_start.isnot(None))
    if start: q = q.filter(ChangeRequest.scheduled_end >= start)
    if end: q = q.filter(ChangeRequest.scheduled_start <= end)
    return [display(db, row) for row in q.order_by(ChangeRequest.scheduled_start).all()]


@router.get("")
def list_changes(search: str | None = None, status: str | None = None, change_type: str | None = None, priority: str | None = None, risk: str | None = None, owner_id: str | None = None, start: datetime | None = None, end: datetime | None = None, db: Session = Depends(get_db), _=Depends(reader), org=Depends(organization_context)):
    q = db.query(ChangeRequest).filter_by(organization_id=org)
    if search:
        term = f"%{search}%"; related = db.query(ChangeRelationship.change_request_id).filter(ChangeRelationship.target_id.in_(db.query(ManagedAsset.id).filter(or_(ManagedAsset.name.ilike(term), ManagedAsset.asset_number.ilike(term), ManagedAsset.asset_tag.ilike(term)))))
        q = q.filter(or_(ChangeRequest.change_id.ilike(term), ChangeRequest.title.ilike(term), ChangeRequest.description.ilike(term), ChangeRequest.business_justification.ilike(term), ChangeRequest.id.in_(related)))
    if status: q = q.filter_by(status=status)
    if change_type: q = q.filter_by(change_type=change_type)
    if priority: q = q.filter_by(priority=priority)
    if risk: q = q.filter_by(risk_level=risk)
    if owner_id: q = q.filter_by(owner_id=owner_id)
    if start: q = q.filter(ChangeRequest.scheduled_end >= start)
    if end: q = q.filter(ChangeRequest.scheduled_start <= end)
    return [display(db, row) for row in q.order_by(ChangeRequest.created_at.desc()).all()]


@router.get("/links/{target_type}/{target_id}")
def linked_changes(target_type: Literal["asset", "service", "problem", "incident", "vendor", "device"], target_id: UUID, db: Session = Depends(get_db), _=Depends(reader), org=Depends(organization_context)):
    validate_target(db, target_type, target_id, org)
    ids = db.query(ChangeRelationship.change_request_id).filter_by(target_type=target_type, target_id=target_id)
    return [display(db, row) for row in db.query(ChangeRequest).filter(ChangeRequest.organization_id == org, ChangeRequest.id.in_(ids)).order_by(ChangeRequest.created_at.desc()).all()]


@router.post("", status_code=201)
def create_change(payload: ChangeWrite, db: Session = Depends(get_db), actor=Depends(operator), org=Depends(organization_context)):
    if payload.risk in {"high", "critical"} and not payload.rollback_plan.strip(): raise HTTPException(422, "High and critical risk changes require a rollback plan")
    if payload.planned_start and payload.planned_end and payload.planned_end <= payload.planned_start: raise HTTPException(422, "Planned end must follow planned start")
    if payload.owner_id and not db.query(User).filter_by(id=payload.owner_id, organization_id=org).first(): raise HTTPException(422, "Owner does not belong to this organization")
    property_row = db.query(Property).filter_by(organization_id=org, is_active=True).first()
    change_type = db.query(ChangeType).filter(ChangeType.code.in_([payload.change_type, {"standard": "standard_change", "normal": "normal_change", "emergency": "emergency_change"}[payload.change_type]])).first() or db.query(ChangeType).first()
    if not change_type: raise HTTPException(500, "Change type configuration unavailable")
    number = db.execute(text("SELECT nextval('v4g_change_number_seq')")).scalar_one()
    row = ChangeRequest(change_id=f"CHG-{number:05d}", organization_id=org, property_id=property_row.id if property_row else None, type_id=change_type.id, change_type=payload.change_type, title=payload.title, description=payload.description, business_justification=payload.reason, technical_justification=payload.reason, requested_by=actor.id, owner_id=payload.owner_id, risk_level=payload.risk, risk_explanation=payload.risk_explanation, impact_level=payload.risk, priority=payload.priority, backout_plan=payload.rollback_plan, validation_plan=payload.validation_plan, test_plan="", communication_plan="", implementation_plan=payload.implementation_plan, scheduled_start=payload.planned_start, scheduled_end=payload.planned_end, status="draft")
    db.add(row); db.flush()
    for kind, target_id in (("asset", payload.asset_id), ("device", payload.device_id), ("service", payload.service_id), ("problem", payload.problem_id), ("incident", payload.incident_id), ("vendor", payload.vendor_id), ("location", payload.location_id)):
        if target_id: add_link(db, row, kind, target_id, actor)
    add_event(db, row, actor, "created", f"Created {row.change_id}"); db.commit(); db.refresh(row); return display(db, row, True)


@router.get("/{change_id}")
def detail(change_id: UUID, db: Session = Depends(get_db), _=Depends(reader), org=Depends(organization_context)): return display(db, get_change(db, change_id, org), True)


@router.patch("/{change_id}")
def update(change_id: UUID, payload: ChangePatch, db: Session = Depends(get_db), actor=Depends(operator), org=Depends(organization_context)):
    row = get_change(db, change_id, org)
    if row.status not in {"draft", "submitted", "under_review"}: raise HTTPException(422, "Planning fields cannot be edited after approval")
    changes = payload.model_dump(exclude_unset=True); mapping = {"risk": "risk_level", "reason": "business_justification", "rollback_plan": "backout_plan"}
    prospective_risk = changes.get("risk", row.risk_level); prospective_rollback = changes.get("rollback_plan", row.backout_plan)
    if prospective_risk in {"high", "critical"} and not prospective_rollback: raise HTTPException(422, "High and critical risk changes require a rollback plan")
    for key, value in changes.items(): setattr(row, mapping.get(key, key), value)
    add_event(db, row, actor, "updated", "Planning record updated"); db.commit(); return display(db, row, True)


@router.post("/{change_id}/actions/{action}")
def action(change_id: UUID, action: str, payload: ActionWrite, db: Session = Depends(get_db), actor=Depends(operator), org=Depends(organization_context)):
    row = get_change(db, change_id, org); now = datetime.now(timezone.utc)
    transitions = {"submit": ("draft", "submitted"), "review": ("submitted", "under_review"), "approve": ("under_review", "approved"), "schedule": ("approved", "scheduled"), "start": ("scheduled", "in_progress"), "complete": ("in_progress", "completed"), "fail": ("in_progress", "failed"), "rollback": ("in_progress", "rolled_back"), "cancel": (("draft", "submitted", "under_review", "approved", "scheduled"), "cancelled"), "close": (("completed", "failed", "rolled_back", "cancelled"), "closed")}
    if action not in transitions: raise HTTPException(404, "Unsupported action")
    source, target_status = transitions[action]; allowed_sources = {source} if isinstance(source, str) else set(source)
    if row.status not in allowed_sources: raise HTTPException(422, f"Cannot {action} a {row.status} change")
    if action == "approve":
        if row.risk_level in {"high", "critical"} and row.requested_by == actor.id: raise HTTPException(403, "Requester cannot self-approve a high or critical risk change")
        row.approver_id = actor.id; row.approved_at = now
    if action == "schedule":
        row.scheduled_start = payload.planned_start or row.scheduled_start; row.scheduled_end = payload.planned_end or row.scheduled_end
        if not row.scheduled_start or not row.scheduled_end or row.scheduled_end <= row.scheduled_start: raise HTTPException(422, "A valid planned start and end are required")
    if action == "start": row.actual_start = now; row.owner_id = row.owner_id or actor.id
    if action == "complete":
        if not payload.validation: raise HTTPException(422, "Validation outcome is required")
        row.test_plan = payload.validation; row.outcome = payload.outcome or "successful"; row.actual_end = now; row.implemented_at = now
        if row.outcome not in OUTCOMES: raise HTTPException(422, "Unsupported outcome")
    if action == "fail": row.outcome = "failed"; row.actual_end = now
    if action == "rollback":
        if not payload.rollback_reason: raise HTTPException(422, "Rollback reason is required")
        row.outcome = "rolled_back"; row.rollback_time = now; row.rollback_owner_id = actor.id; row.rollback_reason = payload.rollback_reason; row.rollback_notes = payload.rollback_notes; row.actual_end = now
    if action == "cancel": row.outcome = "cancelled"
    if action == "close":
        if not row.outcome or not payload.closure_notes: raise HTTPException(422, "Outcome and closure notes are required")
        row.closure_notes = payload.closure_notes; row.closed_by = actor.id; row.closed_at = now
    row.status = target_status
    if action == "submit": row.submitted_at = now
    add_event(db, row, actor, action, payload.notes or f"Change {action}d"); db.commit(); db.refresh(row); return display(db, row, True)


@router.post("/{change_id}/notes", status_code=201)
def note(change_id: UUID, payload: NoteWrite, db: Session = Depends(get_db), actor=Depends(note_writer), org=Depends(organization_context)):
    row = get_change(db, change_id, org); db.add(ChangeComment(change_request_id=row.id, user_id=actor.id, body=payload.note, internal=True)); add_event(db, row, actor, "note", payload.note); db.commit(); return display(db, row, True)


@router.post("/{change_id}/relationships", status_code=201)
def link(change_id: UUID, payload: LinkWrite, db: Session = Depends(get_db), actor=Depends(operator), org=Depends(organization_context)):
    row = get_change(db, change_id, org); add_link(db, row, payload.target_type, payload.target_id, actor); db.commit(); return display(db, row, True)
