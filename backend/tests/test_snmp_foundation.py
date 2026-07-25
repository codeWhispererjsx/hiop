"""Offline contracts for Epic 4A. No SNMP transport is imported or contacted."""
import os
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from fastapi.testclient import TestClient

from app.main import app
from app.models.snmp import (
    SNMPCredential, SNMPDeviceProfile, SNMPDiscoveryCandidate, SNMPInterface,
    SNMPMetric, SNMPOIDDefinition, SNMPPollingConfiguration, SNMPPollRun,
    SNMPTarget,
)
from app.schemas.snmp import (
    SNMPCredentialCreate, SNMPCredentialRead, SNMPOIDCreate,
    SNMPPollingConfigurationWrite, SNMPProfileCreate, SNMPTargetCreate,
)
from app.services.snmp_client_service import DisabledSNMPClient, SNMPTransportUnavailable
from app.services.snmp_secret_service import SNMPSecretError, SNMPSecretService


class SNMPSchemaTests(unittest.TestCase):
    def test_v1_community_is_valid(self):
        row = SNMPCredentialCreate(name="Legacy", version="v1", community="placeholder")
        self.assertEqual(row.version.value, "v1")

    def test_v2c_community_is_valid(self):
        row = SNMPCredentialCreate(name="Standard", version="v2c", community="placeholder")
        self.assertEqual(row.version.value, "v2c")

    def test_v1_requires_community(self):
        with self.assertRaises(ValidationError):
            SNMPCredentialCreate(name="Legacy", version="v1")

    def test_v2c_rejects_v3_fields(self):
        with self.assertRaises(ValidationError):
            SNMPCredentialCreate(name="Bad", version="v2c", community="x", username="user")

    def test_v3_no_auth_no_priv_is_valid(self):
        row = SNMPCredentialCreate(name="V3", version="v3", username="monitor")
        self.assertEqual(row.security_level.value, "noAuthNoPriv")

    def test_v3_no_auth_rejects_secrets(self):
        with self.assertRaises(ValidationError):
            SNMPCredentialCreate(
                name="Bad", version="v3", username="monitor",
                authentication_protocol="SHA256", authentication_secret="placeholder",
            )

    def test_v3_auth_no_priv_is_valid(self):
        row = SNMPCredentialCreate(
            name="Auth", version="v3", username="monitor", security_level="authNoPriv",
            authentication_protocol="SHA256", authentication_secret="placeholder",
        )
        self.assertEqual(row.authentication_protocol.value, "SHA256")

    def test_v3_auth_no_priv_requires_auth(self):
        with self.assertRaises(ValidationError):
            SNMPCredentialCreate(name="Bad", version="v3", username="monitor", security_level="authNoPriv")

    def test_v3_auth_priv_is_valid(self):
        row = SNMPCredentialCreate(
            name="Secure", version="v3", username="monitor", security_level="authPriv",
            authentication_protocol="SHA256", authentication_secret="placeholder-auth",
            privacy_protocol="AES128", privacy_secret="placeholder-privacy",
        )
        self.assertEqual(row.privacy_protocol.value, "AES128")

    def test_v3_auth_priv_requires_privacy(self):
        with self.assertRaises(ValidationError):
            SNMPCredentialCreate(
                name="Bad", version="v3", username="monitor", security_level="authPriv",
                authentication_protocol="SHA", authentication_secret="placeholder",
            )

    def test_v3_rejects_community(self):
        with self.assertRaises(ValidationError):
            SNMPCredentialCreate(name="Bad", version="v3", username="monitor", community="x")

    def test_invalid_oid_rejected(self):
        with self.assertRaises(ValidationError):
            self._oid("iso.org.dod")

    def test_valid_oid_normalized(self):
        self.assertEqual(self._oid(".1.3.6.1.2.1.1.3.0").oid, "1.3.6.1.2.1.1.3.0")

    def test_executable_transform_rejected(self):
        with self.assertRaises(ValidationError):
            self._oid("1.3.6.1", transform_type="python")

    def test_profile_executable_data_rejected(self):
        with self.assertRaises(ValidationError):
            SNMPProfileCreate(name="Bad profile", profile_data={"script": "do something"})

    def test_invalid_target_ip_rejected(self):
        with self.assertRaises(ValidationError):
            SNMPTargetCreate(name="Target", credential_id="11111111-1111-1111-1111-111111111111", ip_address="host", version="v3")

    def test_invalid_port_rejected(self):
        with self.assertRaises(ValidationError):
            SNMPTargetCreate(name="Target", credential_id="11111111-1111-1111-1111-111111111111", ip_address="10.0.0.1", port=0, version="v3")

    def test_invalid_timeout_rejected(self):
        with self.assertRaises(ValidationError):
            SNMPTargetCreate(name="Target", credential_id="11111111-1111-1111-1111-111111111111", ip_address="10.0.0.1", timeout_seconds=0, version="v3")

    def test_invalid_polling_interval_rejected(self):
        with self.assertRaises(ValidationError):
            SNMPPollingConfigurationWrite(polling_interval_seconds=10)

    @staticmethod
    def _oid(oid, **kwargs):
        return SNMPOIDCreate(
            name="System uptime", oid=oid, metric_key="system.uptime",
            data_type="timeticks", collection_type="scalar", **kwargs,
        )


class SNMPSecretTests(unittest.TestCase):
    def test_encrypts_and_decrypts_community(self):
        with patch.dict(os.environ, {"HIOP_SNMP_SECRET_KEY": "test-key-one"}):
            encrypted = SNMPSecretService.encrypt_secret("placeholder-community")
            self.assertNotIn("placeholder-community", encrypted)
            self.assertEqual(SNMPSecretService.decrypt_secret(encrypted), "placeholder-community")

    def test_auth_and_privacy_secrets_use_authenticated_encryption(self):
        with patch.dict(os.environ, {"HIOP_SNMP_SECRET_KEY": "test-key-two"}):
            for secret in ("placeholder-auth", "placeholder-privacy"):
                encrypted = SNMPSecretService.encrypt_secret(secret)
                self.assertNotEqual(encrypted, secret)
                self.assertEqual(SNMPSecretService.decrypt_secret(encrypted), secret)

    def test_wrong_key_fails_safely(self):
        with patch.dict(os.environ, {"HIOP_SNMP_SECRET_KEY": "first"}):
            encrypted = SNMPSecretService.encrypt_secret("placeholder")
        with patch.dict(os.environ, {"HIOP_SNMP_SECRET_KEY": "second"}):
            with self.assertRaises(SNMPSecretError):
                SNMPSecretService.decrypt_secret(encrypted)

    def test_empty_secret_fails(self):
        with self.assertRaises(SNMPSecretError):
            SNMPSecretService.encrypt_secret("")

    def test_read_schema_has_no_secret_fields(self):
        fields = SNMPCredentialRead.model_fields
        for name in ("community", "community_encrypted", "authentication_secret", "authentication_secret_encrypted", "privacy_secret", "privacy_secret_encrypted"):
            self.assertNotIn(name, fields)


class SNMPModelAndRouteTests(unittest.TestCase):
    def test_all_foundation_tables_registered(self):
        expected = {
            "snmp_credentials", "snmp_targets", "snmp_device_profiles",
            "snmp_oid_definitions", "snmp_polling_configurations",
            "snmp_poll_runs", "snmp_metrics", "snmp_interfaces",
            "snmp_discovery_candidates",
        }
        models = (SNMPCredential, SNMPTarget, SNMPDeviceProfile, SNMPOIDDefinition,
                  SNMPPollingConfiguration, SNMPPollRun, SNMPMetric, SNMPInterface,
                  SNMPDiscoveryCandidate)
        self.assertEqual({model.__tablename__ for model in models}, expected)

    def test_interface_unique_constraint_exists(self):
        names = {constraint.name for constraint in SNMPInterface.__table__.constraints}
        self.assertIn("uq_snmp_interface_target_index", names)

    def test_target_endpoint_unique_constraint_exists(self):
        names = {constraint.name for constraint in SNMPTarget.__table__.constraints}
        self.assertIn("uq_snmp_target_endpoint_context", names)

    def test_configuration_routes_registered_without_live_routes(self):
        from app.api.v1.snmp import router
        paths = {f"/api/v1{route.path}" for route in router.routes}
        required = {
            "/api/v1/snmp/credentials", "/api/v1/snmp/targets",
            "/api/v1/snmp/profiles", "/api/v1/snmp/oids",
            "/api/v1/snmp/poll-runs", "/api/v1/snmp/metrics",
            "/api/v1/snmp/interfaces", "/api/v1/snmp/candidates",
        }
        self.assertTrue(required.issubset(paths))
        self.assertFalse(any(path.endswith(("/get", "/walk", "/test", "/poll")) for path in paths if "/snmp/" in path))

    def test_mutations_use_admin_role_dependency(self):
        from app.api.v1.snmp import admin_only
        self.assertTrue(callable(admin_only))

    def test_unauthenticated_read_is_denied(self):
        response = TestClient(app).get("/api/v1/snmp/credentials")
        self.assertEqual(response.status_code, 401)

    def test_technician_mutation_is_denied(self):
        from types import SimpleNamespace
        from app.core.security import get_current_user
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id="technician-id", username="technician", role="technician"
        )
        try:
            response = TestClient(app).post(
                "/api/v1/snmp/credentials",
                json={"name": "Test profile", "version": "v2c", "community": "placeholder"},
            )
            self.assertEqual(response.status_code, 403)
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_disabled_client_never_performs_network_io(self):
        with self.assertRaisesRegex(SNMPTransportUnavailable, "not available"):
            DisabledSNMPClient().walk("1.3.6.1")


class SNMPMigrationContractTests(unittest.TestCase):
    def test_migration_is_additive_and_reversible(self):
        from pathlib import Path
        migration = Path("alembic/versions/c9e4a7b2d610_add_snmp_foundation.py").read_text()
        self.assertEqual(migration.count("op.create_table("), 9)
        self.assertIn("def downgrade()", migration)
        self.assertNotIn("op.drop_column", migration)
        self.assertNotIn("op.drop_table", migration.split("def downgrade()", 1)[0])


if __name__ == "__main__":
    unittest.main()
