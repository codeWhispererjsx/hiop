import ssl
import unittest
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.core.rate_limit import OperationRateLimiter
from app.main import app
from app.models.active_directory import ActiveDirectoryConnection
from app.services.active_directory_service import ActiveDirectoryConnectionService
from app.services.ldap_client import (
    COMPUTER_FILTER,
    GROUP_FILTER,
    USER_FILTER,
    LdapClientConfig,
    LdapError,
    MockLdapClient,
    SecureLdapClient,
    account_enabled,
    build_search_filter,
    classify_ldap_error,
    convert_entry,
    convert_filetime,
    convert_group_type,
    convert_guid,
    convert_sid,
    dn_within,
    escape_filter_value,
)


def client_config(**overrides):
    values = {
        "connection_id": "connection-1",
        "host": "dc01.hotel.internal",
        "port": 636,
        "use_ssl": True,
        "use_start_tls": False,
        "verify_tls": True,
        "ca_certificate_reference": None,
        "authentication_method": "simple",
        "connect_timeout": 5,
        "search_timeout": 10,
        "page_size": 2,
        "maximum_page_size": 100,
        "maximum_objects": 10,
        "domain_name": "hotel.internal",
        "environment": "production",
        "allow_insecure_ldap": False,
        "approved_hosts": (),
        "allow_public_hosts": False,
        "retry_count": 1,
    }
    values.update(overrides)
    return LdapClientConfig(**values)


class FakeEntry:
    def __init__(self, attributes, raw=None):
        self.entry_attributes_as_dict = attributes
        self.entry_raw_attributes = raw or {}


class PagingConnection:
    def __init__(self):
        self.entries = []
        self.result = {}
        self.calls = []

    def search(self, base, search_filter, scope, **kwargs):
        self.calls.append((base, search_filter, kwargs))
        cookie = kwargs.get("paged_cookie")
        if cookie is None:
            self.entries = [
                FakeEntry({
                    "objectGUID": str(uuid.uuid4()),
                    "distinguishedName": "CN=Alice,OU=Users,DC=hotel,DC=internal",
                    "sAMAccountName": "alice",
                    "userAccountControl": 512,
                }),
                FakeEntry({
                    "objectGUID": str(uuid.uuid4()),
                    "distinguishedName": "CN=Bob,OU=Users,DC=hotel,DC=internal",
                    "sAMAccountName": "bob",
                    "userAccountControl": 514,
                }),
            ]
            next_cookie = b"page-2"
        else:
            self.entries = [
                FakeEntry({
                    "objectGUID": str(uuid.uuid4()),
                    "distinguishedName": "CN=Carol,OU=Users,DC=hotel,DC=internal",
                    "sAMAccountName": "carol",
                    "userAccountControl": 512,
                })
            ]
            next_cookie = b""
        self.result = {
            "controls": {
                "1.2.840.113556.1.4.319": {"value": {"cookie": next_cookie}}
            }
        }
        return True

    def unbind(self):
        return True


class LdapModeAndPolicyTests(unittest.TestCase):
    def test_ldaps_starttls_and_explicit_development_ldap(self):
        SecureLdapClient(client_config())
        SecureLdapClient(client_config(use_ssl=False, use_start_tls=True, port=389))
        SecureLdapClient(client_config(
            use_ssl=False,
            use_start_tls=False,
            environment="development",
            allow_insecure_ldap=True,
            port=389,
        ))

    def test_insecure_production_tls_bypass_and_public_host_are_rejected(self):
        invalid = [
            {"use_ssl": False, "use_start_tls": False, "port": 389},
            {"verify_tls": False},
            {"host": "ldap.example.com", "domain_name": "hotel.internal"},
            {"host": "ldap://dc01.hotel.internal"},
        ]
        for overrides in invalid:
            with self.subTest(overrides=overrides), self.assertRaises(LdapError):
                SecureLdapClient(client_config(**overrides))

    def test_tls_object_requires_certificate_validation(self):
        client = SecureLdapClient(client_config())
        tls = client._tls()
        self.assertEqual(tls.validate, ssl.CERT_REQUIRED)


class LdapFilterAndDnTests(unittest.TestCase):
    def test_fixed_filters_exclude_computers_from_users(self):
        self.assertIn("(!(objectClass=computer))", USER_FILTER)
        self.assertIn("objectCategory=computer", COMPUTER_FILTER)
        self.assertIn("objectCategory=group", GROUP_FILTER)

    def test_filter_escaping_blocks_injection_and_raw_wildcards(self):
        escaped = escape_filter_value("alice)(uid=admin)")
        self.assertNotIn(")(|", escaped)
        built = build_search_filter("user", search_term="alice)(uid=admin)")
        self.assertIn("\\29", built)
        with self.assertRaises(LdapError):
            escape_filter_value("ali*")
        with self.assertRaises(LdapError):
            build_search_filter("user", search_term="alice", search_attribute="userPassword")

    def test_search_base_must_remain_inside_root(self):
        self.assertTrue(dn_within("OU=Users,DC=hotel,DC=internal", "DC=hotel,DC=internal"))
        self.assertFalse(dn_within("OU=Users,DC=outside,DC=internal", "DC=hotel,DC=internal"))
        self.assertFalse(dn_within("not-a-dn", "DC=hotel,DC=internal"))


class LdapConversionTests(unittest.TestCase):
    def test_guid_sid_filetime_and_account_flags(self):
        identifier = uuid.uuid4()
        self.assertEqual(convert_guid(identifier.bytes_le), str(identifier))
        sid = bytes([1, 2]) + (5).to_bytes(6, "big") + (21).to_bytes(4, "little") + (42).to_bytes(4, "little")
        self.assertEqual(convert_sid(sid), "S-1-5-21-42")
        self.assertIsNotNone(convert_filetime("132537600000000000"))
        self.assertIsNone(convert_filetime("bad"))
        self.assertTrue(account_enabled(512))
        self.assertFalse(account_enabled(514))

    def test_user_computer_and_group_conversion(self):
        guid = uuid.uuid4()
        raw = {"objectGUID": [guid.bytes_le]}
        user = convert_entry("user", {
            "distinguishedName": "CN=Alice,OU=Front Office,DC=hotel,DC=internal",
            "sAMAccountName": "alice",
            "userAccountControl": 514,
            "memberOf": ["CN=Staff,DC=hotel,DC=internal"],
        }, raw)
        self.assertFalse(user["enabled"])
        self.assertEqual(user["organizational_unit"], "Front Office")
        computer = convert_entry("computer", {
            "distinguishedName": "CN=PC01,OU=Computers,DC=hotel,DC=internal",
            "dNSHostName": "PC01.HOTEL.INTERNAL",
            "userAccountControl": 512,
        }, raw)
        self.assertEqual(computer["dns_hostname"], "pc01.hotel.internal")
        group = convert_entry("group", {
            "distinguishedName": "CN=Staff,OU=Groups,DC=hotel,DC=internal",
            "groupType": -2147483646,
            "member": ["a", "b", "c"],
        }, raw, include_members=True, member_limit=2)
        self.assertTrue(group["group_type"]["security"])
        self.assertTrue(group["members_truncated"])
        self.assertEqual(group["members"], ["a", "b"])

    def test_malformed_attributes_do_not_crash_object(self):
        result = convert_entry("user", {
            "distinguishedName": "CN=Broken,DC=hotel,DC=internal",
            "lastLogonTimestamp": "bad",
        })
        self.assertIsNone(result["object_guid"])
        self.assertTrue(result["parse_warnings"])


class LdapPagingAndErrorsTests(unittest.TestCase):
    def test_active_directory_paging_and_limit(self):
        client = SecureLdapClient(client_config(page_size=2, maximum_objects=5))
        client.connection = PagingConnection()
        result = client.search_users("DC=hotel,DC=internal", limit=5)
        self.assertEqual(len(result.items), 3)
        self.assertEqual(result.page_count, 2)
        self.assertFalse(result.truncated)
        self.assertFalse(client.connection.calls[0][2]["paged_cookie"])

    def test_query_limit_reports_truncation(self):
        client = SecureLdapClient(client_config(page_size=2, maximum_objects=2))
        client.connection = PagingConnection()
        result = client.search_users("DC=hotel,DC=internal", limit=2)
        self.assertTrue(result.truncated)
        self.assertTrue(result.warnings)

    def test_error_categories_and_retry_policy(self):
        self.assertEqual(classify_ldap_error(Exception("invalid credentials")).category, "bind_failed")
        self.assertEqual(classify_ldap_error(Exception("certificate verify failed")).category, "certificate_invalid")
        timeout = classify_ldap_error(Exception("socket timed out"))
        self.assertEqual(timeout.category, "timeout")
        self.assertTrue(timeout.retryable)
        self.assertFalse(classify_ldap_error(Exception("insufficient access")).retryable)


class ConnectionWorkflowTests(unittest.TestCase):
    def connection(self):
        now = datetime.now(timezone.utc)
        return ActiveDirectoryConnection(
            id=str(uuid.uuid4()),
            name="Test AD",
            domain_name="example.invalid",
            server_host="dc.example.invalid",
            server_port=636,
            use_ssl=True,
            use_start_tls=False,
            base_dn="DC=example,DC=invalid",
            user_search_base="OU=Users,DC=example,DC=invalid",
            computer_search_base="OU=Computers,DC=example,DC=invalid",
            group_search_base="OU=Groups,DC=example,DC=invalid",
            bind_username=None,
            encrypted_bind_secret=None,
            authentication_method="anonymous",
            connection_timeout_seconds=5,
            page_size=25,
            enabled=True,
            verify_tls=True,
            failure_count=0,
            created_at=now,
            updated_at=now,
        )

    @patch("app.services.active_directory_service.create_audit_log")
    def test_structured_connection_test_and_health_update(self, audit):
        connection = self.connection()
        db = MagicMock()
        service = ActiveDirectoryConnectionService(
            db,
            client_factory=lambda config: MockLdapClient(config.host, config.port, config.use_ssl),
        )
        service.repo = SimpleNamespace(get=lambda _: connection)
        result = service.test_connection(connection.id, SimpleNamespace(id="admin", username="admin"))
        self.assertEqual(result["overall_status"], "success")
        self.assertTrue(any(stage["name"] == "root_dse" for stage in result["stages"]))
        self.assertEqual(connection.last_test_status, "success")
        self.assertEqual(connection.failure_count, 0)
        self.assertGreaterEqual(audit.call_count, 2)
        self.assertNotIn("secret", str(result).lower())

    @patch("app.services.active_directory_service.create_audit_log")
    def test_preview_is_bounded_and_disabled_connection_is_rejected(self, _audit):
        connection = self.connection()
        service = ActiveDirectoryConnectionService(
            MagicMock(),
            client_factory=lambda config: MockLdapClient(config.host, config.port, config.use_ssl),
        )
        service.repo = SimpleNamespace(get=lambda _: connection)
        result = service.preview(
            connection.id, "users", SimpleNamespace(username="admin"),
            limit=10, search_term="alice", enabled=True,
        )
        self.assertEqual(result["object_type"], "user")
        connection.enabled = False
        with self.assertRaises(HTTPException) as denied:
            service.preview(connection.id, "users", SimpleNamespace(username="admin"), limit=10)
        self.assertEqual(denied.exception.status_code, 409)

    def test_routes_are_admin_only_and_rate_limited(self):
        paths = app.openapi()["paths"]
        expected = {
            "/api/v1/active-directory/connections/{id}/root-dse",
            "/api/v1/active-directory/connections/{id}/preview/users",
            "/api/v1/active-directory/connections/{id}/preview/computers",
            "/api/v1/active-directory/connections/{id}/preview/groups",
        }
        self.assertTrue(expected.issubset(paths))
        for route in app.routes:
            if getattr(route, "path", None) not in expected:
                continue
            role = next(dep.call for dep in route.dependant.dependencies if getattr(dep.call, "__name__", "") == "role_checker")
            with self.assertRaises(HTTPException):
                role(current_user=SimpleNamespace(role="technician"))
        limiter = OperationRateLimiter(limit=1, window_seconds=60)
        limiter.check("admin:connection")
        with self.assertRaises(HTTPException) as limited:
            limiter.check("admin:connection")
        self.assertEqual(limited.exception.status_code, 429)


if __name__ == "__main__":
    unittest.main()
