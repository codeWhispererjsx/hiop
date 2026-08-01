import json

from app.models.incidents import OperationalPlaybook, OperationalPlaybookVersion

SEVERITY = {"informational": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def select_playbooks(db, incident):
    candidates = (
        db.query(OperationalPlaybook)
        .filter_by(property_id=incident.property_id, enabled=True, status="active")
        .all()
    )
    ranked = []
    for playbook in candidates:
        types = json.loads(playbook.incident_types or "[]")
        if types and incident.incident_type not in types:
            continue
        score, reasons = 30, ["property and active-status match"]
        if incident.incident_type in types:
            score += 40
            reasons.append("incident type match")
        level = SEVERITY.get(incident.severity, 2)
        if SEVERITY.get(playbook.minimum_severity, 0) <= level <= SEVERITY.get(playbook.maximum_severity, 4):
            score += 20
            reasons.append("severity range match")
        if playbook.current_version_id and db.get(OperationalPlaybookVersion, playbook.current_version_id):
            score += 10
            reasons.append("approved current version")
        ranked.append({"playbook": playbook, "score": score, "reasons": reasons})
    ranked.sort(key=lambda item: (-item["score"], item["playbook"].name))
    return {
        "items": ranked,
        "requires_human_selection": incident.severity in {"high", "critical"} or len(ranked) != 1,
        "conflict": len(ranked) > 1 and ranked[0]["score"] == ranked[1]["score"],
    }
