"""Deterministic validation for stored automation definitions."""
from typing import Any

def validate_graph(graph: Any, action_keys: set[str]) -> list[str]:
    errors: list[str] = []
    if not isinstance(graph, dict):
        return ["workflow_graph must be an object"]
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return ["nodes and edges must be arrays"]
    if len(nodes) > 100 or len(edges) > 200:
        errors.append("workflow graph exceeds safe node or edge limits")
    ids = set()
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str):
            errors.append("every node requires a string id")
            continue
        if node["id"] in ids:
            errors.append(f"duplicate node id: {node['id']}")
        ids.add(node["id"])
        if node.get("type") == "action" and node.get("action_key") not in action_keys:
            errors.append(f"unknown or disabled action: {node.get('action_key')}")
        if "condition" in node and not isinstance(node["condition"], dict):
            errors.append(f"condition on node {node['id']} must be structured")
    for edge in edges:
        if not isinstance(edge, dict) or edge.get("source") not in ids or edge.get("target") not in ids:
            errors.append("edge references an unknown node")
    return errors
