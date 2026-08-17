from pathlib import Path

from app.models.asset_intelligence import ManagedAsset
from app.models.hierarchy import Building, Department, Floor, Organization, Room
from app.models.hospitality_operations import HospitalityTechnologyService
from app.models.local_agent import LocalAgentRegistration
from app.models.user import User


def test_v4e5_reuses_central_organization_department_and_location_models():
    assert Organization.__tablename__ == "organizations"
    assert Department.__tablename__ == "departments"
    assert {Building.__tablename__, Floor.__tablename__, Room.__tablename__} == {"buildings", "floors", "rooms"}
    for model in (Department, Building, Floor, Room): assert "organization_id" in model.__table__.columns


def test_v4e5_assignments_extend_existing_entities():
    for field in ("department_id", "primary_location_type", "primary_location_id"): assert field in User.__table__.columns
    for field in ("department_id", "location_type", "location_id"): assert field in HospitalityTechnologyService.__table__.columns
    assert "department_id" in ManagedAsset.__table__.columns and "room_id" in ManagedAsset.__table__.columns


def test_agent_foundation_is_secure_and_organization_bound():
    assert LocalAgentRegistration.__tablename__ == "local_agent_registrations"
    assert "organization_id" in LocalAgentRegistration.__table__.columns
    source = Path(__file__).parents[1].joinpath("app/models/local_agent.py").read_text(encoding="utf-8").lower()
    assert "credential_hash" in source and "property_id" in source
    for unsafe in ("execute_command", "remote_shell", "auto_update"): assert unsafe not in source


def test_structure_api_enforces_roles_and_tenant_context():
    source = Path(__file__).parents[1].joinpath("app/api/v1/organization_structure.py").read_text(encoding="utf-8")
    assert "organization_context" in source
    assert 'require_roles(["platformadmin", "admin", "technician", "viewer"])' in source
    assert 'require_roles(["admin"])' in source
    for route in ("/organization", "/departments", "/locations", "/assignments/{entity_type}/{entity_id}", "/agents"):
        assert route in source
    assert '"active_directory_ou"' in source and '"hostname_rule"' in source


def test_legacy_hierarchy_api_is_now_tenant_scoped():
    source = Path(__file__).parents[1].joinpath("app/hierarchy/routes.py").read_text(encoding="utf-8")
    assert source.count("organization_context") >= 5
    assert "Property.organization_id == organization_id" in source


def test_v4e5_migration_is_additive():
    source = Path(__file__).parents[1].joinpath("alembic/versions/v4e5a0b1c2d3_organization_deployment_foundation.py").read_text(encoding="utf-8").lower()
    assert 'create_table("local_agent_registrations"' in source
    assert 'add_column("users"' in source
    for forbidden in ("drop_table(\"managed_assets\"", "drop_table(\"users\"", "delete from managed_assets", "delete from devices"):
        assert forbidden not in source
