import unittest

from pydantic import ValidationError

from app.main import app
from app.schemas.device import DeviceCreate
from app.schemas.hierarchy import HierarchyMutation, NetworkZoneInput


class HierarchyPhaseOneBContractTests(unittest.TestCase):
    def test_hierarchy_routes_are_registered(self):
        paths = app.openapi()["paths"]
        self.assertIn("/api/v1/hierarchy", paths)
        self.assertIn("/api/v1/hierarchy/{kind}", paths)
        self.assertIn("/api/v1/hierarchy/{kind}/{row_id}", paths)

    def test_device_accepts_normalized_relationships(self):
        payload = DeviceCreate(
            asset_tag="TEST-1", hostname="test-1", device_type="Desktop", brand="Dell",
            model="Test", serial_number="SER-1", department="IT", location="Office",
            ip_address="192.0.2.1", mac_address="00:11:22:33:44:55",
            department_id="00000000-0000-0000-0000-000000000001",
            room_id="00000000-0000-0000-0000-000000000002",
            network_zone_id="00000000-0000-0000-0000-000000000003",
        )
        self.assertIsNotNone(payload.department_id)
        self.assertIsNotNone(payload.room_id)
        self.assertIsNotNone(payload.network_zone_id)

    def test_vlan_range_is_validated(self):
        with self.assertRaises(ValidationError):
            HierarchyMutation(name="Guest network", vlan_id=4095)

    def test_cidr_is_validated_and_normalized(self):
        zone = NetworkZoneInput(name="Guest", cidr="10.20.30.42/24")
        self.assertEqual(zone.cidr, "10.20.30.0/24")
        with self.assertRaises(ValidationError):
            NetworkZoneInput(name="Invalid", cidr="not-a-network")


if __name__ == "__main__":
    unittest.main()
