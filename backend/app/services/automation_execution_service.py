"""Constrained automation execution. Handlers are explicit and deterministic."""
import json

SAFE_HANDLERS = {"noop", "record_event"}

def execute_graph(graph: dict, context: dict | None = None) -> dict:
    context = context or {}
    nodes = graph.get("nodes", [])
    executed = []
    for node in nodes:
        if not isinstance(node, dict) or node.get("type") != "action":
            continue
        key = node.get("action_key")
        if key not in SAFE_HANDLERS:
            raise ValueError(f"action handler is not approved: {key}")
        executed.append({"node_id": node.get("id"), "action_key": key, "result": "recorded" if key == "record_event" else "ok"})
    return {"executed": executed, "context_keys": sorted(context.keys()), "side_effects": False}
