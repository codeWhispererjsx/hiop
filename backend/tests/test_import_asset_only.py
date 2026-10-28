from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy.sql.elements import TextClause

from app.models.asset_intelligence import AssetLifecycleEvent, ManagedAsset
from app.models.hierarchy import Department
from app.models.inventory_import import ImportSessionStatus, ImportValidationStatus
from app.services import import_finalization_service as finalization
from app.services.import_validation import validate_row


class AssetImportDB:
    def __init__(self, organization_id, property_id):
        self.info = {"organization_id": organization_id}
        self.property_id = property_id
        self.added = []

    def scalar(self, statement):
        if isinstance(statement, TextClause):
            return 41
        if "FROM departments" in str(statement):
            return None
        return self.property_id

    def add(self, row):
        if isinstance(row, (Department, ManagedAsset)):
            row.id = uuid4()
        self.added.append(row)

    def flush(self):
        pass


def test_allocation_rows_stage_without_asset_tag_or_network_fields():
    normalized, errors, _ = validate_row(
        {
            "System Name": "LAPTOP-01",
            "Staff Assigned": "Alex Example",
            "Date of Deployment": "2024-03-05",
            "Item Serial Number": "SERIAL-01",
        },
        {
            "System Name": "hostname",
            "Staff Assigned": "business_owner",
            "Date of Deployment": "deployment_date",
            "Item Serial Number": "serial_number",
        },
    )

    assert errors == []
    assert normalized["asset_tag"] is None
    assert normalized["hostname"] == "laptop-01"
    assert normalized["business_owner"] == "Alex Example"
    assert normalized["deployment_date"] == "2024-03-05"
    assert normalized["ip_address"] is None
    assert normalized["mac_address"] is None


def test_managed_asset_finalization_preserves_fields_without_device_creation(monkeypatch):
    organization_id, property_id = uuid4(), uuid4()
    db = AssetImportDB(organization_id, property_id)
    service = finalization.ImportFinalizationService(db)
    session = SimpleNamespace(
        mapping_metadata={"tenant_property_id": str(property_id)}
    )
    monkeypatch.setattr(service, "_session", lambda _session_id: session)
    monkeypatch.setattr(finalization, "create_audit_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(finalization.DeviceIdentityService, "apply_managed_asset_rules", lambda *_args: None)

    row = SimpleNamespace(import_session_id=uuid4(), source_row_number=12)
    result = SimpleNamespace(
        plan={
            "values": {
                "hostname": "laptop-01",
                "asset_tag": None,
                "device_type": None,
                "brand": None,
                "vendor": None,
                "model": None,
                "serial_number": "SERIAL-01",
                "department_id": None,
                "department": "IT",
                "room_id": None,
                "location": None,
                "business_owner": "Alex Example",
                "deployment_date": "2024-03-05",
                "description": "Assigned laptop",
            }
        },
        after_snapshot={},
    )
    actor = SimpleNamespace(id=uuid4(), username="admin")

    asset = service._create_asset(result, row, actor)

    assert asset.asset_number == "HIOP-000041"
    assert asset.name == "laptop-01"
    assert asset.device_id is None
    assert asset.asset_tag is None
    assert asset.serial_number == "SERIAL-01"
    assert asset.business_owner == "Alex Example"
    assert asset.deployment_date == date(2024, 3, 5)
    assert asset.department_id is not None
    assert result.plan["target_asset_id"] == str(asset.id)
    assert any(isinstance(item, Department) and item.name == "IT" for item in db.added)
    assert any(isinstance(item, AssetLifecycleEvent) for item in db.added)
    assert all(not isinstance(item, finalization.Device) for item in db.added)


def test_asset_only_readiness_does_not_require_network_device_fields(monkeypatch):
    organization_id, property_id, session_id = uuid4(), uuid4(), uuid4()
    db = AssetImportDB(organization_id, property_id)
    service = finalization.ImportFinalizationService(db)
    session = SimpleNamespace(
        id=session_id,
        import_type="device_inventory",
        matching_state="completed",
        status=ImportSessionStatus.REVIEW_REQUIRED,
        finalization_completed_at=None,
        plan_version=2,
        mapping_metadata={"tenant_property_id": str(property_id)},
    )
    row = SimpleNamespace(
        id=uuid4(),
        import_session_id=session_id,
        source_row_number=3,
        validation_status=ImportValidationStatus.VALID,
        final_disposition="create_asset",
        resolution_action=None,
        linked_device_id=None,
        linked_discovery_id=None,
        asset_tag=None,
        hostname="laptop-01",
        device_type=None,
        brand=None,
        vendor=None,
        model=None,
        serial_number="SERIAL-01",
        department_name=None,
        room_name=None,
        ip_address=None,
        mac_address=None,
        inventory_status=None,
        normalized_data={"business_owner": "Alex Example"},
        notes=None,
        approved_changes={},
        resolved_by=None,
        resolved_at=None,
    )
    monkeypatch.setattr(service, "_session", lambda _session_id: session)
    monkeypatch.setattr(service, "_rows", lambda _session_id: [row])
    def scalar(statement):
        query = str(statement).lower()
        if "import_location_suggestions" in query:
            return None
        if "count(" in query:
            return 0
        return property_id

    db.scalar = scalar
    db.get = lambda _model, _identifier: None

    readiness = service.readiness(session_id)

    assert readiness["ready"]
    assert readiness["blocking_issues"] == []
    assert readiness["plans"][0]["disposition"] == "create_asset"


def test_invalid_deployment_date_is_reported_during_staging():
    normalized, errors, _ = validate_row(
        {"System Name": "LAPTOP-01", "Date of Deployment": "not-a-date"},
        {"System Name": "hostname", "Date of Deployment": "deployment_date"},
    )

    assert normalized["deployment_date"] is None
    assert any(error["field"] == "deployment_date" for error in errors)
