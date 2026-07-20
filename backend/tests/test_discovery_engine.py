import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.discovery.fingerprinting import fingerprint, lookup_vendor
from app.discovery.network import (
    ensure_authorized,
    inspect_arp_table,
    normalize_mac,
    parse_networks,
)
from app.models.discovered_device import DiscoveryStatus, RunStatus
from app.services.discovery_service import DiscoveryService


CONFIG = {
    "enabled": True,
    "authorized_cidr_ranges": "10.20.30.0/24",
    "ignore_ranges": "10.20.30.2/32",
    "ping_timeout_seconds": 1,
    "concurrency_limit": 2,
    "max_hosts_per_run": 16,
    "automatic_vendor_lookup": True,
    "automatic_hostname_lookup": True,
}


class FakeRunRepository:
    def __init__(self):
        self.items = []

    def add(self, run):
        self.items.append(run)
        return run

    def get(self, run_id):
        return next((run for run in self.items if run.id == run_id), None)

    def list(self, *, offset=0, limit=100):
        return self.items[offset:offset + limit]

    def latest(self):
        return self.items[-1] if self.items else None

    def count(self):
        return len(self.items)


class DiscoveryNetworkTests(unittest.TestCase):
    def test_cidr_validation_rejects_public_and_unauthorized_ranges(self):
        with self.assertRaisesRegex(ValueError, "private"):
            parse_networks("8.8.8.0/24")
        with self.assertRaisesRegex(ValueError, "outside"):
            ensure_authorized("10.21.0.0/24", "10.20.0.0/16", max_hosts=256)
        with self.assertRaisesRegex(ValueError, "host discovery limit"):
            ensure_authorized("10.20.0.0/24", "10.20.0.0/16", max_hosts=100)

    def test_ignore_ranges_and_canonical_cidr_are_returned(self):
        network, ignored = ensure_authorized(
            "10.20.30.5/30", "10.20.30.0/24", "10.20.30.4/32", max_hosts=4
        )
        self.assertEqual(str(network), "10.20.30.4/30")
        self.assertEqual(str(ignored[0]), "10.20.30.4/32")

    def test_mac_normalization_and_passive_arp_parsing(self):
        output = "  10.20.30.1          00-00-0C-AA-BB-CC     dynamic\n"
        completed = subprocess.CompletedProcess(["arp", "-a"], 0, output, "")
        with patch("app.discovery.network.subprocess.run", return_value=completed) as run:
            entries = inspect_arp_table()
        self.assertEqual(entries, {"10.20.30.1": "00:00:0c:aa:bb:cc"})
        self.assertFalse(run.call_args.kwargs["shell"])
        self.assertEqual(normalize_mac("00000CAABBCC"), "00:00:0c:aa:bb:cc")


class DiscoveryFingerprintTests(unittest.TestCase):
    def test_vendor_and_fingerprint_are_hints_not_certainty(self):
        vendor = lookup_vendor("00:00:0c:aa:bb:cc")
        result = fingerprint("switch-lobby", vendor)
        self.assertEqual(vendor, "Cisco")
        self.assertEqual(result.device_type_guess, "switch")
        self.assertLess(result.confidence_score, 100)

    def test_unknown_fingerprint_has_low_confidence(self):
        result = fingerprint(None, None)
        self.assertEqual(result.device_type_guess, "unknown")
        self.assertLessEqual(result.confidence_score, 25)


class DiscoveryServiceTests(unittest.TestCase):
    def test_matching_priority_prefers_mac_over_approved_device_and_ip(self):
        db = MagicMock()
        service = DiscoveryService(db, config=CONFIG)
        expected = object()
        service.devices = MagicMock()
        service.devices.find_by_mac.return_value = expected
        matched = service.match_observation({
            "ip_address": "10.20.30.1",
            "mac_address": "00:00:0c:aa:bb:cc",
            "approved_device_id": uuid4(),
            "hostname": "switch-lobby",
        })
        self.assertIs(matched, expected)
        service.devices.find_by_approved_device.assert_not_called()
        service.devices.find_by_ip_hostname.assert_not_called()

    def test_duplicate_observation_updates_history_in_place(self):
        db = MagicMock()
        service = DiscoveryService(db, config=CONFIG)
        existing = SimpleNamespace(
            ip_address="10.20.30.1", mac_address="00:00:0c:aa:bb:cc",
            hostname=None, vendor=None, operating_system_guess=None,
            device_type_guess="unknown", subnet="10.20.30.0/30",
            discovery_method="icmp", response_time=2.0,
            status=DiscoveryStatus.ONLINE, confidence_score=15.0,
            approved_device_id=None, network_zone_id=None, times_seen=1,
            last_seen_at=None,
        )
        service._inventory_match = MagicMock(return_value=None)
        service.match_observation = MagicMock(return_value=existing)
        device, is_new, inventory_matched = service._record_observation({
            "ip_address": "10.20.30.1",
            "mac_address": "00-00-0C-AA-BB-CC",
            "hostname": "switch-lobby",
            "status": DiscoveryStatus.ONLINE,
        })
        self.assertIs(device, existing)
        self.assertFalse(is_new)
        self.assertFalse(inventory_matched)
        self.assertEqual(existing.times_seen, 2)
        self.assertEqual(existing.mac_address, "00:00:0c:aa:bb:cc")

    def test_discover_range_honors_ignore_range_and_records_history(self):
        db = MagicMock()
        probes = []

        def probe(address, timeout):
            probes.append(address)
            return True, 1.5

        service = DiscoveryService(
            db,
            config={**CONFIG, "authorized_cidr_ranges": "10.20.30.0/30"},
            probe=probe,
            arp_reader=lambda: {"10.20.30.1": "00:00:0c:aa:bb:cc"},
            resolver=lambda address, timeout: "switch-lobby" if address.endswith(".1") else None,
        )
        service.runs = FakeRunRepository()
        service._record_observation = MagicMock(
            return_value=(SimpleNamespace(), True, False)
        )
        run = service.discover_range("10.20.30.0/30")
        self.assertEqual(probes, ["10.20.30.1"])
        self.assertEqual(run.status, RunStatus.COMPLETED)
        self.assertEqual(run.hosts_attempted, 1)
        self.assertEqual(run.hosts_responded, 1)
        self.assertEqual(run.new_devices, 1)
        db.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
