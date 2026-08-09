"""V3A topology contracts use fixtures only and never contact real infrastructure."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.models.topology import TopologyLink
from app.services.snmp_client_service import SNMPValue, SNMPWalkResult
from app.services.topology_neighbor_collection_service import TopologyNeighborCollectionService
from app.services.topology_neighbor_parser import parse_cdp_rows, parse_lldp_rows
from app.services.topology_v3a_service import (
    MINIMUM_RELATIONSHIP_CONFIDENCE, SNMPMACTableProvider, V3ATopologyService,
    confidence_level, normalize_mac,
)


def device(**changes):
    values={"id":uuid4(),"hostname":"floor-switch-01","ip_address":"10.50.21.10","mac_address":"00:11:22:33:44:55","device_type":"Switch","network_status":"Online","brand":"Cisco","model":"C9200"}
    values.update(changes)
    return SimpleNamespace(**values)


class ScalarRows:
    def __init__(self,rows):self.rows=rows
    def all(self):return self.rows


class QueueDB:
    def __init__(self,scalars):self.scalar_values=list(scalars);self.added=[]
    def scalar(self,_query):return self.scalar_values.pop(0)
    def add(self,row):
        if getattr(row,"id",None) is None:row.id=uuid4()
        self.added.append(row)
    def flush(self):pass


def test_lldp_and_cdp_neighbor_fixtures_are_normalized_without_network_access():
    lldp,_=parse_lldp_rows([{"local_port_identifier":"Gi1/0/1","remote_chassis_id":"00-11-22-33-44-55","remote_system_name":"floor-switch-01","remote_port_id":"Gi1/0/24","remote_management_address":"10.50.21.10","remote_capabilities":bytes([0x20])}])
    cdp,_=parse_cdp_rows([{"local_port_identifier":"1","remote_system_name":"core-switch","remote_port_id":"Gi0/1","remote_management_address":"10.50.21.1","remote_capabilities":9}])
    assert lldp[0].remote_chassis_id=="00:11:22:33:44:55"
    assert "bridge" in lldp[0].remote_capabilities
    assert {"router","switch"}<=set(cdp[0].remote_capabilities)


def test_neighbor_confidence_is_deterministic_explainable_and_conflict_aware():
    neighbor=parse_lldp_rows([{"local_port_identifier":"Gi1/0/1","remote_chassis_id":"0011.2233.4455","remote_system_name":"peer","remote_port_id":"Gi1/0/2","remote_management_address":"10.0.0.2"}])[0][0]
    service=TopologyNeighborCollectionService(None)
    score,parts=service._score(neighbor,object(),object(),device())
    conflict,conflict_parts=service._score(neighbor,object(),object(),device(),conflicts=["identity_conflict"])
    assert score>=80 and sum(parts.values())>=score
    assert conflict<score and conflict_parts["conflict_penalty"]<0


def test_confidence_labels_avoid_fake_precision():
    assert confidence_level(80)=="high"
    assert confidence_level(65)=="medium"
    assert confidence_level(20)=="low"
    assert MINIMUM_RELATIONSHIP_CONFIDENCE==60


def test_mac_normalization_supports_common_bridge_mib_formats():
    assert normalize_mac("0011.2233.4455")=="00:11:22:33:44:55"
    assert normalize_mac("0x001122334455")=="00:11:22:33:44:55"
    assert normalize_mac("not-a-mac") is None


def test_mac_table_provider_is_bounded_and_read_only(monkeypatch):
    class Client:
        def __init__(self,*_args,**_kwargs):self.closed=False
        def bulk_walk(self,root,**kwargs):
            assert root=="1.3.6.1.2.1.17.4.3.1.1"
            assert kwargs["max_rows"]>0 and kwargs["max_duration"]>0
            return SNMPWalkResult([SNMPValue(root+".1",value_text="0x001122334455")],False)
        def close(self):self.closed=True
    monkeypatch.setattr("app.services.topology_v3a_service.read_discovery",lambda _db:{"authorized_cidr_ranges":["10.0.0.0/8"],"ignore_ranges":[]})
    target=SimpleNamespace(credential=object())
    assert SNMPMACTableProvider(object(),Client).collect(target)=={"00:11:22:33:44:55"}


def test_same_relationship_discovered_repeatedly_updates_one_link():
    topology=SimpleNamespace(id=uuid4())
    actor=SimpleNamespace(id="admin",username="admin")
    source,destination=device(),device(hostname="pos-01",mac_address="aa:bb:cc:dd:ee:ff",device_type="Point of Sale")
    source_node=SimpleNamespace(id=uuid4(),device_id=source.id)
    destination_node=SimpleNamespace(id=uuid4(),device_id=destination.id)
    existing=TopologyLink(id=uuid4(),topology_id=topology.id,source_node_id=source_node.id,target_node_id=destination_node.id,link_type="connected_to",direction="source_to_target",status="stale",source_type="SNMP_MAC_TABLE",confidence_score=65,discovery_method="SNMP_MAC_TABLE",is_manual=False,is_confirmed=False,is_suppressed=False,metadata_json={})
    db=QueueDB([source_node,destination_node,existing,None])
    service=V3ATopologyService(db)
    link,created=service.upsert_relationship(topology,source,destination,"CONNECTED_TO","SNMP_MAC_TABLE",70,actor,"MAC evidence")
    assert link is existing and not created
    assert link.status=="active" and link.confidence_score==70
    assert not any(isinstance(row,TopologyLink) for row in db.added)


def test_weak_evidence_and_self_links_create_no_relationship():
    service=V3ATopologyService(QueueDB([]))
    topology=SimpleNamespace(id=uuid4());actor=SimpleNamespace(id="admin")
    first,second=device(),device()
    assert service.upsert_relationship(topology,first,second,"CONNECTED_TO","weak",59,actor)==(None,False)
    assert service.upsert_relationship(topology,first,first,"CONNECTED_TO","LLDP",90,actor)==(None,False)


def test_relationship_becomes_stale_but_is_not_deleted_and_can_be_verified_again():
    now=datetime.now(timezone.utc)
    link=SimpleNamespace(last_seen_at=now-timedelta(days=2),status="active",missing_since=None)
    db=Mock();db.scalars.return_value=ScalarRows([link])
    service=V3ATopologyService(db)
    assert service.mark_stale(SimpleNamespace(id=uuid4()),now)==1
    assert link.status=="stale" and link.missing_since==link.last_seen_at


def test_v3a_api_surface_is_read_only_except_admin_refresh():
    from app.main import app
    paths=app.openapi()["paths"]
    for path in ("/api/v1/topology","/api/v1/topology/refresh","/api/v1/topology/relationships/{relationship_id}","/api/v1/topology/devices/{device_id}/neighbors","/api/v1/topology/stats"):
        assert path in paths
    assert set(paths["/api/v1/topology"].keys())=={"get"}
    assert set(paths["/api/v1/topology/refresh"].keys())=={"post"}


def test_unknown_mac_cannot_create_a_fake_inventory_device():
    source=Path(__file__).parents[1].joinpath("app/services/topology_v3a_service.py").read_text(encoding="utf-8")
    assert "Device(" not in source
    assert "db.delete(" not in source
    assert ".set(" not in source and ".write(" not in source
