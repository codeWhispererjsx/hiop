from pathlib import Path
import pytest
from app.models.asset_intelligence import ManagedAsset
from app.models.asset_management import Vendor, VendorContact
from app.models.procurement import AssetProcurement
from app.schemas.vendor_management import VendorContactCreate, VendorCreate

def test_vendor_and_contact_validation():
    row=VendorCreate(name="ABC Technologies",vendor_code=" abc ",vendor_type="supplier",products_services=["Hardware","Hardware","POS support"])
    assert row.vendor_code=="ABC" and row.products_services==["Hardware","POS support"]
    contact=VendorContactCreate(name="Jane Smith",role="Technical Support",email="jane@example.com",primary=True)
    assert contact.primary and contact.email=="jane@example.com"
    with pytest.raises(ValueError):VendorCreate(name="ABC",vendor_type="accounting")

def test_v4d_relationships_use_existing_asset_and_procurement_tables():
    assert "vendor_id" in ManagedAsset.__table__.columns
    assert "vendor_id" in AssetProcurement.__table__.columns
    assert Vendor.__tablename__=="vendors" and VendorContact.__tablename__=="vendor_contacts"
    assert Vendor.__table__.columns.organization_id.nullable is False

def test_v4d_routes_are_tenant_and_role_protected():
    source=Path(__file__).parents[1].joinpath("app/api/v1/vendors.py").read_text(encoding="utf-8")
    assert "organization_context" in source
    assert 'require_roles(["platformadmin","admin","technician","viewer"])' in source
    assert 'require_roles(["admin"])' in source
    for route in ('/{vendor_id}/contacts','/{vendor_id}/assets','/{vendor_id}/procurement','/{vendor_id}/deactivate'):assert route in source

def test_v4d_migration_is_additive_and_preserves_existing_data():
    source=Path(__file__).parents[1].joinpath("alembic/versions/v4d8e9f0a1b2_vendor_management.py").read_text(encoding="utf-8").lower()
    assert "add_column(\"managed_assets\"" in source and "add_column(\"asset_procurements\"" in source
    for forbidden in ("drop_table(\"managed_assets\"","delete from managed_assets","delete from asset_procurements","drop_table(\"vendors\""):assert forbidden not in source
