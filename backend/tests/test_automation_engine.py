import pytest

from app.services.automation_execution_service import execute_graph
from app.services.automation_validation_service import validate_graph
from app.services.workflow_condition_service import evaluate


def test_valid_safe_workflow_graph():
    graph = {"nodes": [{"id": "start", "type": "action", "action_key": "noop"}], "edges": []}
    assert validate_graph(graph, {"noop"}) == []
    result = execute_graph(graph, {"property_id": "test"})
    assert result["executed"][0]["action_key"] == "noop"
    assert result["side_effects"] is False


def test_unknown_action_is_rejected():
    graph = {"nodes": [{"id": "unsafe", "type": "action", "action_key": "shell"}], "edges": []}
    assert "unknown or disabled action: shell" in validate_graph(graph, {"noop"})
    with pytest.raises(ValueError, match="not approved"):
        execute_graph(graph)


def test_duplicate_nodes_and_invalid_edges_are_rejected():
    graph = {
        "nodes": [{"id": "a", "type": "action", "action_key": "noop"}, {"id": "a", "type": "action", "action_key": "noop"}],
        "edges": [{"source": "a", "target": "missing"}],
    }
    errors = validate_graph(graph, {"noop"})
    assert "duplicate node id: a" in errors
    assert "edge references an unknown node" in errors


def test_nested_conditions_are_bounded_and_explainable():
    condition = {"all": [
        {"operator": "severity_is", "field": "severity", "value": "critical"},
        {"any": [
            {"operator": "role_has", "field": "roles", "value": "admin"},
            {"operator": "permission_has", "field": "permissions", "value": "automation.execute"},
        ]},
    ]}
    result = evaluate(condition, {"severity": "critical", "roles": ["admin"], "permissions": []})
    assert result["result"] is True
    assert result["logical"] == "all"


def test_condition_depth_limit():
    condition = {"operator": "equals", "field": "value", "value": 1}
    for _ in range(7):
        condition = {"all": [condition]}
    with pytest.raises(ValueError, match="nesting"):
        evaluate(condition, {"value": 1})
