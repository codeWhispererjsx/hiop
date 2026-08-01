from datetime import datetime, timedelta, timezone

from app.models.incidents import OperationalIncident, OperationalIncidentSource
from app.services.incident_orchestration_service import publish, timeline

EVENT_INCIDENT_TYPES = {
    "critical_alert_created": "service_degradation",
    "device_offline": "device_failure",
    "topology_partition_detected": "network_outage",
    "technology_service_unavailable": "service_degradation",
    "revenue_impact_detected": "revenue_system_failure",
    "security_service_degraded": "security_system_failure",
    "restore_validation_failed": "configuration_change_failure",
    "compliance_violation_created": "compliance_incident",
    "correlation_group_created": "monitoring_failure",
    "property_operational_status_changed": "unknown",
}


def create_pending_incident_from_event(db, event):
    incident_type = EVENT_INCIDENT_TYPES.get(event.event_type)
    if not incident_type or not event.property_id:
        return None
    from app.services.settings_service import read_incident_settings
    config = read_incident_settings(db)
    if not config["enabled"]:
        return None
    key = event.correlation_key or f"{event.event_type}:{event.source_entity_id or event.event_id}"
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    existing = db.query(OperationalIncident).filter(
        OperationalIncident.property_id == event.property_id,
        OperationalIncident.correlation_key == key,
        OperationalIncident.created_at >= cutoff,
        OperationalIncident.status.notin_(("closed", "cancelled", "duplicate", "merged")),
    ).first()
    if existing:
        linked = db.query(OperationalIncidentSource).filter_by(
            incident_id=existing.id, source_entity_id=event.id
        ).first()
        if not linked:
            db.add(OperationalIncidentSource(
                incident_id=existing.id, source_type="internal_event",
                source_entity_type=event.event_type, source_entity_id=event.id,
                relationship_type="contributing", source_status=event.status,
                linked_by="automation:event",
            ))
        return existing
    severity = event.severity if event.severity in {"informational", "low", "medium", "high", "critical"} else "medium"
    priority = "P1" if severity == "critical" else "P2" if severity == "high" else "P3"
    levels = {"informational": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
    auto_declared = bool(
        config["automatic_incident_declaration_enabled"]
        and levels[severity] >= levels[config["minimum_automatic_severity"]]
    )
    row = OperationalIncident(
        property_id=event.property_id,
        incident_number=f"INC-{datetime.now(timezone.utc):%Y%m%d}-{str(event.event_id).replace('-', '')[:6].upper()}",
        title=event.event_type.replace("_", " ").title(),
        description="Pending incident created from an approved internal event; human declaration and playbook selection are required.",
        incident_type=incident_type, status="declared" if auto_declared else "detected",
        declared_at=datetime.now(timezone.utc) if auto_declared else None,
        severity=severity, priority=priority,
        source_type="internal_event", source_reference_type=event.event_type,
        source_reference_id=event.id, correlation_key=key, created_by="automation:event",
    )
    db.add(row)
    db.flush()
    db.add(OperationalIncidentSource(
        incident_id=row.id, source_type="internal_event",
        source_entity_type=event.event_type, source_entity_id=event.id,
        relationship_type="triggered", source_status=event.status,
        linked_by="automation:event",
    ))
    timeline(db, row, "incident_declared" if auto_declared else "incident_created", "Incident declared from approved event" if auto_declared else "Pending incident created from internal event", "automation:event", event.event_type, severity)
    publish("incident_declared" if auto_declared else "incident_created", row, pending_human_declaration=not auto_declared)
    return row
