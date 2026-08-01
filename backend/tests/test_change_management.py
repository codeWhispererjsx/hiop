from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.v1.change_management import ArtifactWrite, AttachmentWrite, ChangeWrite, WindowWrite, router
from app.main import app
from app.models import change_management as models
from app.services.change_management_service import CHANGE_TRANSITIONS, RISK_FACTORS, calculate_risk
from app.services.scheduler_service import CHANGE_JOB_INTERVALS, change_job_id


def test_epic_four_models_are_registered():
    names = {"ChangeRequest","ChangeType","ChangeCategory","ChangePriority","ChangeRisk","ChangeImpact","ChangeApproval","ChangeTask","ChangeComment","ChangeAttachment","ChangeRevision","CABMeeting","CABMember","CABDecision","CABVote","CABAgenda","CABAttendance","RiskAssessment","RiskFactor","MitigationPlan","BusinessImpact","TechnicalImpact","MaintenanceWindow","MaintenanceCalendar","MaintenanceApproval","MaintenanceConflict","ChangeExecution","ExecutionTask","ExecutionEvidence","ExecutionLog","RollbackExecution","Release","ReleasePackage","ReleaseVersion","ReleaseDeployment","ReleaseArtifact","ChangeCommunication","ChangeRelationship"}
    assert all(hasattr(models, name) for name in names)
    assert len({getattr(models, name).__tablename__ for name in names}) == len(names)


def test_rfc_lifecycle_requires_review_schedule_verification_and_close():
    assert CHANGE_TRANSITIONS["draft"] == {"submitted", "cancelled"}
    assert "approved" not in CHANGE_TRANSITIONS["draft"]
    assert CHANGE_TRANSITIONS["approved"] == {"scheduled", "cancelled"}
    assert CHANGE_TRANSITIONS["implemented"] == {"verified", "failed"}
    assert CHANGE_TRANSITIONS["closed"] == set()


@pytest.mark.parametrize("value,expected", [(0,"low"),(1,"low"),(2,"medium"),(3,"high"),(4,"critical"),(5,"critical")])
def test_deterministic_risk_scoring(value, expected):
    score, level = calculate_risk({name:value for name in RISK_FACTORS})
    assert score == value * 10
    assert level == expected


def test_risk_rejects_missing_unknown_or_unbounded_factors():
    with pytest.raises(HTTPException): calculate_risk({"guest_impact":1})
    factors = {name:1 for name in RISK_FACTORS}; factors["unknown"] = 1
    with pytest.raises(HTTPException): calculate_risk(factors)
    with pytest.raises(HTTPException): calculate_risk({name:6 for name in RISK_FACTORS})


def test_change_and_window_schemas_enforce_bounded_plans_and_dates():
    with pytest.raises(ValidationError): WindowWrite(name="Too long",window_type="standard",start_at="2026-01-02T00:00:00Z",end_at="2026-01-01T00:00:00Z")
    with pytest.raises(ValidationError): ChangeWrite(type_id="00000000-0000-0000-0000-000000000001",title="RFC",description="safe",business_justification="safe",technical_justification="safe",backout_plan="safe",validation_plan="safe",test_plan="safe",communication_plan="safe",implementation_plan="safe",scheduled_start="2026-01-01T00:00:00Z")


def test_attachment_metadata_blocks_traversal_and_oversize_payloads():
    AttachmentWrite(filename="evidence.pdf",media_type="application/pdf",size_bytes=10,storage_reference="changes/evidence.pdf",checksum_sha256="a"*64)
    with pytest.raises(ValidationError): AttachmentWrite(filename="bad",media_type="text/plain",size_bytes=10,storage_reference="../secret",checksum_sha256="a"*64)
    with pytest.raises(ValidationError): AttachmentWrite(filename="bad",media_type="text/plain",size_bytes=25_000_001,storage_reference="safe",checksum_sha256="a"*64)
    ArtifactWrite(package_id="00000000-0000-0000-0000-000000000001",filename="release.zip",media_type="application/zip",size_bytes=10,storage_reference="releases/release.zip",checksum_sha256="b"*64)
    with pytest.raises(ValidationError): ArtifactWrite(package_id="00000000-0000-0000-0000-000000000001",filename="release.zip",media_type="application/zip",size_bytes=10,storage_reference="../release.zip",checksum_sha256="b"*64)


def test_api_surface_covers_rfc_cab_risk_maintenance_execution_release_and_reports():
    paths = {route.path for route in router.routes}
    expected = {"/changes/dashboard","/changes","/changes/requests/{change_id}","/changes/requests/{change_id}/approvals","/changes/requests/{change_id}/attachments","/changes/requests/{change_id}/risk-assessments","/changes/cab/meetings","/changes/cab/meetings/{meeting_id}/changes/{change_id}/vote","/changes/maintenance/windows","/changes/maintenance/windows/{window_id}/conflicts","/changes/requests/{change_id}/executions","/changes/executions/{execution_id}/timeline","/changes/executions/{execution_id}/rollback","/changes/rollbacks/{rollback_id}/approve","/changes/releases","/changes/releases/{release_id}/artifacts","/changes/communications","/changes/reports/summary","/changes/reports/export","/changes/audit-history"}
    assert expected.issubset(paths)
    assert not any("execute-code" in path or "webhook" in path or "/ai/" in path for path in paths)


def test_scheduler_jobs_are_stable_separate_and_complete():
    expected = {"approval_reminders","upcoming_maintenance","missed_approvals","expired_rfc_cleanup","conflict_detection","release_reminders","risk_recalculation","calendar_synchronization"}
    assert set(CHANGE_JOB_INTERVALS) == expected
    assert change_job_id("approval_reminders") == "change_management_approval_reminders"
    with pytest.raises(ValueError): change_job_id("arbitrary")


def test_change_endpoints_require_authentication():
    client = TestClient(app)
    assert client.get("/api/v1/changes/dashboard").status_code == 401
    assert client.post("/api/v1/changes",json={}).status_code == 401


def test_migration_is_additive_seeded_and_reversible():
    text = Path("alembic/versions/b9c0d1e2f3a4_enterprise_change_management.py").read_text()
    assert 'down_revision = "a8b9c0d1e2f3"' in text
    assert "CHANGE_TYPES" in text and "Emergency Change" in text and "Hospitality Service Change" in text
    assert "reversed(TABLES)" in text
