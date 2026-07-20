import importlib.util
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from sqlalchemy import CheckConstraint

from app.models.inventory_import import (
    ImportedDevice,
    ImportSession,
    ImportSessionStatus,
    ImportValidationStatus,
)
from app.repositories.import_repository import ImportedDeviceRepository, ImportSessionRepository
from app.services.import_service import ImportService
from app.services.import_validation import (
    AssetTagValidator,
    BuildingValidator,
    DepartmentValidator,
    FloorValidator,
    HostnameValidator,
    IPAddressValidator,
    MACAddressValidator,
    RoomValidator,
)
from app.services.settings_service import read_import_settings


MIGRATION = Path(__file__).parents[1] / "alembic" / "versions" / "7f4e2c1a9d30_add_inventory_import_foundation.py"


class ImportModelTests(unittest.TestCase):
    def test_enum_contracts(self):
        self.assertEqual({item.value for item in ImportSessionStatus}, {"uploaded", "validating", "processing", "completed", "partial", "failed"})
        self.assertEqual({item.value for item in ImportValidationStatus}, {"pending", "valid", "warning", "duplicate", "invalid"})

    def test_session_and_device_columns_match_contract(self):
        self.assertEqual(set(ImportSession.__table__.columns.keys()), {
            "id", "filename", "original_filename", "import_type", "file_format", "uploaded_by", "uploaded_at",
            "processing_started_at", "processing_completed_at", "status", "total_rows", "processed_rows",
            "successful_rows", "failed_rows", "duplicate_rows", "matched_rows", "skipped_rows", "error_summary",
            "mapping_metadata", "selected_worksheet", "matching_state", "match_summary", "created_at", "updated_at",
        })
        self.assertEqual(set(ImportedDevice.__table__.columns.keys()), {
            "id", "import_session_id", "asset_tag", "hostname", "ip_address", "mac_address", "department_name",
            "building_name", "floor_name", "room_name", "network_zone", "vendor", "brand", "model",
            "serial_number", "inventory_status", "notes", "raw_data", "normalized_data", "errors", "warnings",
            "source_row_number", "resolution_action", "linked_device_id", "linked_discovery_id", "resolved_by",
            "resolved_at", "validation_status", "imported_at", "created_at", "updated_at",
        })

    def test_relationships_constraints_and_indexes_exist(self):
        self.assertEqual(set(ImportSession.__mapper__.relationships.keys()), {"uploader", "imported_devices", "match_candidates"})
        self.assertEqual(set(ImportedDevice.__mapper__.relationships.keys()), {"import_session", "match_candidates", "location_suggestion", "linked_device", "linked_discovery", "resolver"})
        constraints = {item.name for item in ImportSession.__table__.constraints if isinstance(item, CheckConstraint)}
        self.assertIn("ck_import_sessions_processed_within_total", constraints)
        indexes = {item.name: item for item in ImportedDevice.__table__.indexes}
        required = {"ix_imported_devices_asset_tag", "ix_imported_devices_hostname", "ix_imported_devices_ip_address", "ix_imported_devices_mac_address", "ix_imported_devices_import_session_id"}
        self.assertTrue(required.issubset(indexes))
        self.assertTrue(indexes["uq_imported_devices_session_source_row"].unique)

    def test_repositories_are_persistence_only(self):
        db = MagicMock()
        self.assertIsInstance(ImportSessionRepository(db), ImportSessionRepository)
        self.assertIsInstance(ImportedDeviceRepository(db), ImportedDeviceRepository)

    def test_validator_interfaces_are_available(self):
        validators = (IPAddressValidator, MACAddressValidator, AssetTagValidator, HostnameValidator, DepartmentValidator, BuildingValidator, FloorValidator, RoomValidator)
        self.assertTrue(all(callable(getattr(validator, "validate")) for validator in validators))

    def test_import_settings_are_typed(self):
        db = MagicMock()
        db.query.return_value.all.return_value = []
        values = read_import_settings(db)
        self.assertEqual(values["supported_formats"], ["csv", "xlsx"])
        self.assertEqual(values["maximum_import_file_size"], 10485760)
        self.assertTrue(values["duplicate_matching_enabled"])


class ImportMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("import_foundation_migration", MIGRATION)
        cls.module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(cls.module)

    def test_revision_extends_discovery_head(self):
        self.assertEqual(self.module.revision, "7f4e2c1a9d30")
        self.assertEqual(self.module.down_revision, "c87d380fc50a")

    def test_upgrade_and_downgrade_order(self):
        with patch.object(self.module.op, "create_table") as create_table, patch.object(self.module.op, "create_index"):
            self.module.upgrade()
        self.assertEqual([item.args[0] for item in create_table.call_args_list], ["import_sessions", "imported_devices"])
        with patch.object(self.module.op, "drop_table") as drop_table:
            self.module.downgrade()
        self.assertEqual(drop_table.call_args_list, [call("imported_devices"), call("import_sessions")])


if __name__ == "__main__":
    unittest.main()
