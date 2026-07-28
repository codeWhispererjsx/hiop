ALLOWED={"equals","not_equals","in_list","contains","starts_with","ends_with","exists","is_empty","is_not_empty"}
def evaluate(condition, context):
    if not isinstance(condition,dict): raise ValueError("condition must be structured")
    op=condition.get("operator"); field=condition.get("field")
    if op not in ALLOWED or not isinstance(field,str): raise ValueError("unsupported condition")
    value=context.get(field); expected=condition.get("value")
    return {"operator":op,"field":field,"result": {"equals":value==expected,"not_equals":value!=expected,"in_list":value in (expected or []),"contains":expected in value if isinstance(value,str) and isinstance(expected,str) else False,"starts_with":value.startswith(expected) if isinstance(value,str) and isinstance(expected,str) else False,"ends_with":value.endswith(expected) if isinstance(value,str) and isinstance(expected,str) else False,"exists":value is not None,"is_empty":value in (None,"",[]),"is_not_empty":value not in (None,"",[])}[op]}
