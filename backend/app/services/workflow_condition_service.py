"""Bounded, structured workflow condition evaluation without executable expressions."""

ALLOWED = {
    "equals", "not_equals", "in_list", "not_in_list", "greater_than",
    "greater_than_or_equal", "less_than", "less_than_or_equal", "contains",
    "starts_with", "ends_with", "is_true", "is_false", "is_empty",
    "is_not_empty", "exists", "not_exists", "status_is", "severity_is",
    "property_is", "role_has", "permission_has",
}


def evaluate(condition, context, *, depth=0, counter=None):
    if depth > 5:
        raise ValueError("condition nesting exceeds safe limit")
    counter = counter or [0]
    counter[0] += 1
    if counter[0] > 50:
        raise ValueError("condition count exceeds safe limit")
    if not isinstance(condition, dict):
        raise ValueError("condition must be structured")
    for logical in ("all", "any", "none"):
        if logical in condition:
            children = condition[logical]
            if not isinstance(children, list) or not children:
                raise ValueError(f"{logical} requires a non-empty list")
            evidence = [evaluate(item, context, depth=depth + 1, counter=counter) for item in children]
            values = [item["result"] for item in evidence]
            result = all(values) if logical == "all" else any(values) if logical == "any" else not any(values)
            return {"logical": logical, "result": result, "evidence": evidence}
    op = condition.get("operator")
    field = condition.get("field")
    if op not in ALLOWED or not isinstance(field, str) or len(field) > 120:
        raise ValueError("unsupported condition")
    value = context.get(field)
    expected = condition.get("value")
    try:
        if op in {"equals", "status_is", "severity_is", "property_is"}: result = value == expected
        elif op == "not_equals": result = value != expected
        elif op == "in_list": result = value in (expected or [])
        elif op == "not_in_list": result = value not in (expected or [])
        elif op == "greater_than": result = value > expected
        elif op == "greater_than_or_equal": result = value >= expected
        elif op == "less_than": result = value < expected
        elif op == "less_than_or_equal": result = value <= expected
        elif op == "contains": result = expected in value if isinstance(value, (str, list)) else False
        elif op == "starts_with": result = value.startswith(expected) if isinstance(value, str) and isinstance(expected, str) else False
        elif op == "ends_with": result = value.endswith(expected) if isinstance(value, str) and isinstance(expected, str) else False
        elif op == "is_true": result = value is True
        elif op == "is_false": result = value is False
        elif op == "exists": result = value is not None
        elif op == "not_exists": result = value is None
        elif op == "is_empty": result = value in (None, "", [])
        elif op == "is_not_empty": result = value not in (None, "", [])
        else: result = expected in (value or [])
    except TypeError:
        result = False
    return {"operator": op, "field": field, "result": result}
