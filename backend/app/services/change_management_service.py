import hashlib
import json
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import or_

from app.models.change_management import (
    CABAttendance, CABDecision, CABMember, CABVote, ChangeApproval,
    ChangeExecution, ChangeRequest, ChangeRevision, ChangeTask, ExecutionLog,
    ExecutionTask, MaintenanceConflict, MaintenanceWindow, RiskAssessment,
    RiskFactor, RollbackExecution,
)
from app.services.audit_service import create_audit_log
from app.websocket.connection_manager import manager


CHANGE_TRANSITIONS = {
    "draft": {"submitted", "cancelled"},
    "submitted": {"technical_review", "draft", "cancelled"},
    "technical_review": {"cab_review", "approved", "draft", "cancelled"},
    "cab_review": {"approved", "technical_review", "cancelled"},
    "approved": {"scheduled", "cancelled"},
    "scheduled": {"in_progress", "cancelled"},
    "in_progress": {"implemented", "failed", "cancelled"},
    "implemented": {"verified", "failed"},
    "verified": {"closed", "failed"},
    "failed": {"in_progress", "cancelled"},
    "closed": set(), "cancelled": set(),
}
RISK_FACTORS = {
    "guest_impact", "revenue_impact", "operational_impact", "security_impact",
    "compliance_impact", "downtime", "rollback_complexity",
    "service_dependencies", "vendor_dependency", "maintenance_duration",
}


def change_identifier(db) -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"CHG-{year}-"
    latest = db.query(ChangeRequest.change_id).filter(ChangeRequest.change_id.like(f"{prefix}%")).order_by(ChangeRequest.change_id.desc()).first()
    number = int(latest[0].rsplit("-", 1)[-1]) + 1 if latest else 1
    return f"{prefix}{number:06d}"


def release_identifier(db) -> str:
    from app.models.change_management import Release
    year = datetime.now(timezone.utc).year; prefix = f"REL-{year}-"
    latest = db.query(Release.release_id).filter(Release.release_id.like(f"{prefix}%")).order_by(Release.release_id.desc()).first()
    number = int(latest[0].rsplit("-", 1)[-1]) + 1 if latest else 1
    return f"{prefix}{number:06d}"


def snapshot(change: ChangeRequest) -> dict:
    fields = ("change_id", "title", "description", "business_justification", "technical_justification", "risk_level", "impact_level", "priority", "backout_plan", "validation_plan", "test_plan", "communication_plan", "implementation_plan", "status", "approval_status", "scheduled_start", "scheduled_end")
    return {field: (value.isoformat() if isinstance((value := getattr(change, field)), datetime) else value) for field in fields}


def revision(db, change, actor, summary):
    data = json.dumps(snapshot(change), sort_keys=True, separators=(",", ":"))
    row = ChangeRevision(change_request_id=change.id, version=change.version, snapshot=data, checksum_sha256=hashlib.sha256(data.encode()).hexdigest(), change_summary=summary, created_by=actor)
    db.add(row); return row


def transition(db, change, target, user, comments=None):
    if target not in CHANGE_TRANSITIONS.get(change.status, set()): raise HTTPException(409, f"Invalid change transition: {change.status} -> {target}")
    if target == "submitted":
        required = (change.business_justification, change.technical_justification, change.backout_plan, change.validation_plan, change.test_plan, change.communication_plan, change.implementation_plan)
        if not all(str(value or "").strip() for value in required): raise HTTPException(409, "Complete all plans and justifications before submission")
        change.submitted_at = datetime.now(timezone.utc); change.approval_status = "pending"
        db.add(ChangeApproval(change_request_id=change.id, stage="technical", status="pending"))
    if target == "cab_review":
        technical = db.query(ChangeApproval).filter_by(change_request_id=change.id, stage="technical").order_by(ChangeApproval.requested_at.desc()).first()
        if not technical or technical.status != "approved":
            raise HTTPException(409, "Technical approval is required before CAB review")
        db.add(ChangeApproval(change_request_id=change.id, stage="cab", status="pending"))
    if target == "approved":
        pending = db.query(ChangeApproval).filter_by(change_request_id=change.id, status="pending").count()
        rejected = db.query(ChangeApproval).filter_by(change_request_id=change.id, status="rejected").count()
        if pending or rejected: raise HTTPException(409, "All required approvals must be accepted")
        change.approval_status = "approved"
    if target == "scheduled":
        if not change.scheduled_start or not change.scheduled_end or change.scheduled_end <= change.scheduled_start: raise HTTPException(409, "A valid schedule is required")
        if change.maintenance_window_id:
            window = db.get(MaintenanceWindow, change.maintenance_window_id)
            if not window or window.status != "approved" or change.scheduled_start < window.start_at or change.scheduled_end > window.end_at: raise HTTPException(409, "Change must fit inside an approved maintenance window")
    now = datetime.now(timezone.utc)
    if target == "implemented": change.implemented_at = now
    if target == "closed": change.closed_at = now
    previous = change.status; change.status = target; change.updated_at = now
    create_audit_log(db, user.username, "CHANGE_STATUS_CHANGED", "ChangeRequest", str(change.id), f"{previous} -> {target}: {comments or 'No additional comment'}")
    manager.broadcast_from_thread({"type": "change_updated", "change_id": str(change.id), "status": target, "property_id": str(change.property_id) if change.property_id else None})
    return change


def calculate_risk(factors: dict[str, int]) -> tuple[int, str]:
    unknown = set(factors) - RISK_FACTORS
    if unknown: raise HTTPException(422, f"Unsupported risk factors: {', '.join(sorted(unknown))}")
    if set(factors) != RISK_FACTORS: raise HTTPException(422, "All ten risk factors are required")
    if any(not isinstance(value, int) or value < 0 or value > 5 for value in factors.values()): raise HTTPException(422, "Risk factors must be integers from 0 to 5")
    score = sum(factors.values())
    level = "low" if score <= 12 else "medium" if score <= 25 else "high" if score <= 39 else "critical"
    return score, level


def assess_risk(db, change, factors, rationale, user):
    score, level = calculate_risk(factors); version = (db.query(RiskAssessment).filter_by(change_request_id=change.id).count() + 1)
    assessment = RiskAssessment(change_request_id=change.id, version=version, total_score=score, risk_level=level, rationale=rationale, assessed_by=user.id); db.add(assessment); db.flush()
    for name, value in factors.items(): db.add(RiskFactor(assessment_id=assessment.id, factor_type=name, score=value, weight=1, evidence=rationale))
    change.risk_level = level; change.updated_at = datetime.now(timezone.utc)
    create_audit_log(db, user.username, "CHANGE_RISK_ASSESSED", "ChangeRequest", str(change.id), f"Deterministic risk score {score} ({level})")
    return assessment


def detect_window_conflicts(db, window):
    db.query(MaintenanceConflict).filter_by(window_id=window.id, status="open").delete()
    query = db.query(MaintenanceWindow).filter(
        MaintenanceWindow.id != window.id,
        MaintenanceWindow.status.in_(("approved", "scheduled")),
        MaintenanceWindow.start_at < window.end_at,
        MaintenanceWindow.end_at > window.start_at,
    )
    if window.property_id is not None:
        query = query.filter(or_(MaintenanceWindow.property_id == window.property_id, MaintenanceWindow.property_id.is_(None)))
    overlaps = query.all()
    rows = []
    for other in overlaps:
        severity = "critical" if window.blackout or other.blackout else "high"
        row = MaintenanceConflict(window_id=window.id, conflicting_window_id=other.id, conflict_type="blackout_overlap" if severity == "critical" else "schedule_overlap", severity=severity, details=f"Overlaps {other.name}"); db.add(row); rows.append(row)
    return rows


def decide_cab(db, meeting, change, decision, rationale, conditions, user):
    member = db.query(CABMember).filter_by(meeting_id=meeting.id, user_id=user.id, voting=True).first()
    if not member: raise HTTPException(403, "Voting CAB membership required")
    attendance = db.query(CABAttendance).filter_by(meeting_id=meeting.id, attended=True).count()
    quorum = attendance >= meeting.quorum_required
    if not quorum: raise HTTPException(409, "CAB quorum is not met")
    votes = db.query(CABVote).filter_by(meeting_id=meeting.id, change_request_id=change.id).all()
    approvals = sum(v.vote in {"approve", "conditional_approve"} for v in votes); rejections = sum(v.vote == "reject" for v in votes)
    if decision in {"approved", "conditional_approved"} and approvals <= rejections: raise HTTPException(409, "Recorded votes do not support approval")
    row = CABDecision(meeting_id=meeting.id, change_request_id=change.id, decision=decision, conditions=conditions, rationale=rationale, quorum_met=True, decided_by=user.id); db.add(row)
    approval = db.query(ChangeApproval).filter_by(change_request_id=change.id, stage="cab", status="pending").first()
    if approval:
        approval.status = "approved" if decision in {"approved", "conditional_approved"} else "rejected" if decision == "rejected" else "deferred"; approval.conditions = conditions; approval.comments = rationale; approval.decided_at = datetime.now(timezone.utc)
    return row


def start_execution(db, change, user):
    if change.status != "scheduled": raise HTTPException(409, "Only scheduled changes can start")
    if db.query(ChangeExecution).filter(ChangeExecution.change_request_id == change.id, ChangeExecution.status.in_(("pending", "running", "rollback_running"))).first(): raise HTTPException(409, "An active execution already exists")
    execution = ChangeExecution(change_request_id=change.id, status="running", started_by=user.id, started_at=datetime.now(timezone.utc)); db.add(execution); db.flush()
    tasks = db.query(ChangeTask).filter_by(change_request_id=change.id).order_by(ChangeTask.sequence_order).all()
    for index, task in enumerate(tasks): db.add(ExecutionTask(execution_id=execution.id, change_task_id=task.id, sequence_order=task.sequence_order, title=task.title, status="ready" if index == 0 else "pending"))
    db.add(ExecutionLog(execution_id=execution.id, event_type="execution_started", message="Manual reviewed execution started", actor_id=user.id)); transition(db, change, "in_progress", user)
    manager.broadcast_from_thread({"type": "change_execution_started", "change_id": str(change.id), "execution_id": str(execution.id)})
    return execution


def complete_execution_task(db, execution, task, user, notes):
    if execution.status != "running" or task.status != "ready": raise HTTPException(409, "Execution task is not ready")
    task.status = "completed"; task.notes = notes; task.completed_by = user.id; task.completed_at = datetime.now(timezone.utc)
    next_task = db.query(ExecutionTask).filter(ExecutionTask.execution_id == execution.id, ExecutionTask.sequence_order > task.sequence_order, ExecutionTask.status == "pending").order_by(ExecutionTask.sequence_order).first()
    if next_task: next_task.status = "ready"
    db.flush()
    total = db.query(ExecutionTask).filter_by(execution_id=execution.id).count(); complete = db.query(ExecutionTask).filter_by(execution_id=execution.id, status="completed").count()
    execution.progress_percent = 100 if not total else min(100, round(complete * 100 / total))
    db.add(ExecutionLog(execution_id=execution.id, event_type="task_completed", message=f"Completed: {task.title}", actor_id=user.id))
    return task


def initiate_rollback(db, execution, change, reason, user):
    if execution.status not in {"running", "failed"}: raise HTTPException(409, "Rollback is not available for this execution")
    if db.query(RollbackExecution).filter(RollbackExecution.execution_id == execution.id, RollbackExecution.status.in_(("pending", "approved", "running"))).first(): raise HTTPException(409, "Rollback already active")
    row = RollbackExecution(execution_id=execution.id, reason=reason, plan_snapshot=change.backout_plan, status="pending", initiated_by=user.id); db.add(row); execution.status = "rollback_pending"
    create_audit_log(db, user.username, "CHANGE_ROLLBACK_REQUESTED", "ChangeExecution", str(execution.id), "Rollback requires a separate administrator approval")
    return row
