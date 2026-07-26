"""Epic 5B contracts use normalized fixtures only; no SNMP transport is opened."""
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.v1.topology import router
from app.models.topology_neighbor import (
    TopologyNeighborCandidate, TopologyNeighborCollectionRun,
    TopologyNeighborObservation,
)
from app.schemas.topology_neighbor import CandidateMatchRequest, NeighborCollectionRequest
from app.services.topology_neighbor_collection_service import TopologyNeighborCollectionService
from app.services.topology_neighbor_parser import (
    CDP_OIDS, LLDP_OIDS, capability_bits, parse_cdp_rows, parse_lldp_rows,
    remote_identity,
)


def test_neighbor_models_are_registered():
    assert TopologyNeighborCollectionRun.__tablename__ == "topology_neighbor_collection_runs"
    assert TopologyNeighborObservation.__tablename__ == "topology_neighbor_observations"
    assert TopologyNeighborCandidate.__tablename__ == "topology_neighbor_candidates"


def test_actual_approved_lldp_and_cdp_roots_are_centralized():
    assert LLDP_OIDS["remote_system_name"] == "1.0.8802.1.1.2.1.4.1.1.9"
    assert LLDP_OIDS["remote_chassis_id"] == "1.0.8802.1.1.2.1.4.1.1.5"
    assert CDP_OIDS["remote_system_name"] == "1.3.6.1.4.1.9.9.23.1.2.1.1.6"
    assert CDP_OIDS["remote_port_id"] == "1.3.6.1.4.1.9.9.23.1.2.1.1.7"


def test_lldp_parser_normalizes_identity_capabilities_and_optional_fields():
    rows = [{
        "raw_index": "44.12.1", "local_port_identifier": "12",
        "remote_chassis_id": "00-11-22-33-44-55",
        "remote_chassis_subtype": "macAddress", "remote_port_id": "Gi1/0/24",
        "remote_system_name": "edge-switch-1", "remote_management_address": "10.2.3.4",
        "remote_capabilities": bytes([0x28]),  # bridge + router
    }]
    parsed, warnings = parse_lldp_rows(rows, 20)
    assert not warnings
    assert parsed[0].remote_chassis_id == "00:11:22:33:44:55"
    assert parsed[0].remote_management_address == "10.2.3.4"
    assert parsed[0].remote_capabilities == ["bridge", "router"]
    assert parsed[0].identity_key == remote_identity(rows[0])


def test_cdp_parser_handles_ifindex_vlan_duplex_and_platform():
    parsed, warnings = parse_cdp_rows([{
        "raw_index": "9.1", "local_ifindex": 9,
        "remote_system_name": "dist-1", "remote_port_id": "Ten1/1",
        "remote_management_address": "10.10.0.2", "remote_platform": "Cisco C9300",
        "remote_capabilities": 9, "native_vlan": "120", "duplex": "full",
    }])
    assert not warnings
    assert parsed[0].local_ifindex == 9
    assert parsed[0].native_vlan == 120
    assert parsed[0].remote_platform == "Cisco C9300"
    assert set(parsed[0].remote_capabilities) == {"router", "switch"}


def test_parser_skips_malformed_rows_and_enforces_limit():
    parsed, warnings = parse_lldp_rows([
        {"remote_system_name": "missing-local"},
        {"local_port_identifier": "1", "remote_system_name": "ok"},
        {"local_port_identifier": "2", "remote_system_name": "bounded"},
    ], maximum=2)
    assert [item.remote_system_name for item in parsed] == ["ok"]
    assert any("without a local port" in warning for warning in warnings)
    assert any("limit reached" in warning for warning in warnings)


def test_capability_mapping_does_not_claim_unknown_bits():
    assert capability_bits(bytes([0x01]), {0: "router"}) == []


def test_collection_request_is_bounded_and_deduplicated():
    target = uuid4()
    with pytest.raises(ValidationError):
        NeighborCollectionRequest(target_ids=[target, target])
    with pytest.raises(ValidationError):
        NeighborCollectionRequest(target_ids=[], protocol_mode="both")


def test_candidate_match_requires_exactly_one_reviewed_identity():
    with pytest.raises(ValidationError):
        CandidateMatchRequest()
    with pytest.raises(ValidationError):
        CandidateMatchRequest(device_id=uuid4(), snmp_target_id=uuid4())
    assert CandidateMatchRequest(topology_node_id=uuid4()).topology_node_id


def test_confidence_is_explainable_and_bidirectional_increases_score():
    service = TopologyNeighborCollectionService(db=None)
    neighbor = parse_lldp_rows([{
        "local_port_identifier": "Gi1/0/1", "remote_chassis_id": "0011.2233.4455",
        "remote_management_address": "10.0.0.2", "remote_system_name": "peer",
        "remote_port_id": "Gi1/0/2",
    }])[0][0]
    single, single_parts = service._score(neighbor, object(), object())
    bidirectional, parts = service._score(neighbor, object(), object(), bidirectional=True)
    assert single >= 80
    assert bidirectional > single
    assert parts["bidirectional"] == 20
    assert sum(single_parts.values()) >= single


def test_manual_conflict_penalty_and_precedence_are_visible():
    service = TopologyNeighborCollectionService(db=None)
    neighbor = parse_cdp_rows([{
        "local_port_identifier": "1", "remote_system_name": "peer",
        "remote_management_address": "10.0.0.2", "remote_port_id": "Gi0/1",
    }])[0][0]
    clean, _ = service._score(neighbor, None, None)
    conflicted, breakdown = service._score(
        neighbor, None, None, conflicts=["confirmed_manual_link_precedence"]
    )
    assert conflicted < clean
    assert breakdown["conflict_penalty"] < 0


def test_neighbor_api_surface_has_no_arbitrary_oid_or_walk_endpoint():
    paths = {route.path for route in router.routes}
    required = {
        "/topology/{topology_id}/collect-neighbors",
        "/topology/{topology_id}/targets/{target_id}/collect-neighbors",
        "/topology/{topology_id}/neighbor-runs",
        "/topology/{topology_id}/neighbor-runs/{run_id}/results",
        "/topology/{topology_id}/neighbor-observations",
        "/topology/{topology_id}/neighbor-candidates",
        "/topology/{topology_id}/candidate-links",
    }
    assert required <= paths
    assert not any("walk" in path or "oid" in path for path in paths if "topology" in path)
