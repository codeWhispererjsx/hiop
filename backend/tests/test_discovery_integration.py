import unittest
from unittest.mock import MagicMock, patch

from app.main import app
from app.schemas.settings import DiscoverySettings
from app.services import scheduler_service
from app.services.report_service import REPORTS


class DiscoveryIntegrationTests(unittest.TestCase):
    def test_discovery_settings_reject_public_ranges(self):
        with self.assertRaises(ValueError):
            DiscoverySettings(
                enabled=True,
                authorized_cidr_ranges="8.8.8.0/24",
                interval_minutes=60,
                ping_timeout_seconds=2,
                concurrency_limit=10,
                max_hosts_per_run=256,
                automatic_vendor_lookup=True,
                automatic_hostname_lookup=True,
                admin_notification_threshold=5,
            )

    def test_enabled_schedule_rejects_ranges_above_host_cap(self):
        with self.assertRaisesRegex(ValueError, "max_hosts_per_run"):
            DiscoverySettings(
                enabled=True,
                authorized_cidr_ranges="10.20.0.0/16",
                interval_minutes=60,
                ping_timeout_seconds=2,
                concurrency_limit=10,
                max_hosts_per_run=256,
                automatic_vendor_lookup=True,
                automatic_hostname_lookup=True,
                admin_notification_threshold=5,
            )

    def test_discovery_settings_route_is_admin_only(self):
        operation = app.openapi()["paths"]["/api/v1/settings/discovery"]["put"]
        self.assertIn("security", operation)

    def test_scheduler_uses_one_replaceable_non_overlapping_job(self):
        fake_scheduler = MagicMock()
        fake_scheduler.running = True
        with patch.object(scheduler_service, "scheduler", fake_scheduler):
            scheduler_service.configure_discovery_scheduler(True, 60)
            scheduler_service.configure_discovery_scheduler(True, 30)
        self.assertEqual(fake_scheduler.add_job.call_count, 2)
        for call in fake_scheduler.add_job.call_args_list:
            self.assertEqual(call.kwargs["id"], "automatic_discovery")
            self.assertTrue(call.kwargs["replace_existing"])
            self.assertEqual(call.kwargs["max_instances"], 1)
            self.assertTrue(call.kwargs["coalesce"])

    def test_discovery_report_is_exposed(self):
        paths = app.openapi()["paths"]
        self.assertIn("/api/v1/reports/{report_name}", paths)
        self.assertIn("discovery", REPORTS)


if __name__ == "__main__":
    unittest.main()
