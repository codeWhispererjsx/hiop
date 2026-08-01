from app.models.automation import AutomationAction
from app.models.incidents import IncidentRemediationRecommendation

RULES = (
    ("device_failure", "request_device_scan", "Request a bounded device scan", "Device failure incidents can be verified with an approved scan.", 80),
    ("network_outage", "request_topology_impact_analysis", "Request topology impact analysis", "Network outage scope can be reviewed through topology evidence.", 75),
    ("configuration_change_failure", "request_configuration_backup", "Request configuration evidence capture", "Capture a reviewed configuration version before further change.", 85),
    ("compliance_incident", "request_compliance_evaluation", "Request compliance evaluation", "Re-evaluate approved rules and preserve the result as evidence.", 80),
)


def generate_recommendations(db, incident):
    created = []
    for incident_type, action_key, title, rationale, confidence in RULES:
        if incident.incident_type != incident_type:
            continue
        action = db.get(AutomationAction, action_key)
        if not action or not action.enabled:
            continue
        exists = db.query(IncidentRemediationRecommendation).filter_by(
            incident_id=incident.id, action_key=action_key, status="proposed"
        ).first()
        if exists:
            continue
        row = IncidentRemediationRecommendation(
            incident_id=incident.id, recommendation_type="approved_action",
            action_key=action_key, title=title, rationale=rationale,
            confidence_score=confidence, risk_level=action.risk_level,
            approval_required=True, source_rule=f"incident_type:{incident_type}",
            evidence='["incident type", "linked operational sources"]',
            verification_definition='{"required":true,"manual_confirmation":true}',
        )
        db.add(row)
        created.append(row)
    return created
