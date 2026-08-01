from datetime import datetime, timezone

from app.models.incidents import IncidentEscalation, IncidentEscalationRule, IncidentResponseTarget, IncidentTask
from app.services.incident_orchestration_service import publish, timeline

SEVERITY = {"informational": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def evaluate_incident(db, incident, now=None):
    now = now or datetime.now(timezone.utc)
    rules = db.query(IncidentEscalationRule).filter_by(property_id=incident.property_id, enabled=True).all()
    target = db.query(IncidentResponseTarget).filter_by(
        property_id=incident.property_id, incident_type=incident.incident_type,
        severity=incident.severity, enabled=True,
    ).first()
    reasons = []
    age_minutes = max(0, int((now - incident.detected_at).total_seconds() / 60))
    if target:
        if not incident.acknowledged_at and age_minutes >= target.acknowledgement_target_minutes:
            reasons.append("acknowledgement_overdue")
        if not incident.contained_at and age_minutes >= target.containment_target_minutes:
            reasons.append("containment_overdue")
        if not incident.recovered_at and age_minutes >= target.recovery_target_minutes:
            reasons.append("recovery_overdue")
        if not incident.last_communication_at and age_minutes >= target.update_frequency_minutes:
            reasons.append("communication_update_overdue")
    if incident.severity in {"high", "critical"} and not incident.incident_commander_id:
        reasons.append("incident_commander_missing")
    if db.query(IncidentTask).filter(
        IncidentTask.incident_id == incident.id, IncidentTask.due_at < now,
        IncidentTask.status.notin_(("completed", "verified", "cancelled")),
    ).count():
        reasons.append("task_overdue")
    created = []
    for rule in rules:
        if rule.incident_type and rule.incident_type != incident.incident_type:
            continue
        if SEVERITY.get(incident.severity, 0) < SEVERITY.get(rule.minimum_severity, 0):
            continue
        if rule.elapsed_minutes is not None and age_minutes < rule.elapsed_minutes:
            continue
        existing = db.query(IncidentEscalation).filter_by(incident_id=incident.id, rule_id=rule.id).all()
        if len(existing) >= rule.maximum_escalations:
            continue
        last = max((row.escalated_at for row in existing), default=None)
        if last and (now - last).total_seconds() < rule.repeat_interval_minutes * 60:
            continue
        reason = ", ".join(reasons) or "structured escalation rule matched"
        row = IncidentEscalation(incident_id=incident.id, rule_id=rule.id, action=rule.escalation_action, escalation_count=len(existing) + 1, reason=reason)
        db.add(row)
        created.append(row)
        timeline(db, incident, "escalation", f"Escalation: {rule.name}", "scheduler", reason, incident.severity)
    if created:
        publish("incident_updated", incident, escalation_count=len(created))
        from app.services.incident_notification_service import notify_incident
        notify_incident(db, incident, "escalation", ", ".join(reasons) or "Escalation rule matched.")
    return {"created": len(created), "reasons": reasons}
