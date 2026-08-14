from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.models.hospitality_operations import HospitalityTechnologyService
from app.models.incidents import OperationalIncident
from app.models.service_management import IncidentAssetRelationship, ServiceAssetRelationship
from app.schemas.service_management import OperationalIncidentWrite, ServiceWrite, TransitionWrite
from app.services import service_management_service as service


def test_v4e_models_extend_existing_incident_and_service_records():
    assert OperationalIncident.__tablename__ == "operational_incidents"
    assert HospitalityTechnologyService.__tablename__ == "hospitality_technology_services"
    for field in ("asset_id", "category", "assigned_team", "assigned_technician_id", "resolution_summary", "closure_notes"):
        assert field in OperationalIncident.__table__.columns
    assert ServiceAssetRelationship.__tablename__ == "service_asset_relationships"
    assert IncidentAssetRelationship.__tablename__ == "incident_asset_relationships"


def test_v4e_schema_rejects_invalid_service_and_incident_values():
    with pytest.raises(ValueError):
        ServiceWrite(property_id="00000000-0000-0000-0000-000000000001", name="POS", code="POS", status="down")
    with pytest.raises(ValueError):
        OperationalIncidentWrite(property_id="00000000-0000-0000-0000-000000000001", title="Test issue", priority="P1")
    row = OperationalIncidentWrite(property_id="00000000-0000-0000-0000-000000000001", title="POS service unavailable", category="pos", priority="critical")
    assert row.category == "pos" and row.priority == "critical"


def test_resolution_requires_summary(monkeypatch):
    db = MagicMock()
    row = SimpleNamespace(status="in_progress", id="incident", updated_by=None, resolved_at=None, resolution_summary=None, root_cause_notes=None, follow_up_notes=None, closed_at=None, closure_notes=None)
    actor = SimpleNamespace(username="technician")
    monkeypatch.setattr(service, "timeline", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "audit", lambda *args, **kwargs: None)
    with pytest.raises(HTTPException) as exc:
        service.transition_incident(db, row, "resolved", TransitionWrite(), actor)
    assert exc.value.status_code == 422


def test_resolve_close_and_reopen_preserve_history(monkeypatch):
    db = MagicMock()
    entries = []
    row = SimpleNamespace(status="in_progress", id="incident", updated_by=None, resolved_at=None, resolution_summary=None, root_cause_notes=None, follow_up_notes=None, closed_at=None, closure_notes=None)
    actor = SimpleNamespace(username="admin")
    monkeypatch.setattr(service, "timeline", lambda _db, _row, _actor, kind, title, summary=None: entries.append((kind, title, summary)))
    monkeypatch.setattr(service, "audit", lambda *args, **kwargs: None)
    service.transition_incident(db, row, "resolved", TransitionWrite(resolution_summary="Restored switch power"), actor)
    assert row.status == "resolved" and row.resolution_summary == "Restored switch power"
    service.transition_incident(db, row, "closed", TransitionWrite(closure_notes="Operations confirmed restoration"), actor)
    assert row.status == "closed" and row.closed_at
    service.transition_incident(db, row, "in_progress", TransitionWrite(reason="Issue recurred"), actor)
    assert row.status == "in_progress" and row.resolved_at is None and row.closed_at is None
    assert len(entries) == 3


def test_v4e_routes_enforce_roles_and_tenant_context():
    source = Path(__file__).parents[1].joinpath("app/api/v1/service_management.py").read_text(encoding="utf-8")
    assert "organization_context" in source
    assert 'require_roles(["platformadmin", "admin", "technician", "viewer"])' in source
    assert 'require_roles(["admin", "technician"])' in source
    assert "Technicians may update only" in source
    for route in ("/services", "/incidents", "/transition/{target}", "/notes", "/assets/{asset_id}/incidents"):
        assert route in source


def test_v4e_migration_is_additive():
    source = Path(__file__).parents[1].joinpath("alembic/versions/v4e9f0a1b2c3_service_incident_management.py").read_text(encoding="utf-8").lower()
    assert 'create_table("service_asset_relationships"' in source
    assert 'create_table("incident_asset_relationships"' in source
    assert 'add_column("operational_incidents"' in source
    for forbidden in ('drop_table("operational_incidents"', "delete from operational_incidents", "delete from managed_assets", "drop_table(\"managed_assets\""):
        assert forbidden not in source
