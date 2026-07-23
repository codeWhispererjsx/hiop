import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.main import app
from app.models.inventory_import import (
    ImportExecutionResult,
    ImportExecutionStatus,
    ImportSession,
    ImportSessionStatus,
    ImportedDevice,
)
from app.services.import_finalization_service import (
    FinalizationConflictError,
    FinalizationValidationError,
    ImportFinalizationService,
)
from app.services.settings_service import read_import_settings


class FinalImportPersistenceTests(unittest.TestCase):
    def test_execution_result_and_session_contract(self):
        result_columns = set(ImportExecutionResult.__table__.columns.keys())
        self.assertTrue({"import_session_id", "imported_device_id", "action", "status", "target_device_id", "plan", "before_snapshot", "after_snapshot", "retry_count", "rolled_back_at"}.issubset(result_columns))
        session_columns = set(ImportSession.__table__.columns.keys())
        self.assertTrue({"execution_summary", "plan_version", "plan_locked_at", "finalized_by", "finalization_started_at", "finalization_completed_at", "rollback_by", "rollback_at", "retry_count"}.issubset(session_columns))
        self.assertEqual({item.value for item in ImportExecutionStatus}, {"pending", "running", "completed", "failed", "skipped", "rolled_back", "rollback_failed"})

    def test_migration_extends_matching_head(self):
        path = Path(__file__).parents[1] / "alembic" / "versions" / "d4f2a7c8e901_add_final_import_execution.py"
        spec = importlib.util.spec_from_file_location("final_import_migration", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.revision, "d4f2a7c8e901")
        self.assertEqual(module.down_revision, "91b7d3e5a204")

    def test_final_import_settings_are_typed_and_safe(self):
        db = MagicMock()
        db.query.return_value.all.return_value = []
        values = read_import_settings(db)
        self.assertEqual(values["final_import_batch_size"], 100)
        self.assertEqual(values["final_import_retry_limit"], 3)
        self.assertFalse(values["allow_reviewed_field_overwrite"])


class FinalImportSafetyTests(unittest.TestCase):
    def test_locked_plan_rejects_disposition_change(self):
        session_id = uuid4()
        session = ImportSession(id=session_id, status=ImportSessionStatus.READY, plan_locked_at=SimpleNamespace())
        service = ImportFinalizationService(MagicMock())
        service._session = lambda *_args, **_kwargs: session
        with self.assertRaises(FinalizationConflictError):
            service.set_disposition(session_id, uuid4(), "skip", [], [], SimpleNamespace(username="admin"))

    def test_create_plan_requires_normal_device_fields(self):
        service = ImportFinalizationService(MagicMock())
        session_id = uuid4()
        session = ImportSession(id=session_id, import_type="device_inventory", status=ImportSessionStatus.PARTIAL, matching_state="completed", plan_version=0)
        row = ImportedDevice(id=uuid4(), import_session_id=session_id, source_row_number=2, asset_tag="A-1", hostname="desk-01", final_disposition="create_new", validation_status="valid")
        service._session = lambda *_args, **_kwargs: session
        service._rows = lambda _id: [row]
        service._location = lambda _row: None
        readiness = service.readiness(session_id)
        self.assertFalse(readiness["ready"])
        self.assertIn("invalid_device", {item["code"] for item in readiness["blocking_issues"]})

    def test_idempotent_completed_request_returns_existing_result(self):
        session_id = uuid4()
        session = ImportSession(id=session_id, status=ImportSessionStatus.COMPLETED, finalization_completed_at=SimpleNamespace(), execution_summary={"idempotency_key": "same-key-1234"})
        service = ImportFinalizationService(MagicMock())
        service._session = lambda *_args, **_kwargs: session
        service.results = lambda _id: {"status": "completed"}
        self.assertEqual(service.finalize(session_id, SimpleNamespace(id="u1", username="admin"), plan_version=1, idempotency_key="same-key-1234", confirmed=True)["status"], "completed")

    def test_confirmation_is_required(self):
        service = ImportFinalizationService(MagicMock())
        with self.assertRaises(FinalizationValidationError):
            service.finalize(uuid4(), SimpleNamespace(id="u1", username="admin"), plan_version=1, idempotency_key="unique-key-123", confirmed=False)


class FinalImportApiTests(unittest.TestCase):
    def test_routes_exist_and_mutations_are_secured(self):
        paths = app.openapi()["paths"]
        required = {
            "/api/v1/imports/{session_id}/readiness",
            "/api/v1/imports/{session_id}/execution-plan",
            "/api/v1/imports/{session_id}/finalize",
            "/api/v1/imports/{session_id}/results",
            "/api/v1/imports/{session_id}/rollback-preview",
            "/api/v1/imports/{session_id}/rollback",
            "/api/v1/imports/{session_id}/retry-failed",
        }
        self.assertTrue(required.issubset(paths))
        for path in ("/api/v1/imports/{session_id}/finalize", "/api/v1/imports/{session_id}/rollback", "/api/v1/imports/{session_id}/retry-failed"):
            self.assertIn("security", paths[path]["post"])


if __name__ == "__main__":
    unittest.main()
