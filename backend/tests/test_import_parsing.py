import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from openpyxl import Workbook

from app.imports.columns import detect_mapping, validate_mapping
from app.imports.parsers import ImportFileError, detect_format, parse_file
from app.main import app
from app.models.device import Device
from app.models.inventory_import import ImportedDevice, ImportSession, ImportSessionStatus, ImportValidationStatus
from app.services.import_service import ImportConflictError, ImportService, STORAGE_ROOT
from app.services.import_service import ImportValidationError
from app.services.import_validation import validate_row


LIMITS = {"maximum_rows": 20, "maximum_worksheets": 5, "maximum_columns": 30, "maximum_cell_length": 4000, "preview_rows": 5, "import_batch_size": 2}


class FileSecurityTests(unittest.TestCase):
    def test_rejects_unsupported_empty_and_mismatched_files(self):
        with self.assertRaises(ImportFileError): detect_format("payload.exe", "application/octet-stream", b"MZdata")
        with self.assertRaises(ImportFileError): detect_format("empty.csv", "text/csv", b"")
        with self.assertRaises(ImportFileError): detect_format("fake.csv", "text/csv", b"PK\x03\x04zip")
        with self.assertRaises(ImportFileError): detect_format("fake.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"not zip")

    def test_path_traversal_is_reduced_to_metadata_basename(self):
        self.assertEqual(Path("../../hotel.csv").name, "hotel.csv")

    def test_service_rejects_oversized_content_before_storage(self):
        service = ImportService(MagicMock())
        service._settings = lambda: {**LIMITS, "maximum_import_file_size": 4, "supported_formats": ["csv", "xlsx"]}
        with self.assertRaises(ImportValidationError):
            service.create_import_session(original_filename="inventory.csv", content_type="text/csv", content=b"12345", uploader=SimpleNamespace(id="u1", username="admin"))


class CsvParserTests(unittest.TestCase):
    def parse(self, content: bytes, **limits):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.csv"; path.write_bytes(content)
            return parse_file(path, "csv", {**LIMITS, **limits})

    def test_csv_supports_bom_quotes_and_embedded_commas(self):
        parsed = self.parse("\ufeffasset tag,hostname,notes\r\nA-1,frontdesk-01,\"Lobby, primary\"\r\n".encode())
        self.assertEqual(parsed.rows[0][1]["notes"], "Lobby, primary")

    def test_csv_supports_semicolon_delimiter(self):
        parsed = self.parse(b"asset tag;hostname\nA-1;frontdesk-01\n")
        self.assertEqual(parsed.headers, ["asset tag", "hostname"])

    def test_csv_rejects_missing_header_malformed_and_excess_rows(self):
        with self.assertRaises(ImportFileError): self.parse(b"\n\n")
        with self.assertRaises(ImportFileError): self.parse(b'asset tag,hostname\n"unterminated,host\n')
        with self.assertRaises(ImportFileError): self.parse(b"asset tag,hostname\nA,a\nB,b\n", maximum_rows=1)


class XlsxParserTests(unittest.TestCase):
    def workbook(self, setup) -> Path:
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "sample.xlsx"; workbook = Workbook(); setup(workbook); workbook.save(path); workbook.close(); return path

    def test_xlsx_uses_first_suitable_sheet_and_lists_all_sheets(self):
        def setup(workbook):
            workbook.active.title = "Empty"
            sheet = workbook.create_sheet("Inventory"); sheet.append(["asset tag", "hostname"]); sheet.append(["A-1", "frontdesk-01"])
        parsed = parse_file(self.workbook(setup), "xlsx", LIMITS)
        self.assertEqual(parsed.selected_worksheet, "Inventory")
        self.assertEqual(parsed.worksheet_names, ["Empty", "Inventory"])

    def test_formula_cells_are_not_evaluated(self):
        def setup(workbook):
            sheet = workbook.active; sheet.append(["asset tag", "hostname", "notes"]); sheet.append(["A-1", "frontdesk-01", "=HYPERLINK(\"bad\")"])
        parsed = parse_file(self.workbook(setup), "xlsx", LIMITS)
        self.assertIsNone(parsed.rows[0][1]["notes"])
        self.assertEqual(parsed.rows[0][2][0]["code"], "formula_ignored")

    def test_corrupt_and_empty_workbooks_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            corrupt = Path(directory) / "bad.xlsx"; corrupt.write_bytes(b"PK\x03\x04broken")
            with self.assertRaises(ImportFileError): parse_file(corrupt, "xlsx", LIMITS)
        empty = self.workbook(lambda workbook: None)
        with self.assertRaises(ImportFileError): parse_file(empty, "xlsx", LIMITS)

    def test_xlsx_row_limit_is_enforced(self):
        def setup(workbook):
            sheet = workbook.active; sheet.append(["asset tag", "hostname"]); sheet.append(["A", "a"]); sheet.append(["B", "b"])
        with self.assertRaises(ImportFileError): parse_file(self.workbook(setup), "xlsx", {**LIMITS, "maximum_rows": 1})


class MappingAndValidationTests(unittest.TestCase):
    def test_aliases_unknown_missing_and_ambiguity(self):
        result = detect_mapping(["Asset ID", "Computer Name", "Mystery", "Host Name"])
        self.assertEqual(result["suggested_mapping"]["Asset ID"], "asset_tag")
        self.assertIn("Mystery", result["unknown_columns"])
        self.assertIn("hostname", result["ambiguous_mappings"])

    def test_manual_mapping_is_authoritative(self):
        mapping = validate_mapping(["Tag", "Machine"], {"Tag": "asset_tag", "Machine": "hostname"})
        self.assertEqual(mapping["Machine"], "hostname")
        with self.assertRaises(ValueError): validate_mapping(["Tag"], {"Tag": "asset_tag"})
        with self.assertRaises(ValueError): validate_mapping(["A", "B"], {"A": "hostname", "B": "hostname"})

    def test_normalizes_and_validates_device_fields(self):
        mapping = {"Tag": "asset_tag", "Host": "hostname", "IP": "ip_address", "MAC": "mac_address", "Status": "inventory_status"}
        normalized, errors, _ = validate_row({"Tag": "  A-1 ", "Host": " FRONTDESK-01 ", "IP": "10.0.0.5", "MAC": "00-11-22-AA-BB-CC", "Status": "in service"}, mapping)
        self.assertFalse(errors)
        self.assertEqual(normalized["hostname"], "frontdesk-01")
        self.assertEqual(normalized["mac_address"], "00:11:22:aa:bb:cc")
        self.assertEqual(normalized["inventory_status"], "Active")

    def test_invalid_network_status_and_length_are_reported(self):
        mapping = {"Tag": "asset_tag", "Host": "hostname", "IP": "ip_address", "MAC": "mac_address", "Status": "inventory_status", "Notes": "notes"}
        _, errors, _ = validate_row({"Tag": "bad tag!", "Host": "bad_host", "IP": "999.1.1.1", "MAC": "GG:00", "Status": "lost", "Notes": "x" * 2001}, mapping)
        self.assertEqual({item["code"] for item in errors}, {"invalid_asset_tag", "invalid_hostname", "invalid_ipv4", "invalid_mac", "invalid_inventory_status", "too_long"})


class ImportLifecycleTests(unittest.TestCase):
    def test_duplicate_rows_are_staged_and_counters_are_partial(self):
        STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
        filename = f"test-{uuid4().hex}.csv"; path = STORAGE_ROOT / filename
        path.write_text("asset tag,hostname,mac address\nA-1,desk-01,00:11:22:33:44:55\nA-2,desk-02,00:11:22:33:44:55\nBAD TAG!,bad_host,\n", encoding="utf-8")
        self.addCleanup(path.unlink, missing_ok=True)
        session = ImportSession(id=uuid4(), filename=filename, original_filename="inventory.csv", import_type="device_inventory", file_format="csv", uploaded_by="u1", status=ImportSessionStatus.UPLOADED, mapping_metadata={"headers": ["asset tag", "hostname", "mac address"], "mapping": {"asset tag": "asset_tag", "hostname": "hostname", "mac address": "mac_address"}}, total_rows=0, processed_rows=0, successful_rows=0, failed_rows=0, duplicate_rows=0, matched_rows=0, skipped_rows=0)
        db = MagicMock(); service = ImportService(db); service._settings = lambda: LIMITS
        service.sessions = SimpleNamespace(get=lambda _: session)
        staged = []
        service.devices = SimpleNamespace(delete_for_session=lambda _: staged.clear(), add=staged.append)
        actor = SimpleNamespace(id="u1", username="admin")
        result = service.process_import(session.id, actor)
        self.assertEqual(result.status, ImportSessionStatus.PARTIAL)
        self.assertEqual(result.processed_rows, 3)
        self.assertEqual(result.duplicate_rows, 1)
        self.assertEqual(result.failed_rows, 1)
        self.assertEqual(staged[1].validation_status, ImportValidationStatus.DUPLICATE)
        self.assertTrue(all(not isinstance(item, Device) for item in staged))

    def test_processing_lock_rejects_concurrent_validation(self):
        service = ImportService(MagicMock()); session = ImportSession(id=uuid4(), status=ImportSessionStatus.PROCESSING)
        service.sessions = SimpleNamespace(get=lambda _: session)
        with self.assertRaises(ImportConflictError): service.process_import(session.id, SimpleNamespace(username="admin"))


class ImportApiTests(unittest.TestCase):
    def test_routes_are_registered_and_mutations_are_role_protected(self):
        paths = app.openapi()["paths"]
        required = {"/api/v1/imports/device-inventory/upload", "/api/v1/imports/{session_id}", "/api/v1/imports/{session_id}/columns", "/api/v1/imports/{session_id}/mapping", "/api/v1/imports/{session_id}/validate", "/api/v1/imports/{session_id}/rows", "/api/v1/imports/{session_id}/errors", "/api/v1/imports/{session_id}/cancel"}
        self.assertTrue(required.issubset(paths))
        self.assertIn("security", paths["/api/v1/imports/device-inventory/upload"]["post"])

    def test_non_admin_cannot_call_mutation_dependencies(self):
        from app.imports.routes import router
        protected = {"/imports/device-inventory/upload", "/imports/{session_id}/mapping", "/imports/{session_id}/validate", "/imports/{session_id}/cancel"}
        for route in router.routes:
            if route.path not in protected: continue
            role_checkers = [dependency.call for dependency in route.dependant.dependencies if getattr(dependency.call, "__name__", "") == "role_checker"]
            self.assertEqual(len(role_checkers), 1)
            with self.assertRaises(Exception) as raised:
                role_checkers[0](SimpleNamespace(role="technician"))
            self.assertEqual(raised.exception.status_code, 403)


if __name__ == "__main__": unittest.main()
