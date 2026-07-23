"""Offline tests for Epic 3C staging and change detection."""

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.main import app
from app.models.active_directory import (
    ActiveDirectoryObject,
    ActiveDirectoryObjectChange,
    ActiveDirectorySyncError,
    ActiveDirectorySyncRun,
)
from app.schemas.active_directory import ActiveDirectorySyncRequest
from app.services.active_directory_sync_service import (
    ActiveDirectorySynchronizationService,
    canonical_directory_values,
    classify_change,
    content_hash,
    stable_identity,
)
from app.services.ldap_client import build_search_filter


class DirectoryNormalizationTests(unittest.TestCase):
    def test_stable_identity_priority(self):
        identity, guid = stable_identity({
            "object_guid": "A00B", "object_sid": "S-1-5-1",
            "distinguished_name": "CN=One,DC=example,DC=invalid",
        })
        self.assertEqual(identity, "guid:a00b")
        self.assertEqual(guid, "a00b")

    def test_sid_and_dn_fallbacks_are_stable(self):
        self.assertEqual(
            stable_identity({"object_sid": "S-1-5-2"})[0], "sid:S-1-5-2"
        )
        left = stable_identity({"distinguished_name": "CN=One, DC=Example, DC=Invalid"})
        right = stable_identity({"distinguished_name": "cn=one,dc=example,dc=invalid"})
        self.assertEqual(left, right)

    def test_group_order_does_not_create_false_change(self):
        a = canonical_directory_values({
            "distinguished_name": "CN=Ops,DC=example,DC=invalid",
            "members": ["CN=B,DC=x", "CN=A,DC=x"],
        }, "group")
        b = canonical_directory_values({
            "distinguished_name": "CN=Ops,DC=example,DC=invalid",
            "members": ["CN=A,DC=x", "CN=B,DC=x"],
        }, "group")
        self.assertEqual(content_hash(a), content_hash(b))

    def test_case_and_empty_values_normalize(self):
        values = canonical_directory_values({
            "distinguished_name": "CN=PC, DC=example, DC=invalid",
            "dns_hostname": " PC.EXAMPLE.INVALID ",
            "email": "",
            "enabled": False,
        }, "computer")
        self.assertEqual(values["dns_hostname"], "pc.example.invalid")
        self.assertIsNone(values["email"])
        self.assertFalse(values["enabled"])

    def test_change_classification(self):
        self.assertEqual(classify_change({}, {}, True), "restored")
        self.assertEqual(classify_change({"enabled": True}, {"enabled": False}, False), "disabled")
        self.assertEqual(classify_change(
            {"distinguished_name": "CN=A,OU=One"}, {"distinguished_name": "CN=A,OU=Two"}, False
        ), "moved")

    def test_incremental_filter_is_fixed_and_utc(self):
        value = build_search_filter(
            "user", changed_since=datetime(2026, 7, 23, tzinfo=timezone.utc)
        )
        self.assertIn("(whenChanged>=20260723000000.0Z)", value)
        self.assertNotIn("None", value)


class SyncContractTests(unittest.TestCase):
    def test_dry_run_create_does_not_persist(self):
        db = MagicMock()
        service = ActiveDirectorySynchronizationService(db)
        service._existing = MagicMock(return_value=None)
        outcome = service._stage_item(
            SimpleNamespace(connection_id="c1", id="r1"), "user",
            {
                "object_guid": "00000000-0000-0000-0000-000000000001",
                "distinguished_name": "CN=User,DC=example,DC=invalid",
            },
            datetime.now(timezone.utc), dry_run=True,
        )
        self.assertEqual(outcome, "created")
        db.add.assert_not_called()

    def test_unchanged_update_preserves_review_and_match(self):
        values = canonical_directory_values({
            "distinguished_name": "CN=PC,DC=example,DC=invalid",
            "dns_hostname": "pc.example.invalid", "enabled": True,
        }, "computer")
        obj = SimpleNamespace(
            **values, sync_status="unchanged", review_status="approved",
            matched_device_id="device-1", last_seen_at=None, last_sync_run_id=None,
        )
        service = ActiveDirectorySynchronizationService(MagicMock())
        service._existing = MagicMock(return_value=obj)
        outcome = service._stage_item(
            SimpleNamespace(connection_id="c1", id="r1"), "computer",
            {
                "object_guid": "00000000-0000-0000-0000-000000000002",
                "distinguished_name": "CN=PC,DC=example,DC=invalid",
                "dns_hostname": "PC.EXAMPLE.INVALID", "enabled": True,
            },
            datetime.now(timezone.utc), dry_run=False,
        )
        self.assertEqual(outcome, "unchanged")
        self.assertEqual(obj.review_status, "approved")
        self.assertEqual(obj.matched_device_id, "device-1")

    def test_request_rejects_duplicate_types(self):
        with self.assertRaises(ValueError):
            ActiveDirectorySyncRequest(object_types=["user", "user"])

    def test_state_machine_rejects_invalid_transition(self):
        run = SimpleNamespace(status="completed")
        with self.assertRaises(Exception):
            ActiveDirectorySynchronizationService._transition(run, "running")

    def test_models_have_persistent_recovery_fields(self):
        run_columns = ActiveDirectorySyncRun.__table__.columns
        for field in (
            "sync_mode", "object_types", "checkpoint_before", "checkpoint_after",
            "progress", "per_type_status", "dry_run_results", "cancel_requested_at",
        ):
            self.assertIn(field, run_columns)
        object_columns = ActiveDirectoryObject.__table__.columns
        self.assertIn("missing_since", object_columns)
        self.assertIn("last_sync_run_id", object_columns)
        self.assertEqual(ActiveDirectoryObjectChange.__tablename__, "active_directory_object_changes")
        self.assertEqual(ActiveDirectorySyncError.__tablename__, "active_directory_sync_errors")

    def test_required_routes_are_registered(self):
        paths = set(app.openapi()["paths"])
        expected = {
            "/api/v1/active-directory/connections/{id}/sync",
            "/api/v1/active-directory/sync-runs/{id}",
            "/api/v1/active-directory/sync-runs/{id}/cancel",
            "/api/v1/active-directory/sync-runs/{id}/errors",
            "/api/v1/active-directory/sync-runs/{id}/summary",
            "/api/v1/active-directory/sync-runs/{id}/dry-run-results",
            "/api/v1/active-directory/objects/{id}",
            "/api/v1/active-directory/objects/{id}/changes",
        }
        self.assertTrue(expected.issubset(paths))

    def test_mutation_routes_are_documented_as_authenticated(self):
        paths = app.openapi()["paths"]
        for path in (
            "/api/v1/active-directory/connections/{id}/sync",
            "/api/v1/active-directory/sync-runs/{id}/cancel",
        ):
            self.assertIn("post", paths[path])


if __name__ == "__main__":
    unittest.main()
