import unittest
from unittest.mock import MagicMock

from sqlalchemy import CheckConstraint

from app.models.device import Device
from app.models.hierarchy import NetworkZone
from app.models.user import User
from app.models.discovered_device import (
    DiscoveredDevice,
    DiscoveryRun,
    DiscoveryStatus,
    ReviewStatus,
    RunStatus,
)
from app.services.discovery_service import DiscoveryService


class DiscoveryModelTests(unittest.TestCase):
    def test_enum_contracts(self):
        self.assertEqual({item.value for item in DiscoveryStatus}, {"online", "offline", "unknown"})
        self.assertEqual(
            {item.value for item in ReviewStatus},
            {"pending", "approved", "ignored", "rejected"},
        )
        self.assertEqual(
            {item.value for item in RunStatus},
            {"pending", "running", "completed", "partial", "failed"},
        )

    def test_discovered_device_columns_match_foundation_contract(self):
        expected = {
            "id", "ip_address", "mac_address", "hostname", "vendor",
            "operating_system_guess", "device_type_guess", "network_zone_id",
            "subnet", "discovery_method", "first_seen_at", "last_seen_at",
            "times_seen", "response_time", "status", "review_status",
            "confidence_score", "approved_device_id", "reviewed_by",
            "reviewed_at", "notes", "created_at", "updated_at",
        }
        self.assertEqual(set(DiscoveredDevice.__table__.columns.keys()), expected)

    def test_discovery_run_columns_match_foundation_contract(self):
        expected = {
            "id", "started_at", "completed_at", "status", "range_scanned",
            "hosts_attempted", "hosts_responded", "new_devices",
            "matched_devices", "updated_devices", "error_count", "duration",
            "trigger_type", "triggered_by", "error_summary",
        }
        self.assertEqual(set(DiscoveryRun.__table__.columns.keys()), expected)

    def test_identity_priority_is_backed_by_unique_partial_indexes(self):
        indexes = {index.name: index for index in DiscoveredDevice.__table__.indexes}
        names = {
            "uq_discovered_devices_mac_identity",
            "uq_discovered_devices_approved_device_identity",
            "uq_discovered_devices_ip_hostname_identity",
            "uq_discovered_devices_ip_only_identity",
        }
        self.assertTrue(names.issubset(indexes))
        self.assertTrue(all(indexes[name].unique for name in names))
        self.assertTrue(all(indexes[name].dialect_options["postgresql"]["where"] is not None for name in names))

    def test_integrity_constraints_and_relationships_exist(self):
        constraints = {
            constraint.name
            for constraint in DiscoveredDevice.__table__.constraints
            if isinstance(constraint, CheckConstraint)
        }
        self.assertIn("ck_discovered_devices_confidence_score_range", constraints)
        self.assertIn("ck_discovered_devices_times_seen_positive", constraints)
        self.assertEqual(
            set(DiscoveredDevice.__mapper__.relationships.keys()),
            {"approved_device", "reviewer", "network_zone"},
        )
        self.assertEqual(set(DiscoveryRun.__mapper__.relationships.keys()), {"triggering_user"})

    def test_service_starts_a_validated_run(self):
        db = MagicMock()
        service = DiscoveryService(db=db, config={
            "authorized_cidr_ranges": "10.0.0.0/24",
            "ignore_ranges": "",
            "max_hosts_per_run": 256,
        })
        run = service.start_run("10.0.0.0/24", "manual")
        self.assertEqual(run.status, RunStatus.RUNNING)
        db.add.assert_called_once_with(run)


if __name__ == "__main__":
    unittest.main()
