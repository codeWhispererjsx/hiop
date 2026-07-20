import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException

from app.main import app
from app.models.audit_log import AuditLog
from app.models.device import Device
from app.models.discovered_device import DiscoveredDevice, DiscoveryStatus, ReviewStatus
from app.schemas.discovery import InventoryApproval, RejectRequest
from app.services.discovery_service import DiscoveryConflictError, DiscoveryService


def discovered(**overrides):
    values = {
        "id": uuid4(),
        "ip_address": "10.20.30.10",
        "mac_address": "00:00:0c:aa:bb:cc",
        "hostname": "switch-lobby",
        "vendor": "Cisco",
        "operating_system_guess": None,
        "device_type_guess": "switch",
        "network_zone_id": None,
        "subnet": "10.20.30.0/24",
        "discovery_method": "icmp+arp",
        "first_seen_at": datetime.now(timezone.utc),
        "last_seen_at": datetime.now(timezone.utc),
        "times_seen": 2,
        "response_time": 1.5,
        "status": DiscoveryStatus.ONLINE,
        "review_status": ReviewStatus.PENDING,
        "confidence_score": 75.0,
        "approved_device_id": None,
        "reviewed_by": None,
        "reviewed_at": None,
        "notes": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    values.update(overrides)
    return DiscoveredDevice(**values)


def approval(**overrides):
    values = {
        "asset_tag": "DISC-001",
        "brand": "Cisco",
        "model": "Unknown model",
        "serial_number": "DISC-SERIAL-001",
        "department": "IT",
        "location": "Lobby",
    }
    values.update(overrides)
    return InventoryApproval(**values)


class DiscoveryApiContractTests(unittest.TestCase):
    def test_routes_are_registered_without_frontend_or_scheduler_contracts(self):
        paths = app.openapi()["paths"]
        expected = {
            "/api/v1/discovery",
            "/api/v1/discovery/{discovery_id}",
            "/api/v1/discovery/stats",
            "/api/v1/discovery/run",
            "/api/v1/discovery/{discovery_id}/approve",
            "/api/v1/discovery/{discovery_id}/ignore",
            "/api/v1/discovery/{discovery_id}/reject",
            "/api/v1/discovery/bulk-approve",
            "/api/v1/discovery/bulk-ignore",
            "/api/v1/discovery/bulk-reject",
        }
        self.assertTrue(expected.issubset(paths))

    def test_mutation_routes_reject_non_admin_roles(self):
        protected = {
            "/api/v1/discovery/run",
            "/api/v1/discovery/{discovery_id}/approve",
            "/api/v1/discovery/{discovery_id}/ignore",
            "/api/v1/discovery/{discovery_id}/reject",
            "/api/v1/discovery/bulk-approve",
            "/api/v1/discovery/bulk-ignore",
            "/api/v1/discovery/bulk-reject",
        }
        for route in app.routes:
            if getattr(route, "path", None) not in protected:
                continue
            role_dependencies = [
                dependency.call
                for dependency in route.dependant.dependencies
                if getattr(dependency.call, "__name__", "") == "role_checker"
            ]
            self.assertEqual(len(role_dependencies), 1, route.path)
            with self.assertRaises(HTTPException) as raised:
                role_dependencies[0](SimpleNamespace(role="technician"))
            self.assertEqual(raised.exception.status_code, 403)

    def test_reject_reason_is_optional_and_trimmed(self):
        self.assertIsNone(RejectRequest().reason)
        self.assertEqual(RejectRequest(reason="  duplicate lab entry  ").reason, "duplicate lab entry")


class DiscoveryApprovalTests(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.publisher = MagicMock()
        self.actor = SimpleNamespace(id=str(uuid4()), username="admin", role="admin")
        self.service = DiscoveryService(self.db, config={}, publisher=self.publisher)
        self.service._email_notification = MagicMock()
        self.discovery = discovered()
        self.service.devices.get = MagicMock(return_value=self.discovery)
        self.db.query.return_value.filter.return_value.first.return_value = None

        def add(entity):
            if isinstance(entity, Device) and entity.id is None:
                entity.id = uuid4()
        self.db.add.side_effect = add

    @patch("app.services.discovery_service.resolve_device_hierarchy")
    def test_approval_is_atomic_links_inventory_audits_and_notifies(self, resolve):
        resolve.side_effect = lambda db, values: values
        approved, device = self.service.approve(self.discovery.id, approval(), self.actor)
        self.assertEqual(approved.review_status, ReviewStatus.APPROVED)
        self.assertEqual(approved.approved_device_id, device.id)
        self.assertEqual(approved.reviewed_by, self.actor.id)
        self.assertIsNotNone(approved.reviewed_at)
        self.db.commit.assert_called_once()
        audits = [call.args[0] for call in self.db.add.call_args_list if isinstance(call.args[0], AuditLog)]
        self.assertEqual({item.action for item in audits}, {"APPROVE_DISCOVERY", "CREATE_DEVICE_FROM_DISCOVERY"})
        self.publisher.assert_called_once()
        self.assertEqual(self.publisher.call_args.args[0]["event"], "discovery_approved")

    def test_approval_prevents_existing_inventory_link(self):
        self.discovery.approved_device_id = uuid4()
        with self.assertRaises(DiscoveryConflictError):
            self.service.approve(self.discovery.id, approval(), self.actor)
        self.db.rollback.assert_called_once()
        self.db.commit.assert_not_called()
        self.publisher.assert_not_called()

    @patch("app.services.discovery_service.resolve_device_hierarchy")
    def test_database_duplicate_rolls_back_without_notification(self, resolve):
        resolve.side_effect = lambda db, values: values
        self.db.query.return_value.filter.return_value.first.return_value = Device()
        with self.assertRaises(DiscoveryConflictError):
            self.service.approve(self.discovery.id, approval(), self.actor)
        self.db.rollback.assert_called_once()
        self.db.commit.assert_not_called()
        self.publisher.assert_not_called()

    def test_ignore_and_reject_preserve_discovery_history(self):
        original_times_seen = self.discovery.times_seen
        ignored = self.service.review(self.discovery.id, ReviewStatus.IGNORED, self.actor)
        self.assertEqual(ignored.review_status, ReviewStatus.IGNORED)
        self.assertEqual(ignored.times_seen, original_times_seen)
        self.db.delete.assert_not_called()

        rejected_record = discovered(id=uuid4())
        self.service.devices.get.return_value = rejected_record
        rejected = self.service.review(
            rejected_record.id,
            ReviewStatus.REJECTED,
            self.actor,
            "Duplicate entry",
        )
        self.assertIn("Duplicate entry", rejected.notes)
        self.assertEqual(rejected.review_status, ReviewStatus.REJECTED)
        self.db.delete.assert_not_called()

    def test_bulk_review_is_one_transaction(self):
        first, second = discovered(id=uuid4()), discovered(id=uuid4())
        self.service.devices.get.side_effect = [first, second]
        results = self.service.bulk_review(
            [first.id, second.id], ReviewStatus.IGNORED, self.actor
        )
        self.assertEqual(len(results), 2)
        self.db.commit.assert_called_once()

    @patch("app.services.discovery_service.resolve_device_hierarchy")
    def test_bulk_approval_rolls_back_as_one_transaction(self, resolve):
        resolve.side_effect = lambda db, values: values
        missing_id = uuid4()
        self.service.devices.get.side_effect = [self.discovery, None]
        with self.assertRaises(ValueError):
            self.service.bulk_approve(
                [
                    (self.discovery.id, approval()),
                    (missing_id, approval(asset_tag="DISC-002", serial_number="DISC-SERIAL-002")),
                ],
                self.actor,
            )
        self.db.rollback.assert_called_once()
        self.db.commit.assert_not_called()
        self.publisher.assert_not_called()

    def test_csv_export_neutralizes_spreadsheet_formulas(self):
        unsafe = discovered(hostname="=WEBSERVICE('bad')")
        self.service.devices.list = MagicMock(return_value=[unsafe])
        content, filename = self.service.export_csv()
        self.assertIn("'=WEBSERVICE", content)
        self.assertTrue(filename.startswith("hiop-discovery-"))


if __name__ == "__main__":
    unittest.main()
