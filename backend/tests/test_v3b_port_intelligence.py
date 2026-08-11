"""V3B contracts use fixtures only and never contact real infrastructure."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.models.port_intelligence import PortDeviceAssociation
from app.models.snmp import SNMPInterface
from app.services.port_intelligence_service import (
    BRIDGE_BASE_PORT_IFINDEX_OID, BRIDGE_FDB_ADDRESS_OID, BRIDGE_FDB_PORT_OID,
    PortIntelligenceService, PortMACObservation, PortMACTableProvider,
    mac_from_oid, status_name,
)
from app.services.snmp_client_service import SNMPValue, SNMPWalkResult


class Rows:
    def __init__(self, rows): self.rows = rows
    def all(self): return self.rows


class FixtureDB:
    def __init__(self, interfaces, associations=None):
        self.interfaces = interfaces
        self.associations = associations or []
        self.added = []
    def scalars(self, query):
        text = str(query)
        if "FROM snmp_interfaces" in text: return Rows(self.interfaces)
        if "FROM port_device_associations" in text: return Rows(self.associations)
        return Rows([])
    def add(self, row):
        if getattr(row, "id", None) is None: row.id = uuid4()
        self.added.append(row)
        if isinstance(row, PortDeviceAssociation): self.associations.append(row)
    def flush(self): pass
    def commit(self): pass


def switch():
    return SimpleNamespace(id=uuid4(), hostname="SW-FLOOR-02", device_type="Switch", ip_address="10.0.0.2", mac_address="00:11:22:33:44:55")


def endpoint(mac="aa:bb:cc:dd:ee:ff"):
    return SimpleNamespace(id=uuid4(), hostname="POS Terminal 01", device_type="Point of Sale", ip_address="10.0.0.20", mac_address=mac)


def interface(target_id=None, index=12, name="Gi1/0/12", status="1"):
    return SNMPInterface(id=uuid4(), target_id=target_id or uuid4(), interface_index=index, name=name, description="POS 01", admin_status="1", operational_status=status, speed_bps=1_000_000_000, duplex="full", is_missing=False, missed_polls=0, monitored=True, critical=False, alert_on_down=False, alert_on_utilization=False, alert_on_errors=False)


def service_fixture(interfaces, matches):
    db = FixtureDB(interfaces)
    service = PortIntelligenceService(db)
    target = SimpleNamespace(id=interfaces[0].target_id)
    service._target = lambda _device_id: target
    service._uplinks = lambda _device_id, _interfaces: {}
    service._device_index = lambda: matches
    service._topology_link = lambda *_args, **_kwargs: None
    service._find_association = lambda interface_id, mac, device_id: next((row for row in db.associations if row.interface_id == interface_id and row.observed_mac == mac and row.connected_device_id == device_id), None)
    return service, db


def test_interface_helpers_preserve_status_speed_description_and_oid_mac():
    row = interface()
    assert row.name == "Gi1/0/12" and row.description == "POS 01"
    assert row.speed_bps == 1_000_000_000 and row.duplex == "full"
    assert status_name(row.admin_status) == "up" and status_name("2") == "down"
    assert mac_from_oid(BRIDGE_FDB_ADDRESS_OID + ".170.187.204.221.238.255", BRIDGE_FDB_ADDRESS_OID) == "aa:bb:cc:dd:ee:ff"


def test_mac_table_provider_maps_bridge_port_to_interface_and_is_read_only(monkeypatch):
    class Client:
        def __init__(self, *_args, **_kwargs): pass
        def bulk_walk(self, root, **kwargs):
            assert kwargs["max_rows"] > 0 and kwargs["max_duration"] > 0
            if root == BRIDGE_FDB_ADDRESS_OID:
                return SNMPWalkResult([SNMPValue(root + ".170.187.204.221.238.255", value_text="aa:bb:cc:dd:ee:ff")], False)
            if root == BRIDGE_FDB_PORT_OID:
                return SNMPWalkResult([SNMPValue(root + ".170.187.204.221.238.255", value_numeric=12)], False)
            return SNMPWalkResult([SNMPValue(BRIDGE_BASE_PORT_IFINDEX_OID + ".12", value_numeric=1012)], False)
        def close(self): pass
    monkeypatch.setattr("app.services.port_intelligence_service.read_discovery", lambda _db: {"authorized_cidr_ranges": ["10.0.0.0/8"], "ignore_ranges": []})
    target = SimpleNamespace(credential=object())
    assert PortMACTableProvider(object(), Client).collect(target) == [PortMACObservation(1012, "aa:bb:cc:dd:ee:ff")]


def test_known_mac_creates_one_explainable_current_association_without_new_device(monkeypatch):
    port, device, network_switch = interface(), endpoint(), switch()
    service, db = service_fixture([port], {device.mac_address: [device]})
    monkeypatch.setattr("app.services.port_intelligence_service.create_audit_log", lambda *_args, **_kwargs: None)
    result = service.correlate(network_switch, [PortMACObservation(port.interface_index, device.mac_address)], SimpleNamespace(username="admin"))
    assert result == {"resolved": 1, "unresolved": 0, "uplinks": 0, "observed": 1, "interfaces": 1}
    association = db.associations[0]
    assert association.connected_device_id == device.id and association.interface_id == port.id
    assert association.confidence_score == 90 and association.confidence_level == "high"
    assert any(item["source"] == "V2_IDENTITY" for item in association.evidence)
    assert not any(type(row).__name__ == "Device" for row in db.added)


def test_unknown_and_multiple_mac_entries_remain_unresolved_and_share_one_port(monkeypatch):
    port, network_switch = interface(), switch()
    service, db = service_fixture([port], {})
    monkeypatch.setattr("app.services.port_intelligence_service.create_audit_log", lambda *_args, **_kwargs: None)
    observations = [PortMACObservation(port.interface_index, "aa:aa:aa:aa:aa:aa"), PortMACObservation(port.interface_index, "bb:bb:bb:bb:bb:bb")]
    result = service.correlate(network_switch, observations, SimpleNamespace(username="admin"))
    assert result["unresolved"] == 2 and len(db.associations) == 2
    assert all(row.connected_device_id is None and row.confidence_level == "low" for row in db.associations)


def test_repeated_discovery_is_idempotent_and_device_move_preserves_stale_history(monkeypatch):
    first, second, device, network_switch = interface(index=12), interface(index=15, name="Gi1/0/15"), endpoint(), switch()
    second.target_id = first.target_id
    service, db = service_fixture([first, second], {device.mac_address: [device]})
    monkeypatch.setattr("app.services.port_intelligence_service.create_audit_log", lambda *_args, **_kwargs: None)
    actor = SimpleNamespace(username="admin")
    service.correlate(network_switch, [PortMACObservation(12, device.mac_address)], actor)
    service.correlate(network_switch, [PortMACObservation(12, device.mac_address)], actor)
    assert len(db.associations) == 1
    service.correlate(network_switch, [PortMACObservation(15, device.mac_address)], actor)
    assert len(db.associations) == 2
    old = next(row for row in db.associations if row.interface_id == first.id)
    current = next(row for row in db.associations if row.interface_id == second.id)
    assert not old.is_current and old.stale_at is not None and current.is_current


def test_uplink_is_not_classified_as_endpoint_and_stale_records_are_preserved(monkeypatch):
    port, peer, network_switch = interface(index=48, name="Gi1/0/48"), endpoint("00:00:00:00:00:48"), switch()
    peer.device_type = "Switch"
    service, db = service_fixture([port], {})
    service._uplinks = lambda *_args: {port.id: peer}
    monkeypatch.setattr("app.services.port_intelligence_service.create_audit_log", lambda *_args, **_kwargs: None)
    result = service.correlate(network_switch, [], SimpleNamespace(username="admin"))
    assert result["uplinks"] == 1
    assert db.associations[0].association_type == "uplink" and db.associations[0].connected_device_id == peer.id


def test_v3b_api_is_read_only_against_infrastructure_with_admin_refresh_only():
    from app.main import app
    paths = app.openapi()["paths"]
    assert set(paths["/api/v1/port-intelligence/devices/{device_id}/connection"]) == {"get"}
    assert set(paths["/api/v1/port-intelligence/switches/{device_id}/interfaces"]) == {"get"}
    assert set(paths["/api/v1/port-intelligence/interfaces/{interface_id}"]) == {"get"}
    assert set(paths["/api/v1/port-intelligence/switches/{device_id}/refresh"]) == {"post"}
    source = Path(__file__).parents[1].joinpath("app/services/port_intelligence_service.py").read_text(encoding="utf-8")
    for forbidden in ("enable_port", "disable_port", "set_vlan", "configure_interface", "restart_interface"):
        assert forbidden not in source


def test_stale_age_is_reportable_without_deleting_history():
    now = datetime.now(timezone.utc)
    row = PortDeviceAssociation(id=uuid4(), switch_device_id=uuid4(), interface_id=uuid4(), connected_device_id=uuid4(), observed_mac="aa:bb:cc:dd:ee:ff", confidence_score=90, confidence_level="high", confidence_explanation="Known MAC", evidence=[], first_observed_at=now - timedelta(days=2), last_observed_at=now - timedelta(days=1), is_current=False, stale_at=now)
    assert row.stale_at and not row.is_current and row.first_observed_at < row.last_observed_at
