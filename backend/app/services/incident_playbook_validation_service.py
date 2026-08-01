import hashlib
import json

from app.models.automation import AutomationAction
from app.services.automation_execution_service import SAFE_HANDLERS

PHASES = {
    "detection", "declaration", "acknowledgement", "triage", "investigation",
    "containment", "mitigation", "recovery", "validation", "communication",
    "closure", "post_incident",
}
STEP_TYPES = {
    "human_task", "checklist", "automated_action", "approval", "decision",
    "communication", "evidence_collection", "verification", "wait",
    "escalation", "terminal",
}
PROHIBITED_KEYS = {"script", "shell", "command", "code", "url", "webhook", "password", "secret", "token"}


def _safe_structure(value, depth=0):
    if depth > 8:
        raise ValueError("Playbook definition exceeds the maximum nesting depth")
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in PROHIBITED_KEYS:
                raise ValueError(f"Playbook definition contains prohibited field: {key}")
            _safe_structure(item, depth + 1)
    elif isinstance(value, list):
        if len(value) > 500:
            raise ValueError("Playbook definition exceeds the item limit")
        for item in value:
            _safe_structure(item, depth + 1)


def validate_playbook(db, playbook, version, steps):
    errors, warnings = [], []
    if not steps:
        errors.append("At least one playbook step is required")
    keys = [step.step_key for step in steps]
    if len(keys) != len(set(keys)):
        errors.append("Step keys must be unique")
    for step in steps:
        if step.phase not in PHASES:
            errors.append(f"Unsupported phase: {step.phase}")
        if step.step_type not in STEP_TYPES:
            errors.append(f"Unsupported step type: {step.step_type}")
        if step.step_type == "automated_action":
            action = db.get(AutomationAction, step.action_key) if step.action_key else None
            if not action or not action.enabled or step.action_key not in SAFE_HANDLERS:
                errors.append(f"Step {step.step_key} references an unavailable action")
            elif action.risk_level in {"high", "critical"} and not step.approval_required:
                errors.append(f"Step {step.step_key} must require approval")
        compensation_key = getattr(step, "compensation_action_key", None)
        if compensation_key:
            compensation = db.get(AutomationAction, compensation_key)
            if not compensation or not compensation.enabled or compensation_key not in SAFE_HANDLERS:
                errors.append(f"Step {step.step_key} references an unavailable compensation action")
        if step.evidence_required and not step.verification_required:
            warnings.append(f"Step {step.step_key} captures evidence without explicit verification")
    for name in (
        "scope", "prerequisites", "activation_criteria", "escalation_policy",
        "communication_plan", "evidence_requirements", "verification_requirements",
        "recovery_criteria", "closure_criteria", "post_incident_requirements",
    ):
        raw = getattr(version, name) or "{}"
        try:
            value = json.loads(raw)
            _safe_structure(value)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            errors.append(f"{name}: {exc}")
    required_roles = set()
    if playbook.requires_incident_commander:
        required_roles.add("incident_commander")
    if playbook.requires_technical_lead:
        required_roles.add("technical_lead")
    if playbook.requires_communications_lead:
        required_roles.add("communications_lead")
    owners = {step.owner_role for step in steps if step.owner_role}
    missing = sorted(required_roles - owners)
    if missing:
        warnings.append("No explicitly owned step for roles: " + ", ".join(missing))
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def version_checksum(version, steps):
    payload = {
        "version": version.version_number,
        "definitions": {
            key: getattr(version, key)
            for key in (
                "scope", "prerequisites", "activation_criteria", "escalation_policy",
                "communication_plan", "evidence_requirements", "verification_requirements",
                "recovery_criteria", "closure_criteria", "post_incident_requirements",
            )
        },
        "steps": [
            {
                "key": step.step_key, "phase": step.phase, "type": step.step_type,
                "order": step.sequence_order, "action": step.action_key,
                "compensation_action": getattr(step, "compensation_action_key", None),
                "maximum_retries": getattr(step, "maximum_retries", 1),
                "approval": step.approval_required, "evidence": step.evidence_required,
                "verification": step.verification_required,
            }
            for step in sorted(steps, key=lambda item: (item.sequence_order, item.step_key))
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    if len(encoded) > 1_000_000:
        raise ValueError("Playbook definition exceeds the one-megabyte limit")
    return hashlib.sha256(encoded).hexdigest()
