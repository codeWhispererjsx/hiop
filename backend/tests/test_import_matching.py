import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.imports.matching import classify, normalize_record, score_records, select_hostname_rule, select_subnet_rule
from app.main import app
from app.models.inventory_import import ImportLocationSuggestion, ImportMatchCandidate, ImportSession, ImportedDevice
from app.services.import_matching_service import ImportMatchingService, MatchingConflictError, MatchingNotFoundError, MatchingValidationError
from app.services.settings_service import read_import_settings


def settings(**overrides):
    base = {"exact_match_threshold": 95, "strong_match_threshold": 80, "probable_match_threshold": 60, "weak_match_threshold": 35, "conflict_penalty": 35, "fuzzy_matching_enabled": True, "hostname_similarity_threshold": 88, "fuzzy_similarity_threshold": 90}
    return {**base, **overrides}


class MatchingScoreTests(unittest.TestCase):
    def test_exact_identifiers_and_hostname_ip(self):
        self.assertEqual(score_records({"mac_address": "00:11:22:33:44:55"}, {"mac_address": "00-11-22-33-44-55"}, settings())["level"], "exact")
        self.assertEqual(score_records({"asset_tag": "A-100"}, {"asset_tag": "a100"}, settings())["score"], 95)
        self.assertEqual(score_records({"serial_number": " SN 1 "}, {"serial_number": "sn1"}, settings())["score"], 92)
        result = score_records({"hostname": "desk-01", "ip_address": "10.0.0.2"}, {"hostname": "DESK-01", "ip_address": "10.0.0.2"}, settings())
        self.assertEqual(result["score"], 75)
        self.assertEqual(result["level"], "probable")

    def test_ip_only_is_weak_and_never_certain(self):
        result = score_records({"ip_address": "10.0.0.2"}, {"ip_address": "10.0.0.2"}, settings())
        self.assertEqual((result["score"], result["level"], result["recommended_action"]), (35, "weak", "review"))

    def test_conflicts_reduce_score_and_are_explained(self):
        result = score_records({"mac_address": "001122334455", "asset_tag": "A-1"}, {"mac_address": "001122334455", "asset_tag": "A-2"}, settings())
        self.assertEqual(result["score"], 61)
        self.assertEqual(result["recommended_action"], "review")
        self.assertEqual(result["conflicts"][0]["field"], "asset_tag")

    def test_exact_serial_with_conflicting_hostname_requires_review(self):
        result = score_records({"serial_number": "SN-100", "hostname": "desk-01"}, {"serial_number": "SN-100", "hostname": "desk-99"}, settings())
        self.assertEqual(result["score"], 57)
        self.assertEqual(result["recommended_action"], "review")
        self.assertEqual(result["conflicts"][0]["field"], "hostname")

    def test_fuzzy_only_never_links(self):
        result = score_records({"hostname": "frontdesk-01"}, {"hostname": "frontdesk-02"}, settings(hostname_similarity_threshold=80))
        self.assertTrue(result["fuzzy_only"])
        self.assertNotIn(result["recommended_action"], {"link", "merge"})
        self.assertEqual(result["evidence"][0]["kind"], "similar")

    def test_normalization_is_conservative(self):
        row = normalize_record({"asset_tag": " A-01 ", "hostname": " Front Desk 01 ", "vendor": "ACME  Corp"})
        self.assertEqual(row["asset_tag"], "a01")
        self.assertEqual(row["hostname"], "front desk 01")
        self.assertEqual(row["vendor"], "acme corp")
        self.assertEqual(classify(34, {"exact": 95, "strong": 80, "probable": 60, "weak": 35}), "none")

    def test_longest_subnet_and_ordered_hostname_rules(self):
        broad, narrow = {"cidr": "10.50.0.0/16", "name": "broad"}, {"cidr": "10.50.20.0/24", "name": "narrow"}
        self.assertEqual(select_subnet_rule("10.50.20.8", [broad, narrow])["name"], "narrow")
        rules = [{"pattern": "FO-*", "name": "front-office"}, {"pattern": "*", "name": "fallback"}]
        self.assertEqual(select_hostname_rule("fo-desk-01", rules)["name"], "front-office")


class MatchingModelTests(unittest.TestCase):
    def test_candidate_and_location_contracts(self):
        candidate_columns = set(ImportMatchCandidate.__table__.columns.keys())
        self.assertTrue({"candidate_device_id", "candidate_discovery_id", "candidate_imported_device_id", "evidence", "conflicting_fields", "matching_fields"}.issubset(candidate_columns))
        self.assertTrue({"department_id", "building_id", "floor_id", "room_id", "network_zone_id", "evidence", "conflicts"}.issubset(ImportLocationSuggestion.__table__.columns.keys()))
        self.assertTrue(any(index.name == "ix_import_match_candidates_session_rank" for index in ImportMatchCandidate.__table__.indexes))

    def test_matching_settings_are_typed(self):
        db = MagicMock(); db.query.return_value.all.return_value = []
        values = read_import_settings(db)
        self.assertEqual(values["maximum_candidates_per_row"], 5)
        self.assertEqual(values["exact_match_threshold"], 95)
        self.assertTrue(values["fuzzy_matching_enabled"])
        self.assertEqual(values["subnet_mapping_rules"], [])


class ResolutionSafetyTests(unittest.TestCase):
    def service(self):
        service = ImportMatchingService(MagicMock())
        session_id, row_id, candidate_id = uuid4(), uuid4(), uuid4()
        row = ImportedDevice(id=row_id, import_session_id=session_id, source_row_number=2)
        candidate = ImportMatchCandidate(id=candidate_id, import_session_id=session_id, imported_device_id=row_id, candidate_type="inventory_device", candidate_device_id=uuid4(), match_score=96, match_level="exact", match_status="pending", recommended_action="link")
        service.rows = SimpleNamespace(get=lambda value: row if value == row_id else None)
        service.repository = SimpleNamespace(get_candidate=lambda value: candidate if value == candidate_id else None, candidates_for_row=lambda *_: [candidate])
        return service, session_id, row_id, candidate_id, row, candidate

    @patch("app.services.import_matching_service.create_audit_log")
    def test_accept_is_link_only_and_contradictory_resolution_is_blocked(self, _audit):
        service, session_id, row_id, candidate_id, row, candidate = self.service()
        service.resolve_candidate(session_id, row_id, candidate_id, SimpleNamespace(id="u1", username="admin"), accept=True)
        self.assertEqual(row.resolution_action, "linked")
        self.assertEqual(row.linked_device_id, candidate.candidate_device_id)
        self.assertIsNone(getattr(row, "asset_tag", None))
        candidate.match_status = "pending"
        with self.assertRaises(MatchingConflictError): service.resolve_candidate(session_id, row_id, candidate_id, SimpleNamespace(id="u1", username="admin"), accept=True)

    def test_cross_session_candidate_is_rejected(self):
        service, session_id, row_id, candidate_id, _, candidate = self.service()
        candidate.import_session_id = uuid4()
        with self.assertRaises(MatchingNotFoundError): service.resolve_candidate(session_id, row_id, candidate_id, SimpleNamespace(id="u1", username="admin"), accept=True)

    def test_matching_requires_validated_session_and_lock(self):
        service = ImportMatchingService(MagicMock()); session = ImportSession(id=uuid4(), status="uploaded", matching_state="idle")
        service.sessions = SimpleNamespace(get=lambda _: session)
        with self.assertRaises(MatchingValidationError): service.run(session.id, SimpleNamespace(username="admin"))
        session.status, session.matching_state = "completed", "running"
        with self.assertRaises(MatchingConflictError): service.run(session.id, SimpleNamespace(username="admin"))


class MatchingApiTests(unittest.TestCase):
    def test_review_routes_and_security_are_registered(self):
        paths = app.openapi()["paths"]
        required = {"/api/v1/imports/{session_id}/match", "/api/v1/imports/{session_id}/matches", "/api/v1/imports/{session_id}/rows/{row_id}/matches", "/api/v1/imports/{session_id}/rows/{row_id}/merge-plan", "/api/v1/imports/{session_id}/rows/{row_id}/accept-match", "/api/v1/imports/{session_id}/rows/{row_id}/reject-match", "/api/v1/imports/{session_id}/rows/{row_id}/mark-create-new", "/api/v1/imports/{session_id}/rows/{row_id}/location-suggestion", "/api/v1/imports/{session_id}/matches/recompute"}
        self.assertTrue(required.issubset(paths))
        self.assertIn("security", paths["/api/v1/imports/{session_id}/match"]["post"])

    def test_matching_mutations_are_admin_only(self):
        from app.imports.routes import router
        protected_suffixes = {"/match", "/accept-match", "/reject-match", "/mark-create-new", "/location-suggestion", "/matches/recompute"}
        checked = 0
        for route in router.routes:
            if not any(route.path.endswith(suffix) for suffix in protected_suffixes): continue
            role_checkers = [dependency.call for dependency in route.dependant.dependencies if getattr(dependency.call, "__name__", "") == "role_checker"]
            self.assertEqual(len(role_checkers), 1)
            with self.assertRaises(Exception) as raised: role_checkers[0](SimpleNamespace(role="technician"))
            self.assertEqual(raised.exception.status_code, 403)
            checked += 1
        self.assertEqual(checked, 6)


class MatchingMigrationTests(unittest.TestCase):
    def test_revision_chain(self):
        path = Path(__file__).parents[1] / "alembic" / "versions" / "91b7d3e5a204_add_import_matching_models.py"
        spec = importlib.util.spec_from_file_location("matching_migration", path); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        self.assertEqual(module.revision, "91b7d3e5a204")
        self.assertEqual(module.down_revision, "2c6a8e4f901b")


if __name__ == "__main__": unittest.main()
