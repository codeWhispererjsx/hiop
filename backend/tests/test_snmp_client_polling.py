"""Mock-only Epic 4B SNMP transport and lifecycle verification."""
import os
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from pysnmp.proto import rfc1902, rfc1905

from app.services.snmp_client_service import (
    SYSTEM_OIDS, PySNMPAdapter, SecureSNMPClient, SNMPClientError,
    classify_error, parse_value,
)
from app.services.snmp_polling_service import SNMPPollingService
from app.services.snmp_runtime import snmp_operation_lock
from app.services.snmp_secret_service import SNMPSecretService


def target(version="v2c", **kwargs):
    values = dict(
        id=uuid.uuid4(), credential_id=uuid.uuid4(), enabled=True,
        version=version, ip_address="10.50.20.10", hostname=None, port=161,
        timeout_seconds=2, retries=1, context_name="",
    )
    values.update(kwargs)
    return SimpleNamespace(**values)


def credential(version="v2c", **kwargs):
    with patch.dict(os.environ, {"HIOP_SNMP_SECRET_KEY": "unit-test-only-key"}):
        values = dict(
            id=uuid.uuid4(), enabled=True, version=version,
            community_encrypted=SNMPSecretService.encrypt_secret("placeholder-community") if version != "v3" else None,
            username="monitor" if version == "v3" else None,
            authentication_protocol="none", authentication_secret_encrypted=None,
            privacy_protocol="none", privacy_secret_encrypted=None,
            security_level="noAuthNoPriv",
        )
    values.update(kwargs)
    return SimpleNamespace(**values)


class FakeAdapter:
    def __init__(self, *, bindings=None, error=None, status=None, walks=None):
        self.bindings = bindings or []
        self.error, self.status = error, status
        self.walks = walks or []
        self.auth_calls = []
        self.bulk_flags = []
        self.closed = False

    def auth_data(self, cred, community, auth, privacy):
        self.auth_calls.append((cred.version, community, auth, privacy))
        return object()

    async def target(self, host, port, timeout, retries):
        return (host, port, timeout, retries)

    async def get(self, auth, target_value, context, oids):
        return self.error, self.status, 0, self.bindings

    async def walk(self, auth, target_value, context, root, bulk, max_repetitions):
        self.bulk_flags.append(bulk)
        for response in self.walks:
            yield response

    def close(self):
        self.closed = True


def client(adapter, version="v2c", cred=None, target_row=None):
    return SecureSNMPClient(
        target_row or target(version), cred or credential(version), adapter=adapter,
        resolver=lambda _: ["10.50.20.10"], authorized_networks=["10.50.20.0/24"],
    )


class ParsingTests(unittest.TestCase):
    def test_integer(self): self.assertEqual(parse_value("1.2", rfc1902.Integer32(7)).value_numeric, 7)
    def test_counter32(self): self.assertEqual(parse_value("1.2", rfc1902.Counter32(8)).value_numeric, 8)
    def test_counter64(self): self.assertEqual(parse_value("1.2", rfc1902.Counter64(2**40)).value_numeric, 2**40)
    def test_gauge(self): self.assertEqual(parse_value("1.2", rfc1902.Gauge32(9)).value_numeric, 9)

    def test_timeticks(self):
        value = parse_value("1.2", rfc1902.TimeTicks(1234))
        self.assertEqual(value.raw_ticks, 1234)
        self.assertEqual(value.seconds, 12.34)

    def test_octet_string(self): self.assertEqual(parse_value("1.2", rfc1902.OctetString("switch")).value_text, "switch")
    def test_oid(self): self.assertEqual(parse_value("1.2", rfc1902.ObjectIdentifier("1.3.6.1")).value_text, "1.3.6.1")
    def test_ip(self): self.assertEqual(parse_value("1.2", rfc1902.IpAddress("10.0.0.1")).value_text, "10.0.0.1")
    def test_null(self): self.assertEqual(parse_value("1.2", rfc1902.Null("")).quality, "missing")
    def test_no_such_object(self): self.assertEqual(parse_value("1.2", rfc1905.NoSuchObject()).quality, "missing")
    def test_no_such_instance(self): self.assertEqual(parse_value("1.2", rfc1905.NoSuchInstance()).quality, "missing")
    def test_end_of_mib(self): self.assertEqual(parse_value("1.2", rfc1905.EndOfMibView()).quality, "missing")

    def test_unknown_is_safe_text(self):
        value = parse_value("1.2", SimpleNamespace(prettyPrint=lambda: "unknown-value"))
        self.assertEqual(value.quality, "warning")
        self.assertEqual(value.value_text, "unknown-value")

    def test_giant_text_is_truncated(self):
        value = parse_value("1.2", rfc1902.OctetString("x" * 2000))
        self.assertEqual(value.quality, "truncated")
        self.assertEqual(len(value.value_text), 1000)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.key = patch.dict(os.environ, {"HIOP_SNMP_SECRET_KEY": "unit-test-only-key"})
        self.key.start()
        self.addCleanup(self.key.stop)

    def test_scalar_get_success(self):
        adapter = FakeAdapter(bindings=[(rfc1902.ObjectName("1.3.6.1"), rfc1902.Integer32(4))])
        self.assertEqual(client(adapter).get("1.3.6.1").value_numeric, 4)

    def test_multi_get_preserves_order_and_missing(self):
        adapter = FakeAdapter(bindings=[(rfc1902.ObjectName("1.3.6.2"), rfc1902.Integer32(2))])
        values = client(adapter).get_many(["1.3.6.1", "1.3.6.2"])
        self.assertEqual([value.quality for value in values], ["missing", "good"])

    def test_multi_get_deduplicates(self):
        adapter = FakeAdapter(bindings=[(rfc1902.ObjectName("1.3.6.1"), rfc1902.Integer32(1))])
        values = client(adapter).get_many(["1.3.6.1", "1.3.6.1"])
        self.assertEqual(len(values), 1)

    def test_timeout_classification(self):
        with self.assertRaises(SNMPClientError) as caught:
            client(FakeAdapter(error="No SNMP response received before timeout")).get("1.3.6.1")
        self.assertEqual(caught.exception.category, "timeout")
        self.assertTrue(caught.exception.retryable)

    def test_authentication_failure_classification(self):
        self.assertEqual(classify_error("wrong digest").category, "authentication_failed")

    def test_privacy_failure_classification(self):
        self.assertEqual(classify_error("decryption error").category, "privacy_failed")

    def test_public_target_blocked(self):
        snmp = SecureSNMPClient(
            target(), credential(), adapter=FakeAdapter(),
            resolver=lambda _: ["8.8.8.8"], authorized_networks=["0.0.0.0/0"],
        )
        with self.assertRaises(SNMPClientError) as caught: snmp.get("1.3.6.1")
        self.assertEqual(caught.exception.category, "unauthorized_target")

    def test_ignored_range_blocked(self):
        snmp = SecureSNMPClient(
            target(), credential(), adapter=FakeAdapter(),
            resolver=lambda _: ["10.50.20.10"], authorized_networks=["10.50.20.0/24"],
            ignored_networks=["10.50.20.0/28"],
        )
        with self.assertRaises(SNMPClientError) as caught: snmp.get("1.3.6.1")
        self.assertEqual(caught.exception.category, "unauthorized_target")

    def test_disabled_target_and_credential(self):
        with self.assertRaises(SNMPClientError):
            client(FakeAdapter(), target_row=target(enabled=False)).get("1.3.6.1")
        with self.assertRaises(SNMPClientError):
            client(FakeAdapter(), cred=credential(enabled=False)).get("1.3.6.1")

    def test_decryption_failure_is_safe(self):
        cred = credential()
        cred.community_encrypted = "not-ciphertext"
        with self.assertRaises(SNMPClientError) as caught: client(FakeAdapter(), cred=cred).get("1.3.6.1")
        self.assertEqual(caught.exception.category, "decryption_failed")
        self.assertNotIn("not-ciphertext", str(caught.exception))

    def test_v1_v2c_and_v3_pass_correct_version_to_adapter(self):
        with patch("app.services.snmp_client_service.settings.snmp_allow_v1", True):
            for version in ("v1", "v2c", "v3"):
                adapter = FakeAdapter(bindings=[(rfc1902.ObjectName("1.3.6.1"), rfc1902.Integer32(1))])
                client(adapter, version).get("1.3.6.1")
                self.assertEqual(adapter.auth_calls[0][0], version)

    def test_walk_stops_at_subtree_exit(self):
        adapter = FakeAdapter(walks=[
            (None, 0, 0, [(rfc1902.ObjectName("1.3.6.1.1"), rfc1902.Integer32(1))]),
            (None, 0, 0, [(rfc1902.ObjectName("1.3.7.1"), rfc1902.Integer32(2))]),
        ])
        result = client(adapter).walk("1.3.6.1")
        self.assertEqual(len(result.items), 1)

    def test_walk_row_limit(self):
        adapter = FakeAdapter(walks=[(None, 0, 0, [
            (rfc1902.ObjectName("1.3.6.1.1"), rfc1902.Integer32(1)),
            (rfc1902.ObjectName("1.3.6.1.2"), rfc1902.Integer32(2)),
        ])])
        result = client(adapter).walk("1.3.6.1", max_rows=1)
        self.assertTrue(result.truncated)

    def test_walk_repeated_oid_protection(self):
        response = (None, 0, 0, [(rfc1902.ObjectName("1.3.6.1.1"), rfc1902.Integer32(1))])
        result = client(FakeAdapter(walks=[response, response])).walk("1.3.6.1")
        self.assertTrue(result.truncated)
        self.assertIn("Repeated", result.warning)

    def test_walk_cancellation(self):
        adapter = FakeAdapter(walks=[(None, 0, 0, [(rfc1902.ObjectName("1.3.6.1.1"), rfc1902.Integer32(1))])])
        with self.assertRaises(SNMPClientError) as caught:
            client(adapter).walk("1.3.6.1", cancelled=lambda: True)
        self.assertEqual(caught.exception.category, "cancelled")

    def test_bulk_walk_v2c_and_v3(self):
        for version in ("v2c", "v3"):
            adapter = FakeAdapter()
            client(adapter, version).bulk_walk("1.3.6.1")
            self.assertTrue(adapter.bulk_flags[0])

    def test_v1_bulk_falls_back_to_walk(self):
        adapter = FakeAdapter()
        with patch("app.services.snmp_client_service.settings.snmp_allow_v1", True):
            client(adapter, "v1").bulk_walk("1.3.6.1")
        self.assertFalse(adapter.bulk_flags[0])

    def test_system_identity_uses_standard_oids(self):
        bindings = [(rfc1902.ObjectName(oid), rfc1902.OctetString(key)) for key, oid in SYSTEM_OIDS.items()]
        result = client(FakeAdapter(bindings=bindings)).get_system_identity()
        self.assertEqual(set(result), set(SYSTEM_OIDS))


class ProtocolMappingTests(unittest.TestCase):
    def test_pysnmp_protocol_mapping_available(self):
        adapter = PySNMPAdapter()
        try:
            for name in ("SHA", "SHA256", "SHA384", "SHA512"):
                cred = credential("v3", authentication_protocol=name)
                self.assertIsNotNone(adapter.auth_data(cred, None, "placeholder-auth", None))
            for name in ("AES128", "AES192", "AES256"):
                cred = credential("v3", authentication_protocol="SHA", privacy_protocol=name)
                self.assertIsNotNone(adapter.auth_data(cred, None, "placeholder-auth", "placeholder-privacy"))
        finally:
            adapter.close()

    def test_unsupported_protocol_rejected(self):
        adapter = PySNMPAdapter()
        try:
            cred = credential("v3", authentication_protocol="UNSUPPORTED")
            with self.assertRaises(SNMPClientError): adapter.auth_data(cred, None, "secret", None)
        finally:
            adapter.close()


class LifecycleAndConcurrencyTests(unittest.TestCase):
    def test_valid_transitions(self):
        run = SimpleNamespace(status="pending")
        SNMPPollingService.transition(run, "running")
        SNMPPollingService.transition(run, "completed")
        self.assertEqual(run.status, "completed")

    def test_invalid_transition(self):
        with self.assertRaises(HTTPException):
            SNMPPollingService.transition(SimpleNamespace(status="completed"), "running")

    def test_duplicate_target_lock_blocked(self):
        target_id, credential_id = uuid.uuid4(), uuid.uuid4()
        with snmp_operation_lock(target_id, credential_id):
            with self.assertRaises(SNMPClientError):
                with snmp_operation_lock(target_id, uuid.uuid4()):
                    pass

    def test_duplicate_credential_lock_blocked(self):
        target_id, credential_id = uuid.uuid4(), uuid.uuid4()
        with snmp_operation_lock(target_id, credential_id):
            with self.assertRaises(SNMPClientError):
                with snmp_operation_lock(uuid.uuid4(), credential_id):
                    pass


if __name__ == "__main__":
    unittest.main()
