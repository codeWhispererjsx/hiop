import json
import re

ALLOWED_BASE_FIELDS = {
    "incident_number", "title", "status", "severity", "priority",
    "incident_type", "guest_impact_level", "revenue_impact_level",
}
FIELD_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def render_template(template, incident, extra=None):
    allowed = set(json.loads(template.allowed_fields or "[]")) | ALLOWED_BASE_FIELDS
    values = {field: getattr(incident, field, "") for field in allowed}
    values.update({key: value for key, value in (extra or {}).items() if key in allowed})

    def render(text):
        fields = set(FIELD_PATTERN.findall(text))
        disallowed = fields - allowed
        if disallowed:
            raise ValueError("Template uses disallowed fields: " + ", ".join(sorted(disallowed)))
        return FIELD_PATTERN.sub(lambda match: str(values.get(match.group(1), "")), text)

    return {"subject": render(template.subject_template), "message": render(template.body_template)}
