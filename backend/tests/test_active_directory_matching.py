"""Offline Epic 3D scoring, safeguards, and API contract tests."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import HTTPException

from app.main import app
from app.models.active_directory import (
    ActiveDirectoryDepartmentMapping,
    ActiveDirectoryGroupRoleMapping,
    ActiveDirectoryMatchCandidate,
    ActiveDirectoryObject,
    ActiveDirectoryOUMapping,
    ActiveDirectoryReconciliationResult,
    ActiveDirectoryRecordLink,
)
from app.models.device import Device
from app.models.discovered_device import DiscoveredDevice
from app.models.user import User
from app.schemas.active_directory import (
    ActiveDirectoryGroupRoleMappingWrite,
    ActiveDirectoryOUMappingWrite,
    ActiveDirectoryResolveRequest,
)
from app.services.active_directory_matching_service import (
    normalized,
    score_device,
    score_discovery,
    score_level,
    score_user,
    similarity,
)
from app.services.active_directory_reconciliation_service import (
    ActiveDirectoryReconciliationService,
)


SETTINGS = {
    "exact_threshold": 95, "strong_threshold": 80, "probable_threshold": 60,
    "weak_threshold": 35, "candidate_limit": 5, "fuzzy_enabled": True,
    "fill_missing_only": True, "role_mapping_enabled": True,
    "department_mapping_enabled": True, "ou_mapping_enabled": True,
    "admin_confirmation_required": True, "bulk_exact_limit": 100,
    "reconciliation_batch_size": 50, "conflict_penalty": 35,
}


def ad_user(**values):
    defaults = {
        "object_type": "user", "sam_account_name": "jane", "email": "jane@example.invalid",
        "user_principal_name": "jane@example.invalid", "display_name": "Jane Doe",
        "common_name": "Jane Doe", "department": "Front Office", "enabled": True,
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


def ad_computer(**values):
    defaults = {
        "object_type": "computer", "sam_account_name": "FO-PC01$",
        "dns_hostname": "fo-pc01.example.invalid", "department": "Front Office",
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


class UserScoringTests(unittest.TestCase):
    def test_exact_email_ranks_exact(self):
        result = score_user(ad_user(), User(username="other", email="jane@example.invalid"), SETTINGS)
        self.assertEqual(result["level"], "exact")
        self.assertIn("email", result["matching_fields"])

    def test_exact_upn_is_high_confidence(self):
        result = score_user(ad_user(email=None), User(username="other", email="jane@example.invalid"), SETTINGS)
        self.assertEqual(result["level"], "strong")
        self.assertIn("user_principal_name", result["matching_fields"])

    def test_exact_username_is_strong(self):
        result = score_user(
            ad_user(email=None, user_principal_name=None),
            User(username="JANE", email="other@example.invalid"), SETTINGS,
        )
        self.assertEqual(result["level"], "strong")
        self.assertIn("username", result["matching_fields"])

    def test_conflicting_email_is_explainable(self):
        result = score_user(
            ad_user(user_principal_name=None),
            User(username="jane", email="different@example.invalid"), SETTINGS,
        )
        self.assertTrue(result["conflicting_fields"])
        self.assertEqual(result["recommended_action"], "conflict")

    def test_name_only_cannot_be_exact(self):
        result = score_user(
            ad_user(email=None, user_principal_name=None, sam_account_name=""),
            User(username="Jane Doe", email="unrelated@example.invalid"), SETTINGS,
        )
        self.assertNotEqual(result["level"], "exact")


class DeviceScoringTests(unittest.TestCase):
    def target(self, **values):
        defaults = {
            "hostname": "fo-pc01.example.invalid", "mac_address": "AA:BB:CC:DD:EE:FF",
            "ip_address": "10.0.0.10", "department": "Front Office",
        }
        defaults.update(values)
        return SimpleNamespace(**defaults)

    def test_exact_dns_hostname(self):
        result = score_device(ad_computer(), self.target(), SETTINGS)
        self.assertEqual(result["level"], "exact")
        self.assertIn("dns_hostname", result["matching_fields"])

    def test_exact_short_hostname_is_strong(self):
        result = score_device(
            ad_computer(dns_hostname=None), self.target(hostname="fo-pc01"), SETTINGS
        )
        self.assertEqual(result["level"], "strong")

    def test_discovery_mac_is_high_confidence(self):
        discovery = SimpleNamespace(mac_address="AA:BB:CC:DD:EE:FF", ip_address="10.0.0.99")
        result = score_device(
            ad_computer(dns_hostname=None, sam_account_name="different$"),
            self.target(), SETTINGS, discovery,
        )
        self.assertIn("discovery_mac", result["matching_fields"])
        self.assertEqual(result["level"], "exact")

    def test_ip_only_is_not_exact(self):
        discovery = SimpleNamespace(mac_address=None, ip_address="10.0.0.10")
        result = score_device(
            ad_computer(dns_hostname=None, sam_account_name="different$"),
            self.target(), SETTINGS, discovery,
        )
        self.assertEqual(result["level"], "probable")

    def test_conflicting_mac_is_detected(self):
        discovery = SimpleNamespace(mac_address="00:11:22:33:44:55", ip_address="10.0.0.10")
        result = score_device(ad_computer(), self.target(), SETTINGS, discovery)
        self.assertTrue(any(item["field"] == "mac_address" for item in result["conflicting_fields"]))

    def test_discovery_hostname_suggestion(self):
        result = score_discovery(
            ad_computer(), SimpleNamespace(hostname="fo-pc01.example.invalid"), SETTINGS
        )
        self.assertEqual(result["level"], "strong")


class MatchingPrimitiveTests(unittest.TestCase):
    def test_thresholds(self):
        expected = ((100, "exact"), (90, "strong"), (70, "probable"), (40, "weak"), (20, "none"))
        for value, level in expected:
            self.assertEqual(score_level(value, SETTINGS), level)

    def test_normalization_is_conservative(self):
        self.assertEqual(normalized("  Jane   DOE "), "jane doe")
        self.assertGreater(similarity("front-office", "front office"), 80)

    def test_candidate_model_has_all_target_types(self):
        columns = ActiveDirectoryMatchCandidate.__table__.columns
        for name in (
            "candidate_user_id", "candidate_device_id", "candidate_discovery_id",
            "candidate_department_id", "candidate_role_id", "source_version", "target_version",
        ):
            self.assertIn(name, columns)

    def test_mapping_and_result_models_exist(self):
        self.assertEqual(ActiveDirectoryRecordLink.__tablename__, "active_directory_record_links")
        self.assertEqual(ActiveDirectoryDepartmentMapping.__tablename__, "active_directory_department_mappings")
        self.assertEqual(ActiveDirectoryOUMapping.__tablename__, "active_directory_ou_mappings")
        self.assertEqual(ActiveDirectoryGroupRoleMapping.__tablename__, "active_directory_group_role_mappings")
        self.assertEqual(ActiveDirectoryReconciliationResult.__tablename__, "active_directory_reconciliation_results")


class ReconciliationSafeguardTests(unittest.TestCase):
    def test_admin_mapping_may_require_confirmation(self):
        payload = ActiveDirectoryGroupRoleMappingWrite(
            source_group="HIOP-Admins", target_role="admin"
        )
        self.assertTrue(payload.requires_confirmation)

    def test_ou_patterns_are_non_executable(self):
        with self.assertRaises(ValueError):
            ActiveDirectoryOUMappingWrite(pattern="__import__('os').system('x')")

    def test_resolve_requires_confirmation(self):
        payload = ActiveDirectoryResolveRequest(action="ignore")
        self.assertFalse(payload.confirm)

    def test_user_onboarding_never_creates_password(self):
        obj = ActiveDirectoryObject(
            id="object-1", connection_id="connection-1",
            object_guid="guid-1", object_type="user",
            distinguished_name="CN=Jane,DC=example,DC=invalid",
            sam_account_name="jane", email="jane@example.invalid",
            enabled=True, raw_attributes={},
        )
        db = MagicMock()
        db.get.side_effect = lambda model, key: obj if model is ActiveDirectoryObject else None
        service = ActiveDirectoryReconciliationService(db)
        result = service.resolve(
            obj.id, SimpleNamespace(id="admin-1", username="admin"),
            action="create_new_user", candidate_id=None, approved_fields=[],
            device_payload=None, role="staff", active=True, confirm=True,
        )
        self.assertEqual(result.status, "pending_manual_setup")
        self.assertTrue(result.after_values["password_required"])
        self.assertNotIn("password", result.after_values)
        self.assertFalse(any(isinstance(call.args[0], User) for call in db.add.call_args_list))

    def test_admin_onboarding_needs_extra_confirmation(self):
        obj = ActiveDirectoryObject(
            id="object-2", connection_id="connection-1",
            object_guid="guid-2", object_type="user",
            distinguished_name="CN=Jane,DC=example,DC=invalid",
            sam_account_name="jane", email="jane@example.invalid",
            enabled=True, raw_attributes={},
        )
        db = MagicMock()
        db.get.side_effect = lambda model, key: obj if model is ActiveDirectoryObject else None
        with self.assertRaises(HTTPException) as error:
            ActiveDirectoryReconciliationService(db).resolve(
                obj.id, SimpleNamespace(id="admin-1", username="admin"),
                action="create_new_user", candidate_id=None, approved_fields=[],
                device_payload=None, role="admin", active=True, confirm=True,
            )
        self.assertEqual(error.exception.status_code, 409)

    def test_incomplete_device_creation_is_rejected(self):
        obj = ActiveDirectoryObject(
            id="object-3", connection_id="connection-1",
            object_guid="guid-3", object_type="computer",
            distinguished_name="CN=PC,DC=example,DC=invalid",
            sam_account_name="PC$", enabled=True, raw_attributes={},
        )
        db = MagicMock()
        db.get.side_effect = lambda model, key: obj if model is ActiveDirectoryObject else None
        with self.assertRaises(HTTPException) as error:
            ActiveDirectoryReconciliationService(db).resolve(
                obj.id, SimpleNamespace(id="admin-1", username="admin"),
                action="create_new_device", candidate_id=None, approved_fields=[],
                device_payload={"hostname": "pc"}, role=None, active=None, confirm=True,
            )
        self.assertEqual(error.exception.status_code, 422)


class Epic3DApiContractTests(unittest.TestCase):
    def test_routes_exist(self):
        paths = set(app.openapi()["paths"])
        expected = {
            "/api/v1/active-directory/connections/{id}/match",
            "/api/v1/active-directory/objects/{id}/matches",
            "/api/v1/active-directory/objects/{id}/reconciliation-plan",
            "/api/v1/active-directory/objects/{id}/accept-match",
            "/api/v1/active-directory/objects/{id}/reject-match",
            "/api/v1/active-directory/objects/{id}/mark-create",
            "/api/v1/active-directory/objects/{id}/ignore",
            "/api/v1/active-directory/objects/{id}/resolve",
            "/api/v1/active-directory/bulk-review",
            "/api/v1/active-directory/connections/{id}/mappings/departments",
            "/api/v1/active-directory/connections/{id}/mappings/ous",
            "/api/v1/active-directory/connections/{id}/mappings/roles",
        }
        self.assertTrue(expected.issubset(paths))


if __name__ == "__main__":
    unittest.main()
