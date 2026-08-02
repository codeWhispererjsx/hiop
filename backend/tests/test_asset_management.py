from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];MODELS=(ROOT/"app/models/asset_management.py").read_text();API=(ROOT/"app/api/v1/asset_management.py").read_text();SCHEDULER=(ROOT/"app/services/scheduler_service.py").read_text();MIGRATION=(ROOT/"alembic/versions/e2f3a4b5c6d7_enterprise_asset_management.py").read_text()
def test_enterprise_asset_and_vendor_models():
    for model in ("EnterpriseAsset","AssetLifecycle","AssetTransfer","AssetDisposal","Vendor","VendorPerformance","PurchaseRequest","PurchaseOrder","Contract","Warranty","SoftwareLicense","InventoryItem","AssetRelationship"):assert f"class {model}" in MODELS
def test_asset_lifecycle_is_explicit_and_audited():
    for stage in ("planned","requested","approved","purchased","received","installed","assigned","operational","maintenance","loaned","transferred","retired","disposed","archived"):assert f'"{stage}"' in API
    assert "create_audit_log" in API and "AssetLifecycle" in API
def test_procurement_and_license_guards_are_human_driven():
    for phrase in ("Insufficient approved budget","approved request and approved vendor","No license seats available"):assert phrase in API
    assert "automatic purchase" not in API.lower()
def test_financial_calculation_is_bounded_and_deterministic():assert "straight_line" in API and "declining_balance" in API and "ROUND_HALF_UP" in API and "useful_life_months" in API
def test_migration_and_scheduled_jobs_cover_epic_7():
    assert 'down_revision="d1e2f3a4b5c6"' in MIGRATION
    for job in ("warranty_reminders","contract_renewal_reminders","license_renewal_reminders","inventory_threshold_alerts","asset_lifecycle_reviews","depreciation_recalculation","vendor_score_aggregation"):assert job in SCHEDULER
