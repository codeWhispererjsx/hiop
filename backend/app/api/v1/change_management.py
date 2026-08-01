import csv
import io
import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from openpyxl import Workbook
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.models.audit_log import AuditLog
from app.models.change_management import (
    CABAgenda, CABAttendance, CABDecision, CABMeeting, CABMember, CABVote,
    ChangeApproval, ChangeAttachment, ChangeCategory, ChangeComment,
    ChangeCommunication, ChangeExecution, ChangeRelationship, ChangeRequest,
    ChangeRevision, ChangeTask, ChangeType, ExecutionEvidence, ExecutionTask,
    MaintenanceApproval, MaintenanceConflict, MaintenanceWindow, Release,
    ReleaseArtifact, ReleaseDeployment, ReleasePackage, ReleaseVersion, RiskAssessment,
    RollbackExecution,
)
from app.models.change_management import ExecutionLog
from app.models.hierarchy import Property
from app.models.property_access import UserPropertyAccess
from app.services.audit_service import create_audit_log
from app.services.change_management_service import (
    CHANGE_TRANSITIONS, assess_risk, change_identifier, complete_execution_task,
    decide_cab, detect_window_conflicts, initiate_rollback, release_identifier,
    revision, start_execution, transition,
)
from app.websocket.connection_manager import manager

router = APIRouter(prefix="/changes", tags=["Enterprise Change Management"])
reader = require_roles(["admin", "superadmin", "technician", "viewer"])
contributor = require_roles(["admin", "superadmin", "technician"])
admin = require_roles(["admin", "superadmin"])


class ChangeWrite(BaseModel):
    property_id: UUID | None = None; department_id: UUID | None = None; technology_service_id: UUID | None = None
    type_id: UUID; category_id: UUID | None = None; title: str = Field(min_length=3, max_length=240); description: str = Field(min_length=3, max_length=50000)
    business_justification: str = Field(min_length=3, max_length=20000); technical_justification: str = Field(min_length=3, max_length=20000)
    requested_for: str | None = None; owner_id: str | None = None; impact_level: str = Field("medium", pattern=r"^(low|medium|high|critical)$"); priority: str = Field("normal", pattern=r"^(low|normal|high|urgent|emergency)$")
    backout_plan: str = Field(min_length=3, max_length=30000); validation_plan: str = Field(min_length=3, max_length=30000); test_plan: str = Field(min_length=3, max_length=30000); communication_plan: str = Field(min_length=3, max_length=30000); implementation_plan: str = Field(min_length=3, max_length=50000)
    scheduled_start: datetime | None = None; scheduled_end: datetime | None = None; maintenance_window_id: UUID | None = None

    @model_validator(mode="after")
    def valid_schedule(self):
        if bool(self.scheduled_start) != bool(self.scheduled_end): raise ValueError("both schedule boundaries are required")
        if self.scheduled_start and self.scheduled_end <= self.scheduled_start: raise ValueError("scheduled end must follow start")
        return self


class ChangePatch(BaseModel):
    title: str | None = Field(None, min_length=3, max_length=240); description: str | None = Field(None, min_length=3, max_length=50000); business_justification: str | None = Field(None, max_length=20000); technical_justification: str | None = Field(None, max_length=20000)
    owner_id: str | None = None; category_id: UUID | None = None; impact_level: str | None = Field(None, pattern=r"^(low|medium|high|critical)$"); priority: str | None = Field(None, pattern=r"^(low|normal|high|urgent|emergency)$")
    backout_plan: str | None = Field(None, max_length=30000); validation_plan: str | None = Field(None, max_length=30000); test_plan: str | None = Field(None, max_length=30000); communication_plan: str | None = Field(None, max_length=30000); implementation_plan: str | None = Field(None, max_length=50000)
    scheduled_start: datetime | None = None; scheduled_end: datetime | None = None; maintenance_window_id: UUID | None = None; change_summary: str = Field("RFC updated", max_length=1000)


class ActionWrite(BaseModel): comments: str | None = Field(None, max_length=5000)
class ApprovalWrite(BaseModel): decision: str = Field(pattern=r"^(approved|conditional_approved|rejected|deferred)$"); comments: str = Field(min_length=2, max_length=10000); conditions: str | None = Field(None, max_length=10000)
class TaskWrite(BaseModel): sequence_order: int = Field(ge=0, le=1000); title: str = Field(min_length=2, max_length=220); description: str | None = Field(None, max_length=20000); assigned_to: str | None = None; checkpoint: bool = False; evidence_required: bool = False; due_at: datetime | None = None
class CommentWrite(BaseModel): body: str = Field(min_length=1, max_length=10000); internal: bool = True
class AttachmentWrite(BaseModel):
    filename: str = Field(min_length=1, max_length=255); media_type: str = Field(max_length=120); size_bytes: int = Field(gt=0, le=25_000_000); storage_reference: str = Field(max_length=500); checksum_sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    @field_validator("storage_reference")
    @classmethod
    def safe_ref(cls, value):
        if value.startswith(("/", "\\")) or ".." in value.replace("\\", "/").split("/"): raise ValueError("storage reference must be relative and traversal-free")
        return value
class RiskWrite(BaseModel): factors: dict[str, int]; rationale: str = Field(min_length=3, max_length=20000)
class WindowWrite(BaseModel):
    calendar_id: UUID | None = None; property_id: UUID | None = None; name: str = Field(min_length=3, max_length=180); window_type: str = Field("standard", pattern=r"^(standard|corporate|recurring|emergency|blackout)$"); start_at: datetime; end_at: datetime; timezone: str = Field("UTC", max_length=64); recurrence_rule: str | None = Field(None, max_length=255); blackout: bool = False; emergency: bool = False
    @model_validator(mode="after")
    def boundaries(self):
        if self.end_at <= self.start_at: raise ValueError("window end must follow start")
        if (self.end_at - self.start_at).days > 31: raise ValueError("maintenance window exceeds 31 days")
        return self
class MeetingWrite(BaseModel): property_id: UUID | None = None; title: str = Field(min_length=3, max_length=200); meeting_type: str = Field("regular", pattern=r"^(regular|emergency|virtual)$"); scheduled_start: datetime; scheduled_end: datetime; timezone: str = Field("UTC", max_length=64); quorum_required: int = Field(2, ge=1, le=100)
class VoteWrite(BaseModel): vote: str = Field(pattern=r"^(approve|conditional_approve|reject|defer)$"); conditions: str | None = Field(None, max_length=10000); comments: str | None = Field(None, max_length=10000)
class DecisionWrite(BaseModel): decision: str = Field(pattern=r"^(approved|conditional_approved|rejected|deferred)$"); rationale: str = Field(min_length=3, max_length=10000); conditions: str | None = Field(None, max_length=10000)
class EvidenceWrite(BaseModel): execution_task_id: UUID | None = None; evidence_type: str = Field(max_length=40); reference: str = Field(max_length=500); checksum_sha256: str | None = Field(None, pattern=r"^[a-fA-F0-9]{64}$"); notes: str | None = Field(None, max_length=10000)
class ArtifactWrite(AttachmentWrite): package_id: UUID
class ReleaseWrite(BaseModel): property_id: UUID | None = None; name: str = Field(min_length=3, max_length=200); release_type: str = Field(pattern=r"^(major|minor|patch|emergency)$"); description: str = Field(min_length=3, max_length=30000); planned_start: datetime | None = None; planned_end: datetime | None = None; release_notes: str | None = Field(None, max_length=30000); rollback_plan: str = Field(min_length=3, max_length=30000)
class CommunicationWrite(BaseModel): change_request_id: UUID | None = None; release_id: UUID | None = None; communication_type: str = Field(max_length=40); audience: str = Field(max_length=80); subject: str = Field(min_length=2, max_length=240); body: str = Field(min_length=2, max_length=30000); channel: str = Field("email", pattern=r"^(email|portal|management|guest_notice|emergency)$"); scheduled_at: datetime | None = None
class RelationshipWrite(BaseModel): target_type: str = Field(pattern=r"^(configuration_item|asset|incident|problem|knowledge_article|runbook|service|maintenance_window|project|vendor|contract|release|ticket)$"); target_id: UUID; relationship_type: str = Field("related", max_length=40); notes: str | None = Field(None, max_length=5000)


def allowed_properties(db, user):
    if user.role in {"admin", "superadmin"}: return None
    return [row.property_id for row in db.query(UserPropertyAccess).filter_by(user_id=user.id, enabled=True).all()]


def require_property(db, user, property_id):
    if property_id is None:
        if user.role not in {"admin", "superadmin"}: raise HTTPException(403, "Corporate changes require administrator access")
        return
    if not db.get(Property, property_id): raise HTTPException(404, "Property not found")
    allowed = allowed_properties(db, user)
    if allowed is not None and property_id not in allowed: raise HTTPException(403, "Property is not authorized")


def scoped(query, column, db, user):
    allowed = allowed_properties(db, user); return query if allowed is None else query.filter(column.in_(allowed))


def change_or_404(db, user, change_id):
    row = db.get(ChangeRequest, change_id)
    if not row: raise HTTPException(404, "Change request not found")
    require_property(db, user, row.property_id); return row


def commit(db, user, action, entity, row, message):
    create_audit_log(db, user.username, action, entity, str(row.id), message); db.commit(); db.refresh(row)
    manager.broadcast_from_thread({"type": "change_record_updated", "entity_type": entity, "entity_id": str(row.id), "action": action, "property_id": str(getattr(row, "property_id", "")) or None}); return row


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user=Depends(reader)):
    q = scoped(db.query(ChangeRequest), ChangeRequest.property_id, db, user); total = q.count(); closed = q.filter_by(status="closed").count(); failed = q.filter_by(status="failed").count()
    rollback_q = scoped(db.query(RollbackExecution).join(ChangeExecution).join(ChangeRequest), ChangeRequest.property_id, db, user)
    return {"open_changes": q.filter(~ChangeRequest.status.in_(("closed", "cancelled"))).count(), "emergency_changes": q.filter(ChangeRequest.priority == "emergency").count(), "pending_approvals": q.filter(ChangeRequest.approval_status == "pending").count(), "cab_queue": q.filter(ChangeRequest.status == "cab_review").count(), "high_risk": q.filter(ChangeRequest.risk_level.in_(("high", "critical"))).count(), "success_rate": round(closed * 100 / max(1, closed + failed), 2), "rollbacks": rollback_q.count(), "recent": q.order_by(desc(ChangeRequest.updated_at)).limit(8).all()}


@router.get("/types")
def types(db: Session = Depends(get_db), _=Depends(reader)): return {"items": db.query(ChangeType).filter_by(enabled=True).order_by(ChangeType.name).all()}
@router.get("/categories")
def categories(db: Session = Depends(get_db), _=Depends(reader)): return {"items": db.query(ChangeCategory).filter_by(enabled=True).order_by(ChangeCategory.name).all()}


@router.get("")
def list_changes(search: str | None = None, status: str | None = None, risk: str | None = None, property_id: UUID | None = None, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), db: Session = Depends(get_db), user=Depends(reader)):
    q = scoped(db.query(ChangeRequest), ChangeRequest.property_id, db, user)
    if search: q = q.filter(or_(ChangeRequest.change_id.ilike(f"%{search[:120]}%"), ChangeRequest.title.ilike(f"%{search[:120]}%")))
    if status: q = q.filter_by(status=status)
    if risk: q = q.filter_by(risk_level=risk)
    if property_id: require_property(db, user, property_id); q = q.filter_by(property_id=property_id)
    total = q.count(); return {"items": q.order_by(desc(ChangeRequest.updated_at)).offset((page - 1) * page_size).limit(page_size).all(), "total": total, "page": page, "page_size": page_size}


@router.post("", status_code=201)
def create_change(payload: ChangeWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    require_property(db, user, payload.property_id)
    if not db.get(ChangeType, payload.type_id): raise HTTPException(422, "Unknown change type")
    row = ChangeRequest(change_id=change_identifier(db), requested_by=user.id, **payload.model_dump()); db.add(row); db.flush(); revision(db, row, user.id, "Initial RFC draft"); return commit(db, user, "CHANGE_CREATED", "ChangeRequest", row, "Created RFC draft")


@router.get("/requests/{change_id}")
def get_change(change_id: UUID, db: Session = Depends(get_db), user=Depends(reader)): return change_or_404(db, user, change_id)


@router.patch("/requests/{change_id}")
def update_change(change_id: UUID, payload: ChangePatch, db: Session = Depends(get_db), user=Depends(contributor)):
    row = change_or_404(db, user, change_id)
    if row.status != "draft": raise HTTPException(409, "Only draft RFCs can be edited")
    revision(db, row, user.id, payload.change_summary); values = payload.model_dump(exclude_unset=True, exclude={"change_summary"})
    for key, value in values.items(): setattr(row, key, value)
    row.version += 1; row.updated_at = datetime.now(timezone.utc); return commit(db, user, "CHANGE_UPDATED", "ChangeRequest", row, payload.change_summary)


@router.post("/requests/{change_id}/actions/{action}")
def lifecycle(change_id: UUID, action: str, payload: ActionWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    row = change_or_404(db, user, change_id); mapping = {"submit": "submitted", "technical-review": "technical_review", "cab-review": "cab_review", "approve": "approved", "schedule": "scheduled", "implement": "implemented", "verify": "verified", "close": "closed", "cancel": "cancelled", "fail": "failed"}
    target = mapping.get(action)
    if not target: raise HTTPException(404, "Unsupported lifecycle action")
    if target in {"approved", "closed", "cancelled"} and user.role not in {"admin", "superadmin"}: raise HTTPException(403, "Administrator approval required")
    transition(db, row, target, user, payload.comments); db.commit(); return row


@router.get("/requests/{change_id}/approvals")
def approvals(change_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    change_or_404(db, user, change_id); return {"items": db.query(ChangeApproval).filter_by(change_request_id=change_id).order_by(ChangeApproval.requested_at).all()}


@router.post("/requests/{change_id}/approvals/{approval_id}")
def decide_approval(change_id: UUID, approval_id: UUID, payload: ApprovalWrite, db: Session = Depends(get_db), user=Depends(admin)):
    row = change_or_404(db, user, change_id); approval = db.query(ChangeApproval).filter_by(id=approval_id, change_request_id=row.id, status="pending").first()
    if not approval: raise HTTPException(404, "Pending approval not found")
    if row.requested_by == user.id: raise HTTPException(403, "Requester cannot approve own RFC")
    approval.status = "approved" if payload.decision in {"approved", "conditional_approved"} else payload.decision; approval.comments = payload.comments; approval.conditions = payload.conditions; approval.approver_id = user.id; approval.decided_at = datetime.now(timezone.utc)
    return commit(db, user, "CHANGE_APPROVAL_DECIDED", "ChangeApproval", approval, payload.decision)


@router.get("/requests/{change_id}/tasks")
def tasks(change_id: UUID, db: Session = Depends(get_db), user=Depends(reader)): change_or_404(db, user, change_id); return {"items": db.query(ChangeTask).filter_by(change_request_id=change_id).order_by(ChangeTask.sequence_order).all()}
@router.post("/requests/{change_id}/tasks", status_code=201)
def create_task(change_id: UUID, payload: TaskWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    row = change_or_404(db, user, change_id)
    if row.status != "draft": raise HTTPException(409, "Tasks are fixed after submission")
    task = ChangeTask(change_request_id=row.id, **payload.model_dump()); db.add(task); return commit(db, user, "CHANGE_TASK_CREATED", "ChangeTask", task, "Added implementation task")


@router.get("/requests/{change_id}/comments")
def comments(change_id: UUID, db: Session = Depends(get_db), user=Depends(reader)): change_or_404(db, user, change_id); return {"items": db.query(ChangeComment).filter_by(change_request_id=change_id).order_by(ChangeComment.created_at).all()}
@router.post("/requests/{change_id}/comments", status_code=201)
def add_comment(change_id: UUID, payload: CommentWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    change_or_404(db, user, change_id); row = ChangeComment(change_request_id=change_id, user_id=user.id, **payload.model_dump()); db.add(row); db.commit(); db.refresh(row); return row
@router.post("/requests/{change_id}/attachments", status_code=201)
def add_attachment(change_id: UUID, payload: AttachmentWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    change_or_404(db, user, change_id); row = ChangeAttachment(change_request_id=change_id, uploaded_by=user.id, **payload.model_dump()); db.add(row); return commit(db, user, "CHANGE_ATTACHMENT_ADDED", "ChangeAttachment", row, "Added controlled attachment metadata")
@router.get("/requests/{change_id}/attachments")
def attachments(change_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    change_or_404(db, user, change_id); return {"items": db.query(ChangeAttachment).filter_by(change_request_id=change_id).order_by(desc(ChangeAttachment.created_at)).all()}
@router.get("/requests/{change_id}/revisions")
def revisions(change_id: UUID, db: Session = Depends(get_db), user=Depends(reader)): change_or_404(db, user, change_id); return {"items": db.query(ChangeRevision).filter_by(change_request_id=change_id).order_by(desc(ChangeRevision.version)).all()}


@router.post("/requests/{change_id}/risk-assessments", status_code=201)
def create_risk(change_id: UUID, payload: RiskWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    row = change_or_404(db, user, change_id); result = assess_risk(db, row, payload.factors, payload.rationale, user); db.commit(); db.refresh(result); return result
@router.get("/requests/{change_id}/risk-assessments")
def risk_history(change_id: UUID, db: Session = Depends(get_db), user=Depends(reader)): change_or_404(db, user, change_id); return {"items": db.query(RiskAssessment).filter_by(change_request_id=change_id).order_by(desc(RiskAssessment.version)).all()}


@router.get("/requests/{change_id}/relationships")
def relationships(change_id: UUID, db: Session = Depends(get_db), user=Depends(reader)): change_or_404(db, user, change_id); return {"items": db.query(ChangeRelationship).filter_by(change_request_id=change_id).all()}
@router.post("/requests/{change_id}/relationships", status_code=201)
def add_relationship(change_id: UUID, payload: RelationshipWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    change_or_404(db, user, change_id); row = ChangeRelationship(change_request_id=change_id, created_by=user.id, **payload.model_dump()); db.add(row); return commit(db, user, "CHANGE_RELATIONSHIP_ADDED", "ChangeRelationship", row, "Linked operational dependency")


@router.get("/cab/meetings")
def meetings(db: Session = Depends(get_db), user=Depends(reader)): return {"items": scoped(db.query(CABMeeting), CABMeeting.property_id, db, user).order_by(desc(CABMeeting.scheduled_start)).limit(200).all()}
@router.post("/cab/meetings", status_code=201)
def create_meeting(payload: MeetingWrite, db: Session = Depends(get_db), user=Depends(admin)):
    require_property(db, user, payload.property_id)
    if payload.scheduled_end <= payload.scheduled_start: raise HTTPException(422, "Meeting end must follow start")
    row = CABMeeting(**payload.model_dump(), created_by=user.id); db.add(row); return commit(db, user, "CAB_MEETING_CREATED", "CABMeeting", row, "Scheduled CAB meeting")
@router.post("/cab/meetings/{meeting_id}/members", status_code=201)
def add_member(meeting_id: UUID, user_id: str, member_role: str = "member", voting: bool = True, db: Session = Depends(get_db), user=Depends(admin)):
    meeting = db.get(CABMeeting, meeting_id)
    if not meeting: raise HTTPException(404, "CAB meeting not found")
    require_property(db, user, meeting.property_id); row = CABMember(meeting_id=meeting.id, user_id=user_id, member_role=member_role, voting=voting); db.add(row); return commit(db, user, "CAB_MEMBER_ADDED", "CABMember", row, "Added CAB member")
@router.post("/cab/meetings/{meeting_id}/attendance")
def attendance(meeting_id: UUID, attended: bool = True, db: Session = Depends(get_db), user=Depends(contributor)):
    meeting = db.get(CABMeeting, meeting_id)
    if not meeting: raise HTTPException(404, "CAB meeting not found")
    require_property(db, user, meeting.property_id); row = db.query(CABAttendance).filter_by(meeting_id=meeting.id, user_id=user.id).first() or CABAttendance(meeting_id=meeting.id, user_id=user.id); row.attended = attended; row.joined_at = datetime.now(timezone.utc) if attended else row.joined_at; row.left_at = None if attended else datetime.now(timezone.utc); db.add(row); db.commit(); return row
@router.post("/cab/meetings/{meeting_id}/agenda/{change_id}", status_code=201)
def add_agenda(meeting_id: UUID, change_id: UUID, sequence_order: int = Query(ge=0, le=1000), db: Session = Depends(get_db), user=Depends(admin)):
    meeting = db.get(CABMeeting, meeting_id); change = change_or_404(db, user, change_id)
    if not meeting: raise HTTPException(404, "CAB meeting not found")
    require_property(db, user, meeting.property_id)
    if meeting.property_id is not None and meeting.property_id != change.property_id: raise HTTPException(409, "CAB meeting and RFC belong to different properties")
    row = CABAgenda(meeting_id=meeting.id, change_request_id=change.id, sequence_order=sequence_order); db.add(row); return commit(db, user, "CAB_AGENDA_ADDED", "CABAgenda", row, "Added RFC to CAB agenda")
@router.post("/cab/meetings/{meeting_id}/changes/{change_id}/vote")
def vote(meeting_id: UUID, change_id: UUID, payload: VoteWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    meeting = db.get(CABMeeting, meeting_id); change_or_404(db, user, change_id)
    if not meeting or not db.query(CABMember).filter_by(meeting_id=meeting_id, user_id=user.id, voting=True).first(): raise HTTPException(403, "Voting CAB membership required")
    row = db.query(CABVote).filter_by(meeting_id=meeting_id, change_request_id=change_id, voter_id=user.id).first() or CABVote(meeting_id=meeting_id, change_request_id=change_id, voter_id=user.id, vote=payload.vote); row.vote = payload.vote; row.conditions = payload.conditions; row.comments = payload.comments; row.voted_at = datetime.now(timezone.utc); db.add(row); db.commit(); return row
@router.post("/cab/meetings/{meeting_id}/changes/{change_id}/decision")
def cab_decision(meeting_id: UUID, change_id: UUID, payload: DecisionWrite, db: Session = Depends(get_db), user=Depends(admin)):
    meeting = db.get(CABMeeting, meeting_id); change = change_or_404(db, user, change_id)
    if not meeting: raise HTTPException(404, "CAB meeting not found")
    row = decide_cab(db, meeting, change, payload.decision, payload.rationale, payload.conditions, user); return commit(db, user, "CAB_DECISION_RECORDED", "CABDecision", row, payload.decision)


@router.get("/maintenance/windows")
def windows(status: str | None = None, db: Session = Depends(get_db), user=Depends(reader)):
    q = scoped(db.query(MaintenanceWindow), MaintenanceWindow.property_id, db, user)
    if status: q = q.filter_by(status=status)
    return {"items": q.order_by(MaintenanceWindow.start_at).limit(500).all()}
@router.post("/maintenance/windows", status_code=201)
def create_window(payload: WindowWrite, db: Session = Depends(get_db), user=Depends(admin)):
    require_property(db, user, payload.property_id); row = MaintenanceWindow(**payload.model_dump(), created_by=user.id); db.add(row); db.flush(); conflicts = detect_window_conflicts(db, row); result = commit(db, user, "MAINTENANCE_WINDOW_CREATED", "MaintenanceWindow", row, f"Created window with {len(conflicts)} conflicts"); return result
@router.post("/maintenance/windows/{window_id}/approve")
def approve_window(window_id: UUID, payload: ActionWrite, db: Session = Depends(get_db), user=Depends(admin)):
    row = db.get(MaintenanceWindow, window_id)
    if not row: raise HTTPException(404, "Maintenance window not found")
    require_property(db, user, row.property_id); conflicts = detect_window_conflicts(db, row)
    if any(c.severity == "critical" for c in conflicts): raise HTTPException(409, "Critical maintenance conflict must be resolved")
    row.status = "approved"; approval = MaintenanceApproval(window_id=row.id, approver_id=user.id, status="approved", comments=payload.comments, decided_at=datetime.now(timezone.utc)); db.add(approval); return commit(db, user, "MAINTENANCE_WINDOW_APPROVED", "MaintenanceWindow", row, "Approved maintenance window")
@router.get("/maintenance/windows/{window_id}/conflicts")
def window_conflicts(window_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    row = db.get(MaintenanceWindow, window_id)
    if not row: raise HTTPException(404, "Maintenance window not found")
    require_property(db, user, row.property_id); return {"items": db.query(MaintenanceConflict).filter_by(window_id=row.id).order_by(desc(MaintenanceConflict.detected_at)).all()}


@router.post("/requests/{change_id}/executions", status_code=201)
def execute(change_id: UUID, db: Session = Depends(get_db), user=Depends(contributor)):
    change = change_or_404(db, user, change_id); row = start_execution(db, change, user); db.commit(); db.refresh(row); return row
@router.get("/requests/{change_id}/executions")
def executions(change_id: UUID, db: Session = Depends(get_db), user=Depends(reader)): change_or_404(db, user, change_id); return {"items": db.query(ChangeExecution).filter_by(change_request_id=change_id).order_by(desc(ChangeExecution.created_at)).all()}
@router.get("/executions/{execution_id}/tasks")
def execution_tasks(execution_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    execution = db.get(ChangeExecution, execution_id)
    if not execution: raise HTTPException(404, "Execution not found")
    change_or_404(db, user, execution.change_request_id); return {"items": db.query(ExecutionTask).filter_by(execution_id=execution.id).order_by(ExecutionTask.sequence_order).all()}
@router.get("/executions/{execution_id}/timeline")
def execution_timeline(execution_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    execution = db.get(ChangeExecution, execution_id)
    if not execution: raise HTTPException(404, "Execution not found")
    change_or_404(db, user, execution.change_request_id)
    return {"logs": db.query(ExecutionLog).filter_by(execution_id=execution.id).order_by(ExecutionLog.created_at).all(), "evidence": db.query(ExecutionEvidence).filter_by(execution_id=execution.id).order_by(ExecutionEvidence.created_at).all()}
@router.post("/executions/{execution_id}/tasks/{task_id}/complete")
def complete_task(execution_id: UUID, task_id: UUID, notes: str = Query("", max_length=10000), db: Session = Depends(get_db), user=Depends(contributor)):
    execution = db.get(ChangeExecution, execution_id)
    if not execution: raise HTTPException(404, "Execution not found")
    change_or_404(db, user, execution.change_request_id); task = db.query(ExecutionTask).filter_by(id=task_id, execution_id=execution.id).first()
    if not task: raise HTTPException(404, "Execution task not found")
    result = complete_execution_task(db, execution, task, user, notes); db.commit(); return result
@router.post("/executions/{execution_id}/evidence", status_code=201)
def add_evidence(execution_id: UUID, payload: EvidenceWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    execution = db.get(ChangeExecution, execution_id)
    if not execution: raise HTTPException(404, "Execution not found")
    change_or_404(db, user, execution.change_request_id); row = ExecutionEvidence(execution_id=execution.id, added_by=user.id, **payload.model_dump()); db.add(row); return commit(db, user, "CHANGE_EVIDENCE_ADDED", "ExecutionEvidence", row, "Added execution evidence")
@router.post("/executions/{execution_id}/verify")
def verify_execution(execution_id: UUID, successful: bool, notes: str = Query(min_length=2, max_length=10000), db: Session = Depends(get_db), user=Depends(contributor)):
    execution = db.get(ChangeExecution, execution_id)
    if not execution: raise HTTPException(404, "Execution not found")
    change = change_or_404(db, user, execution.change_request_id)
    if execution.progress_percent < 100: raise HTTPException(409, "All execution tasks must be complete")
    execution.status = "completed" if successful else "failed"; execution.verification_status = "passed" if successful else "failed"; execution.failure_summary = None if successful else notes; execution.completed_at = datetime.now(timezone.utc); transition(db, change, "implemented" if successful else "failed", user, notes); db.commit(); return execution
@router.post("/executions/{execution_id}/rollback", status_code=201)
def rollback(execution_id: UUID, reason: str = Query(min_length=3, max_length=10000), db: Session = Depends(get_db), user=Depends(contributor)):
    execution = db.get(ChangeExecution, execution_id)
    if not execution: raise HTTPException(404, "Execution not found")
    change = change_or_404(db, user, execution.change_request_id); row = initiate_rollback(db, execution, change, reason, user); db.commit(); db.refresh(row); return row
@router.post("/rollbacks/{rollback_id}/approve")
def approve_rollback(rollback_id: UUID, db: Session = Depends(get_db), user=Depends(admin)):
    row = db.get(RollbackExecution, rollback_id)
    if not row or row.status != "pending": raise HTTPException(409, "Pending rollback not found")
    execution = db.get(ChangeExecution, row.execution_id); change_or_404(db, user, execution.change_request_id); row.status = "approved"; row.approved_by = user.id; execution.status = "rollback_running"; row.started_at = datetime.now(timezone.utc); return commit(db, user, "CHANGE_ROLLBACK_APPROVED", "RollbackExecution", row, "Approved manual rollback")
@router.post("/rollbacks/{rollback_id}/complete")
def complete_rollback(rollback_id: UUID, successful: bool, notes: str = Query(min_length=2, max_length=10000), db: Session = Depends(get_db), user=Depends(admin)):
    row = db.get(RollbackExecution, rollback_id)
    if not row or row.status not in {"approved", "running"}: raise HTTPException(409, "Approved rollback required")
    execution = db.get(ChangeExecution, row.execution_id); change = change_or_404(db, user, execution.change_request_id); row.status = "completed" if successful else "failed"; row.completed_at = datetime.now(timezone.utc); row.verification_notes = notes; execution.status = "rolled_back" if successful else "rollback_failed"; change.status = "failed"; return commit(db, user, "CHANGE_ROLLBACK_COMPLETED", "RollbackExecution", row, row.status)


@router.get("/releases")
def releases(db: Session = Depends(get_db), user=Depends(reader)): return {"items": scoped(db.query(Release), Release.property_id, db, user).order_by(desc(Release.created_at)).limit(500).all()}
@router.post("/releases", status_code=201)
def create_release(payload: ReleaseWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    require_property(db, user, payload.property_id); row = Release(release_id=release_identifier(db), owner_id=user.id, **payload.model_dump()); db.add(row); return commit(db, user, "RELEASE_CREATED", "Release", row, "Created release plan")
@router.post("/releases/{release_id}/packages", status_code=201)
def add_package(release_id: UUID, name: str = Query(min_length=2, max_length=180), description: str | None = Query(None, max_length=10000), db: Session = Depends(get_db), user=Depends(contributor)):
    release = db.get(Release, release_id)
    if not release: raise HTTPException(404, "Release not found")
    require_property(db, user, release.property_id); row = ReleasePackage(release_id=release.id, name=name, description=description); db.add(row); return commit(db, user, "RELEASE_PACKAGE_CREATED", "ReleasePackage", row, "Added release package")
@router.post("/releases/{release_id}/versions", status_code=201)
def add_release_version(release_id: UUID, version: str = Query(min_length=1, max_length=80), notes: str | None = Query(None, max_length=10000), db: Session = Depends(get_db), user=Depends(contributor)):
    release = db.get(Release, release_id)
    if not release: raise HTTPException(404, "Release not found")
    require_property(db, user, release.property_id); row = ReleaseVersion(release_id=release.id, version=version, notes=notes, created_by=user.id); db.add(row); return commit(db, user, "RELEASE_VERSION_CREATED", "ReleaseVersion", row, "Created immutable release version draft")
@router.post("/releases/{release_id}/deployments", status_code=201)
def add_deployment(release_id: UUID, wave_number: int = Query(1, ge=1, le=100), property_id: UUID | None = None, change_request_id: UUID | None = None, scheduled_start: datetime | None = None, db: Session = Depends(get_db), user=Depends(contributor)):
    release = db.get(Release, release_id)
    if not release: raise HTTPException(404, "Release not found")
    require_property(db, user, property_id or release.property_id)
    if change_request_id: change_or_404(db, user, change_request_id)
    row = ReleaseDeployment(release_id=release.id, wave_number=wave_number, property_id=property_id or release.property_id, change_request_id=change_request_id, scheduled_start=scheduled_start); db.add(row); return commit(db, user, "RELEASE_DEPLOYMENT_PLANNED", "ReleaseDeployment", row, "Planned controlled deployment wave")
@router.post("/releases/{release_id}/artifacts", status_code=201)
def add_release_artifact(release_id: UUID, payload: ArtifactWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    release = db.get(Release, release_id)
    if not release: raise HTTPException(404, "Release not found")
    require_property(db, user, release.property_id)
    package = db.query(ReleasePackage).filter_by(id=payload.package_id, release_id=release.id).first()
    if not package: raise HTTPException(404, "Release package not found")
    values = payload.model_dump(exclude={"package_id"}); row = ReleaseArtifact(package_id=package.id, **values); db.add(row)
    return commit(db, user, "RELEASE_ARTIFACT_ADDED", "ReleaseArtifact", row, "Added checksum-protected release artifact metadata")


@router.get("/communications")
def communications(db: Session = Depends(get_db), user=Depends(reader)):
    q = db.query(ChangeCommunication); allowed = allowed_properties(db, user)
    if allowed is not None:
        change_ids = db.query(ChangeRequest.id).filter(ChangeRequest.property_id.in_(allowed))
        release_ids = db.query(Release.id).filter(Release.property_id.in_(allowed))
        q = q.filter(or_(ChangeCommunication.change_request_id.in_(change_ids), ChangeCommunication.release_id.in_(release_ids)))
    return {"items": q.order_by(desc(ChangeCommunication.created_at)).limit(500).all()}
@router.post("/communications", status_code=201)
def create_communication(payload: CommunicationWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    if not payload.change_request_id and not payload.release_id: raise HTTPException(422, "Change or release link required")
    if payload.change_request_id: change_or_404(db, user, payload.change_request_id)
    if payload.release_id:
        release = db.get(Release, payload.release_id)
        if not release: raise HTTPException(404, "Release not found")
        require_property(db, user, release.property_id)
    row = ChangeCommunication(created_by=user.id, **payload.model_dump()); db.add(row); return commit(db, user, "CHANGE_COMMUNICATION_CREATED", "ChangeCommunication", row, "Created reviewed communication")


@router.get("/approvals/queue")
def approval_queue(status: str = "pending", page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), db: Session = Depends(get_db), user=Depends(contributor)):
    q = db.query(ChangeApproval).join(ChangeRequest); q = scoped(q, ChangeRequest.property_id, db, user).filter(ChangeApproval.status == status); total = q.count(); return {"items": q.order_by(ChangeApproval.requested_at).offset((page - 1) * page_size).limit(page_size).all(), "total": total, "page": page, "page_size": page_size}


@router.get("/reports/summary")
def report_summary(db: Session = Depends(get_db), user=Depends(reader)):
    q = scoped(db.query(ChangeRequest), ChangeRequest.property_id, db, user); closed = q.filter_by(status="closed").count(); failed = q.filter_by(status="failed").count(); total = closed + failed
    approval_q = scoped(db.query(ChangeApproval).join(ChangeRequest), ChangeRequest.property_id, db, user).filter(ChangeApproval.decided_at.is_not(None))
    avg_approval = approval_q.with_entities(func.avg(func.extract("epoch", ChangeApproval.decided_at - ChangeApproval.requested_at))).scalar()
    rollback_q = scoped(db.query(RollbackExecution).join(ChangeExecution).join(ChangeRequest), ChangeRequest.property_id, db, user)
    return {"total": q.count(), "success_rate": round(closed * 100 / max(1, total), 2), "failed": failed, "emergency": q.filter(ChangeRequest.priority == "emergency").count(), "pending_approvals": q.filter(ChangeRequest.approval_status == "pending").count(), "average_approval_seconds": round(float(avg_approval or 0), 2), "rollbacks": rollback_q.count(), "maintenance_windows": scoped(db.query(MaintenanceWindow), MaintenanceWindow.property_id, db, user).count(), "releases": scoped(db.query(Release), Release.property_id, db, user).count()}


def safe_csv(value): return f"'{value}" if str(value or "").startswith(("=", "+", "-", "@")) else str(value or "")
@router.get("/reports/export")
def export(format: str = Query("csv", pattern=r"^(csv|xlsx|pdf)$"), db: Session = Depends(get_db), user=Depends(reader)):
    rows = scoped(db.query(ChangeRequest), ChangeRequest.property_id, db, user).order_by(desc(ChangeRequest.created_at)).limit(5000).all(); headers = ["Change ID", "Title", "Status", "Risk", "Priority", "Created"]
    data = [[safe_csv(r.change_id), safe_csv(r.title), r.status, r.risk_level, r.priority, r.created_at.isoformat()] for r in rows]
    if format == "csv":
        output = io.StringIO(); writer = csv.writer(output); writer.writerow(headers); writer.writerows(data); return Response(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=change-report.csv"})
    if format == "xlsx":
        book = Workbook(); sheet = book.active; sheet.title = "Changes"; sheet.append(headers)
        for row in data: sheet.append(row)
        output = io.BytesIO(); book.save(output); return Response(output.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=change-report.xlsx"})
    from app.api.v1.knowledge import printable_pdf
    return Response(printable_pdf("HIOP Change Report", [" | ".join(map(str, row)) for row in data]), media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=change-report.pdf"})


@router.get("/audit-history")
def audit(entity_id: str | None = Query(None, max_length=80), page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), db: Session = Depends(get_db), _=Depends(admin)):
    entities = {"ChangeRequest", "ChangeApproval", "ChangeTask", "CABMeeting", "CABMember", "CABAgenda", "CABDecision", "RiskAssessment", "MaintenanceWindow", "ChangeExecution", "ExecutionEvidence", "RollbackExecution", "Release", "ReleasePackage", "ReleaseVersion", "ReleaseDeployment", "ChangeCommunication", "ChangeRelationship"}; q = db.query(AuditLog).filter(AuditLog.entity_type.in_(entities))
    if entity_id: q = q.filter_by(entity_id=entity_id)
    total = q.count(); return {"items": q.order_by(desc(AuditLog.created_at)).offset((page - 1) * page_size).limit(page_size).all(), "total": total, "page": page, "page_size": page_size}
