from pathlib import Path

from app.api.v1 import changes
from app.models.change_management import ChangeRelationship, ChangeRequest, ChangeTimelineEvent


def source(): return Path(__file__).parents[1].joinpath("app/api/v1/changes.py").read_text(encoding="utf-8")


def test_v4g_reuses_core_change_schema():
    assert ChangeRequest.__tablename__ == "change_requests"
    assert ChangeRelationship.__tablename__ == "change_relationships"
    assert ChangeTimelineEvent.__tablename__ == "change_timeline_events"
    for field in ("organization_id", "change_type", "risk_explanation", "actual_start", "actual_end", "outcome", "rollback_reason"):
        assert field in ChangeRequest.__table__.columns


def test_change_vocabularies_are_small_and_explicit():
    assert changes.TYPES == {"standard", "normal", "emergency"}
    assert changes.LEVELS == {"low", "medium", "high", "critical"}
    assert changes.OUTCOMES == {"successful", "failed", "rolled_back", "cancelled"}
    assert {"draft", "under_review", "approved", "scheduled", "in_progress", "rolled_back", "closed"} <= changes.STATUSES


def test_change_validation_and_self_approval_guards_exist():
    text = source()
    assert "High and critical risk changes require a rollback plan" in text
    assert "Requester cannot self-approve a high or critical risk change" in text
    assert "Validation outcome is required" in text
    assert "Outcome and closure notes are required" in text


def test_change_is_tenant_and_role_scoped():
    text = source()
    assert "organization_context" in text
    assert 'require_roles(["platformadmin", "admin", "technician", "viewer"])' in text
    assert 'operator = require_roles(["admin"])' in text
    assert "does not belong to this organization" in text


def test_relationships_and_existing_impact_are_reused():
    text = source()
    for kind in ("asset", "device", "service", "problem", "incident", "vendor", "location"):
        assert f'"{kind}"' in text
    assert "IncidentImpactAssessment" in text
    assert '"source": "existing_incident_impact"' in text


def test_schedule_conflict_and_maintenance_context_are_read_only():
    text = source()
    assert "Potential scheduling" not in text  # presentation belongs to the UI
    assert "MaintenanceWindow" in text
    assert "scheduled_start < row.scheduled_end" in text
    for forbidden in ("subprocess", "paramiko", "netmiko", "execute_command", "apply_configuration"):
        assert forbidden not in text


def test_v4g_migration_is_additive():
    text = Path(__file__).parents[1].joinpath("alembic/versions/v4g0a1b2c3d4_change_management.py").read_text(encoding="utf-8").lower()
    assert 'add_column("change_requests"' in text
    assert 'create_table("change_timeline_events"' in text
    for forbidden in ('drop_table("change_requests"', "delete from change_requests", 'drop_table("problems"'):
        assert forbidden not in text
