from pathlib import Path

from app.api.v1 import property_management
from app.core import tenant
from app.dashboard import routes as dashboard_routes
from app.services import dashboard_service
from app.models.asset_intelligence import ManagedAsset
from app.models.hierarchy import Property
from app.models.local_agent import LocalAgentRegistration
from app.models.procurement import AssetProcurement
from app.models.property_access import UserPropertyAccess


def test_v4j_reuses_organization_property_and_access_foundation():
    assert Property.organization_id is not None
    assert UserPropertyAccess.property_id is not None
    assert ManagedAsset.property_id is not None
    assert AssetProcurement.property_id is not None
    assert LocalAgentRegistration.property_id is not None


def test_v4j_property_api_supports_management_health_access_and_comparison():
    source=Path(property_management.__file__).read_text(encoding="utf-8")
    for route in ['@router.get("")','@router.post(""','/context','/comparison','/{property_id}/access','/{property_id}/{action}']:
        assert route in source
    for metric in ["assets","devices","services","open_incidents","open_problems","upcoming_changes","critical_alerts","availability","health"]:
        assert f'"{metric}"' in source


def test_v4j_backend_property_boundary_is_explicit():
    source=Path(tenant.__file__).read_text(encoding="utf-8")
    assert "X-HIOP-Property-ID".lower().replace("-","_") in source.lower()
    assert "Property is outside your permitted scope" in source
    assert "Property.organization_id == organization_id" in source


def test_v4j_network_operations_enforce_property_context():
    api_root = Path(__file__).parents[1] / "app" / "api" / "v1"
    for module in ("monitoring_health.py", "alerts_events.py", "topology_v3a.py", "port_intelligence.py", "segmentation.py"):
        source = (api_root / module).read_text(encoding="utf-8")
        assert "property_context" in source, f"{module} must enforce the active property"
        assert "Depends(property_context)" in source

    tenant_source = Path(tenant.__file__).read_text(encoding="utf-8")
    assert 'if user.role in {"platformadmin", "admin"}' in tenant_source
    assert 'raise HTTPException(403, "No property access has been assigned")' in tenant_source
    assert 'raise HTTPException(400, "Select a property before opening operational data")' in tenant_source


def test_v4j_dashboard_and_discovery_are_tenant_scoped():
    dashboard_route_source = Path(dashboard_routes.__file__).read_text(encoding="utf-8")
    dashboard_service_source = Path(dashboard_service.__file__).read_text(encoding="utf-8")
    discovery_source = (Path(__file__).parents[1] / "app" / "api" / "v1" / "discovery_intelligence.py").read_text(encoding="utf-8")
    for source in (dashboard_route_source, discovery_source):
        assert "Depends(organization_context)" in source
        assert "Depends(property_context)" in source
    assert "Property.organization_id == organization_id" in dashboard_service_source
    assert "Property.organization_id==organization_id" in discovery_source
    assert 'Select a property before starting discovery' in discovery_source


def test_v4j_migration_is_additive_and_backfills_existing_data():
    migration=Path(__file__).parents[1]/"alembic"/"versions"/"v4j0a1b2c3d4_multi_property_foundation.py"
    source=migration.read_text(encoding="utf-8").lower()
    assert 'down_revision="v4h0a1b2c3d4"' in source
    assert "update managed_assets" in source and "update asset_procurements" in source
    assert "insert into user_property_access" in source
    assert "drop_table" not in source.split("def upgrade():",1)[1].split("def downgrade():",1)[0]


def test_v4j_does_not_introduce_v5_or_automation_scope():
    source=Path(property_management.__file__).read_text(encoding="utf-8").lower()
    for forbidden in ["licensing","predictive","aiops","remote command","automated remediation"]:
        assert forbidden not in source
