"""Deterministic workflow planning with cycle and dependency validation."""

def build_plan(steps, dependencies):
    enabled = {str(step.id): step for step in steps if step.enabled}
    incoming = {key: set() for key in enabled}
    outgoing = {key: set() for key in enabled}
    for dep in dependencies:
        up, down = str(dep.upstream_step_id), str(dep.downstream_step_id)
        if up not in enabled or down not in enabled:
            raise ValueError("dependency references a disabled or unknown step")
        if up == down:
            raise ValueError("step cannot depend on itself")
        incoming[down].add(up); outgoing[up].add(down)
    ready = sorted((key for key, values in incoming.items() if not values), key=lambda key: enabled[key].sequence_order)
    ordered = []
    while ready:
        key = ready.pop(0); ordered.append(enabled[key])
        for child in sorted(outgoing[key]):
            incoming[child].discard(key)
            if not incoming[child] and child not in {str(item.id) for item in ordered} and child not in ready:
                ready.append(child)
        ready.sort(key=lambda item: enabled[item].sequence_order)
    if len(ordered) != len(enabled):
        raise ValueError("workflow step dependency cycle detected")
    return [{"step_id": str(step.id), "step_key": step.step_key, "step_type": step.step_type, "action_key": step.action_key, "approval_required": step.approval_required, "timeout_seconds": step.timeout_seconds} for step in ordered]
