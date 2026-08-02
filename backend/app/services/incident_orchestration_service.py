import json
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app.models.incidents import (
    IncidentCauseAssessment,
    IncidentChecklistItem,
    IncidentEvidence,
    IncidentParticipant,
    IncidentPlaybookRun,
    IncidentPlaybookStepRun,
    IncidentTask,
    IncidentTimelineEntry,
    OperationalIncident,
    OperationalPlaybook,
    OperationalPlaybookStep,
    OperationalPlaybookVersion,
    PostIncidentReview,
)
from app.services.audit_service import create_audit_log
from app.websocket.connection_manager import manager

TRANSITIONS = {
    "detected": {"declared", "cancelled", "duplicate"},
    "declared": {"acknowledged", "resolved", "cancelled", "duplicate", "merged"},
    "acknowledged": {"investigating", "resolved", "cancelled", "merged"},
    "investigating": {"contained", "mitigating", "monitoring", "resolved", "cancelled"},
    "contained": {"mitigating", "monitoring"},
    "mitigating": {"monitoring", "recovered"},
    "monitoring": {"recovered", "mitigating"},
    "recovered": {"resolved", "monitoring"},
    "resolved": {"closed", "monitoring"},
    "closed": {"investigating"},
}
TIME_FIELDS = {
    "declared": "declared_at", "acknowledged": "acknowledged_at",
    "contained": "contained_at", "mitigating": "mitigated_at",
    "recovered": "recovered_at", "resolved": "resolved_at", "closed": "closed_at",
}


def publish(event, incident, **extra):
    manager.broadcast_from_thread({
        "type": event, "incident_id": str(incident.id),
        "property_id": str(incident.property_id), "status": incident.status, **extra,
    })


def timeline(db, incident, entry_type, title, actor=None, summary=None, severity=None, source_id=None):
    row = IncidentTimelineEntry(
        incident_id=incident.id, property_id=incident.property_id, entry_type=entry_type,
        title=title, summary=summary, severity=severity, actor_user_id=actor,
        source_id=source_id,
    )
    db.add(row)
    return row


def transition(db, incident, target, actor, reason=None):
    terminal_review = target in {"duplicate", "merged"} and incident.status not in {"closed", "cancelled", "duplicate", "merged"}
    if target not in TRANSITIONS.get(incident.status, set()) and not terminal_review:
        raise HTTPException(409, f"Invalid incident transition from {incident.status} to {target}")
    if target in {"cancelled", "duplicate", "merged"} and not reason:
        raise HTTPException(422, "A reason is required")
    if target == "recovered" and not incident.recovery_verified:
        raise HTTPException(409, "Recovery verification must be completed first")
    if target == "resolved":
        blocking = db.query(IncidentTask).filter(
            IncidentTask.incident_id == incident.id,
            IncidentTask.status.notin_(("completed", "verified", "cancelled")),
        ).count()
        if blocking:
            raise HTTPException(409, "Required incident tasks remain open")
    if target == "closed":
        evidence = db.query(IncidentEvidence).filter_by(incident_id=incident.id).count()
        cause = db.query(IncidentCauseAssessment).filter_by(incident_id=incident.id).first()
        if not incident.closure_summary or not incident.closure_reason or not evidence or not cause:
            raise HTTPException(409, "Closure requires summary, reason, evidence, and cause classification")
        if incident.severity in {"high", "critical"} and not incident.incident_commander_id:
            raise HTTPException(409, "An incident commander must approve closure")
    old = incident.status
    incident.status = target
    incident.updated_by = actor
    if target in TIME_FIELDS:
        setattr(incident, TIME_FIELDS[target], datetime.now(timezone.utc))
    timeline(db, incident, "status_changed", f"Status changed to {target}", actor, reason)
    create_audit_log(db, actor, "INCIDENT_STATUS_CHANGED", "OperationalIncident", str(incident.id), f"{old} to {target}")
    publish("incident_status_changed", incident, previous_status=old)
    if target in {"contained", "recovered", "resolved", "closed"} or incident.priority in {"P1", "P2"}:
        from app.services.incident_notification_service import notify_incident
        notify_incident(db, incident, f"status changed to {target}", reason or "Reviewed incident transition.")
    return incident


def start_playbook(db, incident, playbook, actor):
    if incident.severity in {"high", "critical"} and not incident.incident_commander_id:
        raise HTTPException(409, "Assign an incident commander before starting this playbook")
    version = db.get(OperationalPlaybookVersion, playbook.current_version_id) if playbook.current_version_id else None
    if not version or version.status != "approved":
        raise HTTPException(409, "Playbook has no approved active version")
    active = db.query(IncidentPlaybookRun).filter(
        IncidentPlaybookRun.incident_id == incident.id,
        IncidentPlaybookRun.status.in_(("pending", "ready", "running", "paused", "waiting_for_human", "waiting_for_approval", "monitoring")),
    ).first()
    if active:
        raise HTTPException(409, "Incident already has an active playbook run")
    steps = db.query(OperationalPlaybookStep).filter_by(playbook_version_id=version.id).order_by(
        OperationalPlaybookStep.sequence_order, OperationalPlaybookStep.step_key
    ).all()
    run = IncidentPlaybookRun(
        incident_id=incident.id, playbook_id=playbook.id, playbook_version_id=version.id,
        status="running", current_phase=steps[0].phase if steps else None,
        current_step_key=steps[0].step_key if steps else None, steps_total=len(steps),
        started_at=datetime.now(timezone.utc), started_by=actor,
    )
    db.add(run)
    db.flush()
    for index, step in enumerate(steps):
        status = "ready" if index == 0 else "pending"
        if index == 0 and step.step_type in {"human_task", "checklist", "decision", "approval", "communication", "evidence_collection", "verification"}:
            status = "assigned"
            run.status = "waiting_for_approval" if step.approval_required or step.step_type == "approval" else "waiting_for_human"
        step_run = IncidentPlaybookStepRun(
            incident_playbook_run_id=run.id, playbook_step_id=step.id, step_key=step.step_key,
            phase=step.phase, status=status, assigned_role=step.owner_role,
            due_at=datetime.now(timezone.utc) + timedelta(seconds=step.timeout_seconds),
        )
        db.add(step_run)
        db.flush()
        if step.step_type == "human_task":
            db.add(IncidentTask(
                incident_id=incident.id, playbook_run_id=run.id, step_run_id=step_run.id,
                title=step.name, description=step.description, task_type="technical_action",
                assigned_role=step.owner_role, created_by=actor,
                due_at=step_run.due_at, verification_required=step.verification_required,
            ))
        for item_index, item in enumerate(json.loads(step.checklist_definition or "[]")):
            db.add(IncidentChecklistItem(
                incident_id=incident.id, playbook_run_id=run.id, step_run_id=step_run.id,
                item_key=str(item.get("key") or f"{step.step_key}-{item_index + 1}"),
                text=str(item.get("text") or "Checklist item")[:500],
                required=bool(item.get("required", True)),
                evidence_required=bool(item.get("evidence_required", False)),
            ))
    incident.playbook_id, incident.playbook_version_id = playbook.id, version.id
    advance_playbook_run(db, run, actor)
    timeline(db, incident, "playbook_started", f"Playbook {playbook.name} started", actor, source_id=run.id)
    create_audit_log(db, actor, "INCIDENT_PLAYBOOK_STARTED", "IncidentPlaybookRun", str(run.id), f"Started for {incident.incident_number}")
    publish("incident_playbook_started", incident, playbook_run_id=str(run.id))
    return run


def advance_playbook_run(db, run, actor):
    """Advance deterministic ready steps; pause whenever human authority is needed."""
    steps = db.query(IncidentPlaybookStepRun).join(
        OperationalPlaybookStep,
        OperationalPlaybookStep.id == IncidentPlaybookStepRun.playbook_step_id,
    ).filter(
        IncidentPlaybookStepRun.incident_playbook_run_id == run.id
    ).order_by(OperationalPlaybookStep.sequence_order, OperationalPlaybookStep.step_key).all()
    definitions = {
        step.id: step for step in db.query(OperationalPlaybookStep).filter(
            OperationalPlaybookStep.id.in_([row.playbook_step_id for row in steps])
        ).all()
    }
    incident = db.get(OperationalIncident, run.incident_id)
    finished = {"completed", "completed_with_warnings", "skipped", "cancelled"}
    for index, row in enumerate(steps):
        if row.status in finished:
            continue
        if any(previous.status not in finished for previous in steps[:index]):
            break
        definition = definitions[row.playbook_step_id]
        row.status = "ready"
        run.current_phase, run.current_step_key = row.phase, row.step_key
        if definition.step_type in {"human_task", "checklist", "decision", "communication", "evidence_collection", "verification", "wait", "approval", "escalation"}:
            row.status = "waiting_for_approval" if definition.approval_required or definition.step_type == "approval" else "assigned"
            run.status = "waiting_for_approval" if row.status == "waiting_for_approval" else "waiting_for_human"
            publish("incident_playbook_progress", incident, playbook_run_id=str(run.id), current_step=row.step_key, run_status=run.status)
            return run
        if definition.step_type == "automated_action":
            if definition.approval_required:
                row.status, run.status = "waiting_for_approval", "waiting_for_approval"
                return run
            from app.services.automation_execution_service import SAFE_HANDLERS, execute_graph
            if definition.action_key not in SAFE_HANDLERS:
                row.status, row.error_category = "failed", "unsupported_action"
                row.error_summary = "Action is not registered in the approved safe handler catalogue."
                run.status, run.steps_failed = "failed", run.steps_failed + 1
                return run
            row.status, row.started_at = "in_progress", datetime.now(timezone.utc)
            try:
                result = execute_graph({"nodes": [{"id": definition.step_key, "type": "action", "action_key": definition.action_key}], "edges": []})
                row.output_snapshot = json.dumps(result, separators=(",", ":"))
                row.status, row.completed_at = "completed", datetime.now(timezone.utc)
                row.verification_status = "passed" if not definition.verification_required else "pending"
                if definition.verification_required:
                    row.status, run.status = "assigned", "waiting_for_human"
                    return run
                run.steps_completed += 1
            except Exception:
                row.status, row.error_category, row.error_summary = "failed", "action_failed", "Approved action failed safely."
                row.completed_at = datetime.now(timezone.utc)
                run.steps_failed += 1
                if not definition.continue_on_failure:
                    run.status = "failed"
                    return run
        elif definition.step_type == "terminal":
            row.status, row.completed_at = "completed", datetime.now(timezone.utc)
            run.steps_completed += 1
    run.status, run.completed_at = "completed", datetime.now(timezone.utc)
    run.current_step_key = None
    publish("incident_playbook_progress", incident, playbook_run_id=str(run.id), run_status=run.status)
    return run


def complete_playbook_step(
    db, run, step_run, actor, verification_status=None,
    evidence_reference=None, approval_outcome=None,
):
    definition = db.get(OperationalPlaybookStep, step_run.playbook_step_id)
    if step_run.status not in {"assigned", "in_progress", "waiting", "waiting_for_approval", "ready"}:
        raise HTTPException(409, "Playbook step is not awaiting completion")
    if step_run.status == "waiting_for_approval" and approval_outcome not in {"approved", "rejected"}:
        raise HTTPException(422, "Approval outcome is required")
    if approval_outcome == "rejected":
        step_run.status, step_run.completed_at, step_run.completed_by = "failed", datetime.now(timezone.utc), actor
        step_run.error_category, step_run.error_summary = "approval_rejected", "Approval checkpoint was rejected."
        run.status, run.steps_failed = "failed", run.steps_failed + 1
        return run
    if definition.evidence_required:
        evidence = db.query(IncidentEvidence).filter_by(incident_id=run.incident_id).count()
        if not evidence and not evidence_reference:
            raise HTTPException(409, "This playbook step requires incident evidence")
    if definition.verification_required and verification_status not in {"passed", "passed_with_warnings"}:
        raise HTTPException(409, "This playbook step requires successful verification")
    step_run.status = "completed_with_warnings" if verification_status == "passed_with_warnings" else "completed"
    step_run.verification_status = verification_status or ("passed" if not definition.verification_required else "pending")
    step_run.completed_at, step_run.completed_by = datetime.now(timezone.utc), actor
    step_run.output_snapshot = json.dumps({"evidence_reference": evidence_reference}, separators=(",", ":"))
    run.steps_completed += 1
    run.status = "running"
    return advance_playbook_run(db, run, actor)


def retry_playbook_step(db, run, step_run, actor):
    definition = db.get(OperationalPlaybookStep, step_run.playbook_step_id)
    if step_run.status not in {"failed", "timed_out"}:
        raise HTTPException(409, "Only failed or timed-out steps can be retried")
    if step_run.retry_count >= definition.maximum_retries:
        raise HTTPException(409, "Retry limit reached")
    step_run.retry_count += 1
    step_run.status = "ready"
    step_run.started_at = step_run.completed_at = None
    step_run.error_category = step_run.error_summary = None
    run.status, run.completed_at = "running", None
    if run.steps_failed:
        run.steps_failed -= 1
    return advance_playbook_run(db, run, actor)


def compensate_playbook_step(db, run, step_run, actor):
    """Run only the versioned, allowlisted compensation action after a failed step."""
    definition = db.get(OperationalPlaybookStep, step_run.playbook_step_id)
    if step_run.status not in {"failed", "timed_out"}:
        raise HTTPException(409, "Compensation is available only for a failed or timed-out step")
    if not definition.compensation_action_key:
        raise HTTPException(409, "No compensation action is configured for this step")
    from app.services.automation_execution_service import SAFE_HANDLERS, execute_graph
    if definition.compensation_action_key not in SAFE_HANDLERS:
        raise HTTPException(409, "Compensation action is not in the approved safe handler catalogue")
    result = execute_graph(
        {"nodes": [{
            "id": f"{definition.step_key}-compensation",
            "type": "action",
            "action_key": definition.compensation_action_key,
        }], "edges": []},
        {"incident_id": str(run.incident_id), "playbook_run_id": str(run.id)},
    )
    step_run.output_snapshot = json.dumps(
        {"compensation": result, "compensated_by": actor}, separators=(",", ":")
    )
    step_run.status, step_run.completed_at, step_run.completed_by = "cancelled", datetime.now(timezone.utc), actor
    run.steps_skipped += 1
    return run


def process_playbook_timeouts(db, now=None, limit=1000):
    """Mark overdue active steps safely; retry requires an explicit operator action."""
    now = now or datetime.now(timezone.utc)
    rows = db.query(IncidentPlaybookStepRun).filter(
        IncidentPlaybookStepRun.due_at < now,
        IncidentPlaybookStepRun.status.in_(
            ("ready", "assigned", "in_progress", "waiting", "waiting_for_approval")
        ),
    ).limit(limit).all()
    for row in rows:
        run = db.get(IncidentPlaybookRun, row.incident_playbook_run_id)
        if not run or run.status in {"completed", "cancelled", "failed"}:
            continue
        row.status, row.completed_at = "timed_out", now
        row.error_category, row.error_summary = "timeout", "Playbook step exceeded its configured deadline."
        run.status, run.steps_failed = "failed", run.steps_failed + 1
        run.error_category, run.error_summary = "step_timeout", "A playbook step timed out and requires review."
        incident = db.get(OperationalIncident, run.incident_id)
        timeline(db, incident, "playbook_step_timed_out", f"Playbook step timed out: {row.step_key}", "scheduler", source_id=row.id)
        publish("incident_playbook_progress", incident, playbook_run_id=str(run.id), current_step=row.step_key, run_status=run.status)
    return len(rows)


def recovery_readiness(db, incident):
    open_tasks = db.query(IncidentTask).filter(
        IncidentTask.incident_id == incident.id,
        IncidentTask.status.notin_(("completed", "verified", "cancelled")),
    ).count()
    pending_checks = db.query(IncidentChecklistItem).filter(
        IncidentChecklistItem.incident_id == incident.id,
        IncidentChecklistItem.required.is_(True),
        IncidentChecklistItem.status != "completed",
    ).count()
    evidence = db.query(IncidentEvidence).filter_by(incident_id=incident.id).count()
    return {
        "ready": open_tasks == 0 and pending_checks == 0 and evidence > 0,
        "open_tasks": open_tasks, "pending_required_checklist": pending_checks,
        "evidence_count": evidence, "manual_confirmation_required": incident.severity in {"high", "critical"},
    }


def ensure_post_incident_review(db, incident):
    review = db.query(PostIncidentReview).filter_by(incident_id=incident.id).first()
    if not review:
        review = PostIncidentReview(
            incident_id=incident.id,
            status="required" if incident.severity in {"high", "critical"} else "not_required",
        )
        db.add(review)
    return review
