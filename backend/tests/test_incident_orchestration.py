import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.incidents import router
from app.models.incidents import (
    IncidentCauseAssessment, IncidentChecklistItem, IncidentCommunication,
    IncidentCommunicationTemplate, IncidentDecision, IncidentEscalationRule,
    IncidentEvidence, IncidentFollowUpAction, IncidentImpactAssessment,
    IncidentPlaybookRun, IncidentPlaybookStepRun,
    IncidentRemediationRecommendation, IncidentResponseTarget,
    OperationalIncident, OperationalPlaybook, OperationalPlaybookStep,
    OperationalPlaybookVersion, PostIncidentReview,
)
from app.services.incident_communication_service import render_template
from app.services.incident_orchestration_service import TRANSITIONS, recovery_readiness, transition
from app.services.incident_playbook_selection_service import SEVERITY
from app.services.incident_playbook_validation_service import validate_playbook, version_checksum
from app.services.incident_event_service import EVENT_INCIDENT_TYPES
from app.services.scheduler_service import INCIDENT_JOB_INTERVALS, incident_job_id


def test_complete_incident_domain_models_exist():
    expected = {
        OperationalIncident: "operational_incidents",
        OperationalPlaybook: "operational_playbooks",
        OperationalPlaybookVersion: "operational_playbook_versions",
        OperationalPlaybookStep: "operational_playbook_steps",
        IncidentPlaybookRun: "incident_playbook_runs",
        IncidentPlaybookStepRun: "incident_playbook_step_runs",
        IncidentChecklistItem: "incident_checklist_items",
        IncidentEvidence: "incident_evidence",
        IncidentDecision: "incident_decisions",
        IncidentCommunication: "incident_communications",
        IncidentEscalationRule: "incident_escalation_rules",
        IncidentResponseTarget: "incident_response_targets",
        IncidentImpactAssessment: "incident_impact_assessments",
        IncidentRemediationRecommendation: "incident_remediation_recommendations",
        IncidentCauseAssessment: "incident_cause_assessments",
        PostIncidentReview: "post_incident_reviews",
        IncidentFollowUpAction: "incident_follow_up_actions",
    }
    assert {model.__tablename__ for model in expected} == set(expected.values())


def test_incident_status_graph_is_controlled_and_reopen_is_explicit():
    assert "acknowledged" in TRANSITIONS["declared"]
    assert "closed" not in TRANSITIONS["declared"]
    assert TRANSITIONS["closed"] == {"investigating"}
    assert "duplicate" in TRANSITIONS["detected"]


def test_transition_rejects_invalid_mutation_without_database_access():
    incident = SimpleNamespace(id="i", property_id="p", status="declared")
    with pytest.raises(HTTPException, match="Invalid incident transition"):
        transition(None, incident, "closed", "operator", "unsafe jump")


def test_communication_template_allows_only_allowlisted_fields():
    template = SimpleNamespace(
        allowed_fields=json.dumps(["incident_number", "title"]),
        subject_template="{{incident_number}} — {{title}}",
        body_template="Status update for {{title}}",
    )
    incident = SimpleNamespace(incident_number="INC-1", title="Switch outage", status="declared")
    rendered = render_template(template, incident)
    assert rendered["subject"] == "INC-1 — Switch outage"
    template.body_template = "{{secret}}"
    with pytest.raises(ValueError, match="disallowed"):
        render_template(template, incident)


class FakeDB:
    def __init__(self, actions=None):
        self.actions = actions or {}
    def get(self, model, key):
        return self.actions.get(key)


def test_playbook_validation_blocks_unregistered_actions_and_calculates_stable_checksum():
    playbook = SimpleNamespace(
        requires_incident_commander=False,
        requires_technical_lead=False,
        requires_communications_lead=False,
    )
    version = SimpleNamespace(
        version_number=1, scope="{}", prerequisites="[]", activation_criteria="{}",
        escalation_policy="{}", communication_plan="{}", evidence_requirements="[]",
        verification_requirements="[]", recovery_criteria="[]", closure_criteria="[]",
        post_incident_requirements="{}",
    )
    step = SimpleNamespace(
        step_key="scan", phase="investigation", step_type="automated_action",
        action_key="unsafe", approval_required=False, evidence_required=False,
        verification_required=False, owner_role="technical_lead", sequence_order=1,
        compensation_action_key=None, maximum_retries=1,
    )
    result = validate_playbook(FakeDB(), playbook, version, [step])
    assert result["valid"] is False
    assert "unavailable action" in result["errors"][0]
    step.step_type, step.action_key = "human_task", None
    first = version_checksum(version, [step])
    assert first == version_checksum(version, [step])
    assert len(first) == 64


def test_playbook_validation_blocks_executable_definition_fields():
    playbook = SimpleNamespace(requires_incident_commander=False, requires_technical_lead=False, requires_communications_lead=False)
    version = SimpleNamespace(
        version_number=1, scope='{"script":"rm"}', prerequisites="[]", activation_criteria="{}",
        escalation_policy="{}", communication_plan="{}", evidence_requirements="[]",
        verification_requirements="[]", recovery_criteria="[]", closure_criteria="[]",
        post_incident_requirements="{}",
    )
    step = SimpleNamespace(step_key="review", phase="triage", step_type="human_task", action_key=None, approval_required=False, evidence_required=False, verification_required=False, owner_role="technical_lead", sequence_order=1, compensation_action_key=None, maximum_retries=1)
    result = validate_playbook(FakeDB(), playbook, version, [step])
    assert result["valid"] is False
    assert any("prohibited" in error for error in result["errors"])


def test_scheduler_job_ids_are_stable_and_jobs_are_separate():
    assert incident_job_id("sla_evaluation") == "incident_sla_evaluation"
    assert {"sla_evaluation", "overdue_tasks", "escalations", "communication_reminders", "post_incident_reminders", "follow_up_reminders", "retention_cleanup"}.issubset(INCIDENT_JOB_INTERVALS)
    with pytest.raises(ValueError):
        incident_job_id("arbitrary")


def test_internal_event_incident_mapping_is_fixed_and_human_pending():
    assert EVENT_INCIDENT_TYPES["critical_alert_created"] == "service_degradation"
    assert EVENT_INCIDENT_TYPES["device_offline"] == "device_failure"
    assert "public_webhook" not in EVENT_INCIDENT_TYPES


def test_incident_routes_cover_command_workspace_and_no_public_webhooks():
    paths = {route.path for route in router.routes if getattr(route, "path", None)}
    expected = {
        "/incidents", "/incidents/similar", "/incidents/{incident_id}",
        "/incidents/{incident_id}/acknowledge", "/incidents/{incident_id}/tasks",
        "/incidents/{incident_id}/checklists", "/incidents/{incident_id}/evidence",
        "/incidents/{incident_id}/communications/preview",
        "/incidents/{incident_id}/communications/send",
        "/incidents/playbooks", "/incidents/playbooks/{playbook_id}/versions",
        "/incidents/playbook-versions/{version_id}/steps",
        "/incidents/playbook-runs/{run_id}/retry-step",
        "/incidents/playbook-runs/{run_id}/compensate-step",
        "/incidents/playbook-runs/{run_id}/steps/{step_run_id}/complete",
        "/incidents/{incident_id}/recovery-readiness",
        "/incidents/{incident_id}/verify-recovery",
        "/incidents/{incident_id}/post-incident-review",
        "/incidents/{incident_id}/follow-up-actions",
        "/incidents/{incident_id}/evidence-bundle",
        "/incidents/reports/summary",
    }
    assert expected.issubset(paths)
    assert not any("webhook" in path for path in paths)


def test_incident_enums_keep_unknown_explicit_and_severity_order_explainable():
    assert OperationalIncident.__table__.c.guest_impact_level.default.arg == "unknown"
    assert OperationalIncident.__table__.c.life_safety_impact_level.default.arg == "unknown"
    assert SEVERITY["critical"] > SEVERITY["high"] > SEVERITY["medium"]


def test_playbook_step_retry_and_compensation_are_bounded_and_versioned():
    table = OperationalPlaybookStep.__table__
    assert table.c.maximum_retries.default.arg == 1
    assert table.c.maximum_retries.server_default.arg == "1"
    assert table.c.compensation_action_key.foreign_keys
