import unittest
from uuid import uuid4

from pydantic import ValidationError

from app.main import app
from app.schemas.device import DeviceCreate
from app.schemas.ticket import TicketCreate


class DevicePhaseOneContractTests(unittest.TestCase):
    def setUp(self):
        self.device = {
            "asset_tag": "TEST-001",
            "hostname": "test-device",
            "device_type": "Test",
            "brand": "HIOP",
            "model": "Phase 1",
            "serial_number": "SERIAL-001",
            "department": "IT",
            "location": "Lab",
            "ip_address": "192.0.2.1",
            "mac_address": "02:00:00:00:00:01",
        }

    def test_inventory_status_excludes_network_states(self):
        with self.assertRaises(ValidationError):
            DeviceCreate(**self.device, inventory_status="Online")

    def test_ticket_accepts_direct_device_relationship(self):
        device_id = uuid4()
        ticket = TicketCreate(title="Test", description="Test", device_id=device_id)
        self.assertEqual(ticket.device_id, device_id)

    def test_device_history_routes_are_registered(self):
        paths = set(app.openapi()["paths"])
        for suffix in ("scans", "alerts", "tickets", "audit-logs"):
            self.assertIn(f"/api/v1/devices/{{device_id}}/{suffix}", paths)


if __name__ == "__main__":
    unittest.main()
