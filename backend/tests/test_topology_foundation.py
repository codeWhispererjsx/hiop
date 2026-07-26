"""Epic 5A foundation contracts. No discovery or network access occurs."""
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.v1.topology import router
from app.models.topology import (
    DeviceDependency, NetworkSegment, Topology, TopologyChange, TopologyGroup,
    TopologyLink, TopologyNode, TopologyNodePosition, TopologySnapshot,
)
from app.schemas.topology import DependencyWrite, LinkWrite, NodeWrite, SegmentWrite
from app.services.topology_service import TopologyService


def test_topology_models_are_registered():
    assert Topology.__tablename__ == "topologies"
    assert TopologyNode.__tablename__ == "topology_nodes"
    assert TopologyLink.__tablename__ == "topology_links"
    assert NetworkSegment.__tablename__ == "network_segments"
    assert DeviceDependency.__tablename__ == "topology_dependencies"
    assert TopologySnapshot.__tablename__ == "topology_snapshots"
    assert TopologyChange.__tablename__ == "topology_changes"
    assert TopologyNodePosition.__tablename__ == "topology_node_positions"
    assert TopologyGroup.__tablename__ == "topology_groups"


def test_node_rejects_contradictory_identity_and_bad_ip():
    with pytest.raises(ValidationError):
        NodeWrite(label="bad", device_id=uuid4(), snmp_target_id=uuid4())
    with pytest.raises(ValidationError):
        NodeWrite(label="bad", management_ip="not-an-ip")


def test_virtual_node_needs_no_inventory_identity():
    node = NodeWrite(label="Internet", node_type="internet", role="external")
    assert node.device_id is None and node.label == "Internet"


def test_link_rejects_self_link_and_invalid_vlan():
    node_id = uuid4()
    with pytest.raises(ValidationError):
        LinkWrite(source_node_id=node_id, target_node_id=node_id)
    with pytest.raises(ValidationError):
        LinkWrite(source_node_id=uuid4(), target_node_id=uuid4(), vlan_id=5000)


def test_segment_normalizes_cidr():
    segment = SegmentWrite(name="Management", cidr="10.0.0.5/24", vlan_id=10)
    assert segment.cidr == "10.0.0.0/24"


def test_dependency_rejects_self_cycle():
    node_id = uuid4()
    with pytest.raises(ValidationError):
        DependencyWrite(upstream_node_id=node_id, downstream_node_id=node_id, dependency_type="network")


def test_dependency_cycle_detection_is_bounded():
    a, b, c = uuid4(), uuid4(), uuid4()
    rows = [
        type("D", (), {"upstream_node_id": a, "downstream_node_id": b})(),
        type("D", (), {"upstream_node_id": b, "downstream_node_id": c})(),
    ]
    scalars = type("S", (), {"all": lambda self: rows})()
    db = type("DB", (), {"scalars": lambda self, query: scalars})()
    service = TopologyService(db)
    assert service._dependency_reachable(uuid4(), a, c)
    assert not service._dependency_reachable(uuid4(), c, a)


def test_topology_api_foundations_are_registered():
    paths = {route.path for route in router.routes}
    for path in (
        "/topology", "/topology/{topology_id}/graph", "/topology/{topology_id}/path",
        "/topology/{topology_id}/impact/{node_id}", "/topology/{topology_id}/snapshots",
        "/topology/{topology_id}/layout",
    ):
        assert path in paths
