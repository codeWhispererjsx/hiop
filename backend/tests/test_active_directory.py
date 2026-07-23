import unittest
import uuid
from unittest.mock import patch

from pydantic import ValidationError

from app.models.active_directory import (
    ActiveDirectoryConnection,
    ActiveDirectoryMatchCandidate,
    ActiveDirectoryObject,
    ActiveDirectorySyncConfiguration,
    ActiveDirectorySyncRun,
    ADAuthenticationMethod,
    ADConflictPolicy,
)
from app.schemas.active_directory import (
    ActiveDirectoryConnectionCreate,
    ActiveDirectoryConnectionRead,
    ActiveDirectoryConnectionUpdate,
)
from app.services.active_directory_secret_service import (
    ActiveDirectorySecretError,
    ActiveDirectorySecretService,
)
from app.services.ldap_client import MockLdapClient


class TestActiveDirectorySecretService(unittest.TestCase):
    def test_encrypt_and_decrypt_secret(self):
        plaintext = "SuperSecretBindPassword123!"
        encrypted = ActiveDirectorySecretService.encrypt_secret(plaintext)
        self.assertIsNotNone(encrypted)
        self.assertNotEqual(encrypted, plaintext)

        decrypted = ActiveDirectorySecretService.decrypt_secret(encrypted)
        self.assertEqual(decrypted, plaintext)

    def test_empty_secret_raises(self):
        with self.assertRaises(ActiveDirectorySecretError):
            ActiveDirectorySecretService.encrypt_secret("")

        with self.assertRaises(ActiveDirectorySecretError):
            ActiveDirectorySecretService.decrypt_secret("")

    def test_invalid_token_raises(self):
        with self.assertRaises(ActiveDirectorySecretError):
            ActiveDirectorySecretService.decrypt_secret("invalid-ciphertext-string")

    @patch("app.services.active_directory_secret_service.os.getenv", return_value=None)
    @patch("app.services.active_directory_secret_service.settings")
    def test_missing_encryption_key_raises(self, mock_settings, mock_getenv):
        mock_settings.SECRET_KEY = None
        with self.assertRaises(ActiveDirectorySecretError):
            ActiveDirectorySecretService.encrypt_secret("some_secret")


class TestActiveDirectorySchemas(unittest.TestCase):
    def test_valid_connection_create_schema(self):
        payload = {
            "name": "Primary Hotel AD",
            "domain_name": "hotel.internal",
            "server_host": "dc01.hotel.internal",
            "server_port": 636,
            "use_ssl": True,
            "base_dn": "DC=hotel,DC=internal",
            "bind_username": "cn=binder,dc=hotel,dc=internal",
            "bind_secret": "secret123",
        }
        schema = ActiveDirectoryConnectionCreate(**payload)
        self.assertEqual(schema.domain_name, "hotel.internal")
        self.assertEqual(schema.server_port, 636)

    def test_invalid_domain_name_raises(self):
        payload = {
            "name": "Invalid Domain AD",
            "domain_name": "invalid domain name with spaces",
            "server_host": "dc01.hotel.internal",
            "base_dn": "DC=hotel,DC=internal",
        }
        with self.assertRaises(ValidationError):
            ActiveDirectoryConnectionCreate(**payload)

    def test_invalid_port_raises(self):
        payload = {
            "name": "Invalid Port AD",
            "domain_name": "hotel.internal",
            "server_host": "dc01.hotel.internal",
            "server_port": 999999,
            "base_dn": "DC=hotel,DC=internal",
        }
        with self.assertRaises(ValidationError):
            ActiveDirectoryConnectionCreate(**payload)

    def test_read_schema_excludes_secret(self):
        conn_dict = {
            "id": str(uuid.uuid4()),
            "name": "Hotel AD",
            "domain_name": "hotel.internal",
            "server_host": "dc01.hotel.internal",
            "server_port": 389,
            "use_ssl": False,
            "use_start_tls": False,
            "base_dn": "DC=hotel,DC=internal",
            "user_search_base": "OU=Users,DC=hotel,DC=internal",
            "computer_search_base": None,
            "group_search_base": None,
            "bind_username": "binder",
            "has_bind_secret": True,
            "authentication_method": "simple",
            "connection_timeout_seconds": 10,
            "page_size": 500,
            "enabled": True,
            "verify_tls": True,
            "ca_certificate_reference": None,
            "last_tested_at": None,
            "last_test_status": None,
            "last_test_message": None,
            "created_by": None,
            "updated_by": None,
            "created_at": "2026-07-23T12:00:00Z",
            "updated_at": "2026-07-23T12:00:00Z",
        }
        schema = ActiveDirectoryConnectionRead(**conn_dict)
        data = schema.model_dump()
        self.assertNotIn("bind_secret", data)
        self.assertNotIn("encrypted_bind_secret", data)
        self.assertTrue(data["has_bind_secret"])


class TestMockLdapClient(unittest.TestCase):
    def test_mock_client_operations(self):
        client = MockLdapClient(host="dc01.hotel.internal", port=636, use_ssl=True)
        res = client.test_connection()
        self.assertTrue(res["success"])
        self.assertEqual(res["host"], "dc01.hotel.internal")

        self.assertTrue(client.bind("cn=admin", "password"))
        self.assertEqual(client.search_users("DC=hotel,DC=internal"), [])
        self.assertEqual(client.search_computers("DC=hotel,DC=internal"), [])
        self.assertEqual(client.search_groups("DC=hotel,DC=internal"), [])
        self.assertTrue(client.validate_base_dn("OU=Users,DC=hotel,DC=internal"))
        self.assertFalse(client.validate_base_dn("invalid_base_dn"))
        client.unbind()
        self.assertFalse(client.bound)


if __name__ == "__main__":
    unittest.main()
