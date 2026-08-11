"""V3C VLAN intelligence contracts use fixtures and never contact infrastructure."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.models.segmentation import VLANMembershipObservation
from app.services.segmentation_service import (
    BRIDGE_BASE_PORT_IFINDEX_OID, PORT_PVID_OID, VLAN_EGRESS_OID, VLAN_NAME_OID,
    VLAN_STATUS_OID, VLAN_UNTAGGED_OID, PortVLANRecord, VLANRecord,
    VLANTableProvider, _bitmap_ports,
)
from app.services.snmp_client_service import SNMPValue, SNMPWalkResult


def test_vlan_and_port_records_preserve_unknown_subnet_and_modes():
    vlan = VLANRecord(120, "POS", "active")
    access = PortVLANRecord(12, 120, "access", "access")
    trunk = PortVLANRecord(48, 130, "allowed", "trunk")
    assert vlan.cidr is None and vlan.gateway is None
    assert access.port_mode == "access" and trunk.port_mode == "trunk"
    assert _bitmap_ports("8010") == {1, 12}


def test_q_bridge_provider_discovers_access_and_multi_vlan_trunk(monkeypatch):
    class Client:
        def __init__(self,*args,**kwargs): pass
        def bulk_walk(self,root,**kwargs):
            values={
                VLAN_NAME_OID:[SNMPValue(root+".120",value_text="POS"),SNMPValue(root+".130",value_text="Management")],
                VLAN_STATUS_OID:[SNMPValue(root+".120",value_numeric=2),SNMPValue(root+".130",value_numeric=2)],
                VLAN_EGRESS_OID:[SNMPValue(root+".120",value_text="0010000000010000"),SNMPValue(root+".130",value_text="0000000000010000")],
                VLAN_UNTAGGED_OID:[SNMPValue(root+".120",value_text="0010000000000000")],
                PORT_PVID_OID:[SNMPValue(root+".12",value_numeric=120),SNMPValue(root+".48",value_numeric=120)],
                BRIDGE_BASE_PORT_IFINDEX_OID:[SNMPValue(root+".12",value_numeric=1012),SNMPValue(root+".48",value_numeric=1048)],
            }
            return SNMPWalkResult(values.get(root,[]),False)
        def close(self): pass
    monkeypatch.setattr("app.services.segmentation_service.read_discovery",lambda _:{"authorized_cidr_ranges":["10.0.0.0/8"],"ignore_ranges":[]})
    vlans,ports=VLANTableProvider(object(),Client).collect(SimpleNamespace(credential=object()))
    assert [(x.vlan_id,x.name,x.status) for x in vlans]==[(120,"POS","active"),(130,"Management","active")]
    assert any(x.interface_index==1012 and x.port_mode=="access" and x.vlan_id==120 for x in ports)
    assert {x.vlan_id for x in ports if x.interface_index==1048}=={120,130}
    assert all(x.port_mode=="trunk" for x in ports if x.interface_index==1048)


def test_membership_history_supports_current_and_stale_without_deletion():
    now=datetime.now(timezone.utc)
    row=VLANMembershipObservation(id=uuid4(),network_segment_id=uuid4(),switch_device_id=uuid4(),interface_id=uuid4(),connected_device_id=uuid4(),membership_type="access",port_mode="access",confidence_score=95,confidence_explanation="Q-BRIDGE and V3B agree",evidence=[],first_observed_at=now-timedelta(days=2),last_observed_at=now-timedelta(days=1),is_current=False,stale_at=now)
    assert not row.is_current and row.stale_at and row.first_observed_at < row.last_observed_at


def test_v3c_api_is_read_only_with_explicit_admin_refresh():
    from app.main import app
    paths=app.openapi()["paths"]
    assert set(paths["/api/v1/segmentation/vlans"])=={"get"}
    assert set(paths["/api/v1/segmentation/devices/{device_id}"])=={"get"}
    assert set(paths["/api/v1/segmentation/subnets"])=={"get"}
    assert set(paths["/api/v1/segmentation/switches/{device_id}/refresh"])=={"post"}
    source=Path(__file__).parents[1].joinpath("app/services/segmentation_service.py").read_text(encoding="utf-8").lower()
    for forbidden in ("snmp set","create_vlan","delete_vlan","assign_vlan","configure_trunk","change_firewall"):
        assert forbidden not in source


def test_vlan_identity_is_unique_per_topology_and_does_not_create_devices():
    migration=Path(__file__).parents[1].joinpath("alembic/versions/v3c8d0e2f4a6_add_vlan_segmentation.py").read_text(encoding="utf-8")
    service=Path(__file__).parents[1].joinpath("app/services/segmentation_service.py").read_text(encoding="utf-8")
    assert "uq_topology_vlan_id" in migration
    assert "Device(" not in service
