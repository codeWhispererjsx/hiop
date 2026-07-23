import importlib.util
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import CheckConstraint, UniqueConstraint

from app.core.config import settings
from app.main import app
from app.models.active_directory import (
    ActiveDirectoryConnection,
    ActiveDirectoryMatchCandidate,
    ActiveDirectoryObject,
    ActiveDirectorySyncConfiguration,
    ActiveDirectorySyncRun,
)
from app.schemas.active_directory import (
    ActiveDirectoryConnectionCreate,
    ActiveDirectoryConnectionRead,
    ActiveDirectoryConnectionUpdate,
    ActiveDirectorySyncConfigurationUpdate,
)
from app.services.active_directory_secret_service import (
    ActiveDirectorySecretError,
    ActiveDirectorySecretService,
)
from app.services.active_directory_service import (
    ActiveDirectoryMatchingService,
    ActiveDirectorySyncService,
)
from app.services.ldap_client import MockLdapClient


def connection_payload(**overrides):
    values = {
        "name": "Primary Hotel AD",
        "domain_name": "hotel.internal",
        "server_host": "dc01.hotel.internal",
        "server_port": 636,
        "use_ssl": True,
        "base_dn": "DC=hotel,DC=internal",
        "user_search_base": "OU=Users,DC=hotel,DC=internal",
        "bind_username": "cn=binder,dc=hotel,dc=internal",
        "bind_secret": "unit-test-secret",
    }
    values.update(overrides)
    return values


class ActiveDirectorySecretTests(unittest.TestCase):
    @patch.dict(os.environ, {"HIOP_AD_SECRET_KEY": "test-key-one"}, clear=False)
    def test_encrypt_decrypt_and_write_only_serialization(self):
        plaintext = "SuperSecretBindPassword123!"
        encrypted = ActiveDirectorySecretService.encrypt_secret(plaintext)
        self.assertNotEqual(encrypted, plaintext)
        self.assertNotIn(plaintext, encrypted)
        self.assertEqual(ActiveDirectorySecretService.decrypt_secret(encrypted), plaintext)

    @patch.dict(os.environ, {"HIOP_AD_SECRET_KEY": "test-key-one"}, clear=False)
    def test_wrong_key_and_invalid_ciphertext_fail_safely(self):
        encrypted = ActiveDirectorySecretService.encrypt_secret("never-log-me")
        with patch.dict(os.environ, {"HIOP_AD_SECRET_KEY": "different-key"}, clear=False):
            with self.assertRaisesRegex(ActiveDirectorySecretError, "Invalid encryption key"):
                ActiveDirectorySecretService.decrypt_secret(encrypted)
        with self.assertRaises(ActiveDirectorySecretError):
            ActiveDirectorySecretService.decrypt_secret("invalid")

    def test_missing_key_and_empty_values_fail(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "app.services.active_directory_secret_service.settings"
        ) as mock_settings:
            mock_settings.secret_key = ""
            with self.assertRaisesRegex(ActiveDirectorySecretError, "missing"):
                ActiveDirectorySecretService.encrypt_secret("secret")
        with self.assertRaises(ActiveDirectorySecretError):
            ActiveDirectorySecretService.encrypt_secret("")
        with self.assertRaises(ActiveDirectorySecretError):
            ActiveDirectorySecretService.decrypt_secret("")

    @patch.dict(os.environ, {}, clear=True)
    def test_existing_hiop_secret_is_a_supported_fallback(self):
        encrypted = ActiveDirectorySecretService.encrypt_secret("fallback-secret")
        self.assertEqual(ActiveDirectorySecretService.decrypt_secret(encrypted), "fallback-secret")


class ActiveDirectorySchemaTests(unittest.TestCase):
    def test_valid_connection_and_safe_read_schema(self):
        schema = ActiveDirectoryConnectionCreate(**connection_payload())
        self.assertEqual(schema.domain_name, "hotel.internal")
        data = {
            **schema.model_dump(exclude={"bind_secret"}),
            "id": str(uuid4()),
            "has_bind_secret": True,
            "last_tested_at": None,
            "last_test_status": None,
            "last_test_message": None,
            "created_by": None,
            "updated_by": None,
            "created_at": "2026-07-23T12:00:00Z",
            "updated_at": "2026-07-23T12:00:00Z",
        }
        serialized = ActiveDirectoryConnectionRead(**data).model_dump()
        self.assertNotIn("bind_secret", serialized)
        self.assertNotIn("encrypted_bind_secret", serialized)

    def test_domain_host_dn_port_timeout_and_page_validation(self):
        invalid = [
            {"domain_name": "bad domain"},
            {"server_host": "bad host!"},
            {"base_dn": "not-a-dn"},
            {"user_search_base": "also-not-a-dn"},
            {"server_port": 70000},
            {"connection_timeout_seconds": 0},
            {"page_size": 5001},
        ]
        for overrides in invalid:
            with self.subTest(overrides=overrides), self.assertRaises(ValidationError):
                ActiveDirectoryConnectionCreate(**connection_payload(**overrides))

    def test_transport_and_anonymous_credentials_are_consistent(self):
        with self.assertRaises(ValidationError):
            ActiveDirectoryConnectionCreate(
                **connection_payload(use_ssl=True, use_start_tls=True)
            )
        with self.assertRaises(ValidationError):
            ActiveDirectoryConnectionCreate(
                **connection_payload(authentication_method="anonymous")
            )
        with self.assertRaises(ValidationError):
            ActiveDirectoryConnectionUpdate(domain_name="bad domain")

    def test_sync_interval_and_conflict_policy_validation(self):
        with self.assertRaises(ValidationError):
            ActiveDirectorySyncConfigurationUpdate(sync_interval_minutes=0)
        with self.assertRaises(ValidationError):
            ActiveDirectorySyncConfigurationUpdate(conflict_policy="overwrite_everything")


class ActiveDirectoryModelTests(unittest.TestCase):
    def test_columns_relationships_indexes_and_stable_identity(self):
        self.assertTrue(
            {"encrypted_bind_secret", "verify_tls", "base_dn"}.issubset(
                ActiveDirectoryConnection.__table__.columns.keys()
            )
        )
        self.assertIn("sync_configuration", ActiveDirectoryConnection.__mapper__.relationships)
        self.assertIn("objects", ActiveDirectoryConnection.__mapper__.relationships)
        self.assertIn("match_candidates", ActiveDirectoryObject.__mapper__.relationships)
        self.assertEqual(
            str(ActiveDirectoryObject.__table__.c.matched_device_id.type),
            "UUID",
        )
        self.assertEqual(
            str(ActiveDirectoryMatchCandidate.__table__.c.candidate_device_id.type),
            "UUID",
        )
        self.assertTrue(
            any(
                isinstance(item, UniqueConstraint)
                and item.name == "uq_ad_object_connection_guid"
                for item in ActiveDirectoryObject.__table__.constraints
            )
        )
        object_indexes = {index.name for index in ActiveDirectoryObject.__table__.indexes}
        self.assertTrue(
            {"ix_ad_objects_object_guid", "ix_ad_objects_sync_status", "ix_ad_objects_review_status"}
            .issubset(object_indexes)
        )

    def test_database_safety_constraints_exist(self):
        constraint_names = {
            constraint.name
            for table in (
                ActiveDirectoryConnection.__table__,
                ActiveDirectorySyncConfiguration.__table__,
                ActiveDirectoryObject.__table__,
                ActiveDirectorySyncRun.__table__,
                ActiveDirectoryMatchCandidate.__table__,
            )
            for constraint in table.constraints
            if isinstance(constraint, CheckConstraint)
        }
        self.assertTrue(
            {
                "ck_ad_connection_single_tls_mode",
                "ck_ad_object_type",
                "ck_ad_sync_run_nonnegative_counts",
                "ck_ad_candidate_typed_target",
                "ck_ad_candidate_score",
            }.issubset(constraint_names)
        )


class ActiveDirectoryApiContractTests(unittest.TestCase):
    def test_routes_exist_and_no_sync_mutation_route_exists(self):
        paths = app.openapi()["paths"]
        expected = {
            "/api/v1/active-directory/connections",
            "/api/v1/active-directory/connections/{id}",
            "/api/v1/active-directory/connections/{id}/secret",
            "/api/v1/active-directory/connections/{id}/disable",
            "/api/v1/active-directory/connections/{id}/test",
            "/api/v1/active-directory/connections/{id}/sync-config",
            "/api/v1/active-directory/sync-runs",
            "/api/v1/active-directory/objects",
            "/api/v1/active-directory/matches",
        }
        self.assertTrue(expected.issubset(paths))
        self.assertNotIn("/api/v1/active-directory/sync", paths)

    def test_mutations_are_admin_only_and_reads_exclude_staff(self):
        for route in app.routes:
            if not getattr(route, "path", "").startswith("/api/v1/active-directory"):
                continue
            methods = getattr(route, "methods", set())
            role_dependency = next(
                (
                    dependency.call
                    for dependency in route.dependant.dependencies
                    if getattr(dependency.call, "__name__", "") == "role_checker"
                ),
                None,
            )
            self.assertIsNotNone(role_dependency, route.path)
            if methods.intersection({"POST", "PATCH", "PUT", "DELETE"}):
                with self.assertRaises(HTTPException) as denied:
                    role_dependency(current_user=SimpleNamespace(role="technician"))
                self.assertEqual(denied.exception.status_code, 403)
                self.assertEqual(
                    role_dependency(current_user=SimpleNamespace(role="admin")).role,
                    "admin",
                )
            else:
                self.assertEqual(
                    role_dependency(current_user=SimpleNamespace(role="technician")).role,
                    "technician",
                )
                with self.assertRaises(HTTPException):
                    role_dependency(current_user=SimpleNamespace(role="staff"))


class ActiveDirectoryFoundationBoundaryTests(unittest.TestCase):
    def test_mock_client_never_performs_network_io(self):
        client = MockLdapClient("dc01.hotel.internal", 636, True)
        self.assertTrue(client.test_connection()["success"])
        self.assertEqual(client.search_users("DC=hotel,DC=internal").items, [])
        self.assertTrue(client.validate_base_dn("OU=Users,DC=hotel,DC=internal"))
        self.assertFalse(client.validate_base_dn("invalid"))

    def test_epic_3b_service_methods_are_explicit_stubs(self):
        sync = ActiveDirectorySyncService(MagicMock())
        matching = ActiveDirectoryMatchingService(MagicMock())
        for operation in (
            sync.stage_directory_object,
            sync.finalize_sync_run,
            sync.mark_missing_objects,
            matching.generate_user_candidates,
            matching.generate_device_candidates,
            matching.resolve_candidate,
        ):
            with self.assertRaises(NotImplementedError):
                operation()

    def test_ad_settings_are_safe_and_disabled(self):
        self.assertFalse(settings.active_directory_enabled)
        self.assertTrue(settings.ad_tls_verification_required)
        self.assertFalse(settings.ad_allow_insecure_ldap)
        self.assertLessEqual(settings.ad_default_page_size, settings.ad_maximum_page_size)

    def test_migration_chain_upgrade_downgrade_and_constraints(self):
        path = (
            Path(__file__).parents[1]
            / "alembic"
            / "versions"
            / "e8a9b0c1d2e3_add_active_directory_foundation.py"
        )
        spec = importlib.util.spec_from_file_location("ad_migration", path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        self.assertEqual(module.down_revision, "d4f2a7c8e901")
        source = path.read_text(encoding="utf-8")
        self.assertEqual(source.count("op.create_table("), 5)
        self.assertEqual(source.count("op.drop_table("), 5)
        self.assertIn("ck_ad_candidate_typed_target", source)
        self.assertIn("ck_ad_sync_run_nonnegative_counts", source)


if __name__ == "__main__":
    unittest.main()
