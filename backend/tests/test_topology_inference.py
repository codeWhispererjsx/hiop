"""Epic 5C inference contracts use synthetic graph objects only."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.api.v1.topology import router
from app.models.topology_inference import (
    TopologyConfidenceHistory, TopologyConflict, TopologyInferenceRun,
    TopologyReviewItem,
)
from app.services.topology_inference_service import TopologyInferenceService


def node(**values):
    defaults = {
        "id": uuid4(), "device_id": None, "snmp_target_id": None,
        "layer": "unknown", "status": "active", "node_type": "unknown",
        "role": "unknown", "label": "node", "is_manual": False,
        "management_ip": None, "metadata_json": {},
    }
    return SimpleNamespace(**{**defaults, **values})


def link(source, target, **values):
    defaults = {
        "id": uuid4(), "source_node_id": source, "target_node_id": target,
        "source_interface_id": None, "target_interface_id": None,
        "status": "active", "is_suppressed": False, "is_manual": False,
        "is_confirmed": False, "confidence_score": 50,
        "first_seen_at": datetime.now(timezone.utc) - timedelta(days=40),
        "metadata_json": {}, "link_type": "physical",
    }
    return SimpleNamespace(**{**defaults, **values})


def evidence(source_type="LLDP", evidence_type="unidirectional_neighbor"):
    return SimpleNamespace(source_type=source_type, evidence_type=evidence_type)


def dependency(upstream, downstream, enabled=True):
    return SimpleNamespace(id=uuid4(), upstream_node_id=upstream, downstream_node_id=downstream, enabled=enabled)


def test_inference_models_are_registered():
    assert TopologyInferenceRun.__tablename__ == "topology_inference_runs"
    assert TopologyConflict.__tablename__ == "topology_conflicts"
    assert TopologyReviewItem.__tablename__ == "topology_review_items"
    assert TopologyConfidenceHistory.__tablename__ == "topology_confidence_history"


def test_confidence_fuses_protocol_direction_interfaces_and_inventory():
    left, right = node(device_id=uuid4()), node(snmp_target_id=uuid4())
    graph_link = link(left.id, right.id, source_interface_id=uuid4(), target_interface_id=uuid4())
    score, parts = TopologyInferenceService.recalculate_confidence(
        graph_link,
        [evidence("LLDP", "bidirectional_neighbor"), evidence("CDP")],
        {left.id: left, right.id: right},
    )
    assert score == 95
    assert parts["bidirectional"] == 25
    assert parts["protocol_agreement"] == 15
    assert parts["both_interfaces_resolved"] == 15


def test_confirmed_manual_link_remains_authoritative():
    left, right = node(), node()
    graph_link = link(left.id, right.id, is_manual=True, is_confirmed=True)
    score, parts = TopologyInferenceService.recalculate_confidence(
        graph_link, [], {left.id: left, right.id: right}
    )
    assert score == 100
    assert parts["confirmed_manual"] == 75


def test_conflicts_and_missing_reduce_confidence():
    left, right = node(), node()
    graph_link = link(left.id, right.id, status="missing", metadata_json={"conflicts": ["identity"]})
    score, parts = TopologyInferenceService.recalculate_confidence(
        graph_link, [evidence()], {left.id: left, right.id: right}
    )
    assert score == 0
    assert parts["missing_penalty"] == -30
    assert parts["conflict_penalty"] == -20


def test_duplicate_link_key_is_direction_independent():
    left, right, first_if, second_if = uuid4(), uuid4(), uuid4(), uuid4()
    forward = link(left, right, source_interface_id=first_if, target_interface_id=second_if)
    reverse = link(right, left, source_interface_id=second_if, target_interface_id=first_if)
    assert TopologyInferenceService.link_key(forward) == TopologyInferenceService.link_key(reverse)


def test_layer_inference_uses_device_type_and_degree_without_overwriting_existing():
    assert TopologyInferenceService.infer_layer(node(node_type="printer"), 1)[0] == "endpoint"
    assert TopologyInferenceService.infer_layer(node(node_type="switch"), 4)[0] == "access"
    assert TopologyInferenceService.infer_layer(node(node_type="switch"), 15)[0] == "distribution"
    assert TopologyInferenceService.infer_layer(node(layer="core", is_manual=True), 1)[0] == "core"


def test_uplink_downlink_and_trunk_classification():
    assert TopologyInferenceService.classify_link("access", "distribution")[0] == "uplink"
    assert TopologyInferenceService.classify_link("core", "access")[0] == "downlink"
    assert TopologyInferenceService.classify_link("access", "access", vlan_id=20)[0] == "trunk"


def test_path_reconstruction_returns_shortest_then_alternatives_and_is_cycle_safe():
    a, b, c, d = uuid4(), uuid4(), uuid4(), uuid4()
    links = [link(a, b), link(b, d), link(a, c), link(c, d), link(b, c)]
    paths = TopologyInferenceService.reconstruct_paths(a, d, links, max_depth=6, max_paths=5)
    assert len(paths) >= 2
    assert paths[0]["hops"] == 2
    assert all(len(path["nodes"]) == len(set(path["nodes"])) for path in paths)


def test_dependency_only_path_reconstruction():
    core, access, endpoint = uuid4(), uuid4(), uuid4()
    paths = TopologyInferenceService.reconstruct_paths(
        core, endpoint, [], [dependency(core, access), dependency(access, endpoint)],
        path_type="dependency",
    )
    assert paths[0]["hops"] == 2
    assert all(edge["type"] == "dependency" for edge in paths[0]["edges"])


def test_orphan_analysis_identifies_orphans_islands_and_missing_uplinks():
    core = node(layer="core")
    access = node(layer="access")
    endpoint = node(layer="endpoint")
    orphan = node(layer="access")
    result = TopologyInferenceService.orphan_analysis(
        [core, access, endpoint, orphan],
        [link(core.id, access.id), link(access.id, endpoint.id)],
    )
    assert str(orphan.id) in result["orphan_node_ids"]
    assert str(orphan.id) in result["missing_uplink_node_ids"]
    assert len(result["isolated_components"]) == 1


def test_graph_checksum_is_stable_across_input_order():
    a, b = node(), node()
    first, second = link(a.id, b.id), link(b.id, a.id)
    assert TopologyInferenceService.graph_checksum([a, b], [first, second]) == TopologyInferenceService.graph_checksum([b, a], [second, first])


def test_inference_api_routes_and_review_actions_are_registered():
    paths = {route.path for route in router.routes}
    required = {
        "/topology/{topology_id}/inference",
        "/topology/{topology_id}/run-inference",
        "/topology/{topology_id}/conflicts",
        "/topology/{topology_id}/review-items",
        "/topology/{topology_id}/review-items/{item_id}/approve",
        "/topology/{topology_id}/review-items/{item_id}/reject",
        "/topology/{topology_id}/review-items/{item_id}/ignore",
        "/topology/{topology_id}/path-analysis",
        "/topology/{topology_id}/impact-analysis",
        "/topology/{topology_id}/comparison",
    }
    assert required <= paths
