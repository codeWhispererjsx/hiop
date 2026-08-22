from types import SimpleNamespace
from uuid import uuid4

from app.services.device_identity_service import DeviceIdentityService, _matches, confidence_level


class FakeDB:
    def __init__(self, departments): self.departments = departments
    def get(self, _model, key): return self.departments.get(key)


class DeterministicIdentity(DeviceIdentityService):
    def __init__(self, rules, departments=None, sequence=1):
        super().__init__(FakeDB(departments or {})); self.rules = rules; self.sequence = sequence
    def scoped_rules(self, organization_id, property_id=None, include_disabled=False):
        return [row for row in self.rules if row.organization_id == organization_id and row.enabled and row.property_id in (None, property_id)]
    def _next_sequence(self, result, department, device_type):
        return result.identity_sequence or self.sequence
    def profile(self, result, organization_id, create=False):
        return SimpleNamespace(identity_sequence=result.identity_sequence)


def rule(org, prop, department_id, **overrides):
    values = dict(id=uuid4(), organization_id=org, property_id=prop, name="Printer rule", enabled=True,
                  match_field="hostname", match_operator="contains", pattern="FO-PRN",
                  output_device_type="Printer", output_department_id=department_id, output_location="Front Desk",
                  friendly_name_template="{department} {device_type} {sequence}", priority=100, confidence=84,
                  created_at=None)
    values.update(overrides); return SimpleNamespace(**values)


def device(prop, hostname="FO-PRN-01", **overrides):
    values = dict(id=uuid4(), property_id=prop, primary_hostname=hostname, fqdn=None, vendor="HP",
                  sys_description="Printer", ad_organizational_unit=None, device_type="Printer",
                  confidence_score=70, identity_confirmed=False, friendly_name=None, department=None,
                  location=None, identity_sequence=None)
    values.update(overrides); return SimpleNamespace(**values)


def test_deterministic_match_operators_and_confidence_bands():
    assert _matches("FO-PRN-01", "contains", "prn")
    assert _matches("FO-PRN-01", "starts_with", "fo")
    assert _matches("FO-PRN-01", "ends_with", "01")
    assert not _matches("FO-PRN-01", "equals", "FO")
    assert [confidence_level(x) for x in (20, 60, 90)] == ["LOW", "MEDIUM", "HIGH"]


def test_scoped_rule_generates_explainable_stable_friendly_name():
    org, prop, department_id = uuid4(), uuid4(), uuid4()
    department = SimpleNamespace(id=department_id, name="Front Office")
    service = DeterministicIdentity([rule(org, prop, department_id)], {department_id: department}, sequence=2)
    result = service.evaluate(device(prop), org)
    assert result.friendly_name == "Front Office Printer 2"
    assert result.device_type == "Printer" and result.department == "Front Office" and result.location == "Front Desk"
    assert result.confidence == 94 and result.source == "RULE" and result.rule_ids
    assert any("Hostname" in item for item in result.evidence)
    existing = service.evaluate(device(prop, identity_sequence=7), org)
    assert existing.friendly_name == "Front Office Printer 7"


def test_unknown_and_wrong_tenant_do_not_receive_precise_identity():
    org_a, org_b, prop, department_id = uuid4(), uuid4(), uuid4(), uuid4()
    department = SimpleNamespace(id=department_id, name="Front Office")
    service = DeterministicIdentity([rule(org_a, prop, department_id)], {department_id: department})
    unknown = service.evaluate(device(prop, hostname="unclassified-host", device_type="Unknown Device", vendor=None, confidence_score=15), org_a)
    isolated = service.evaluate(device(prop), org_b)
    assert unknown.friendly_name is None and unknown.confidence < 50
    assert isolated.friendly_name is None and isolated.rule_ids == []


def test_manual_identity_always_wins_over_new_automatic_evidence():
    org, prop, department_id = uuid4(), uuid4(), uuid4()
    service = DeterministicIdentity([rule(org, prop, department_id)], {department_id: SimpleNamespace(name="Front Office")})
    manual = device(prop, identity_confirmed=True, friendly_name="Reception Desk Printer", department="Front Office", location="Reception")
    result = service.evaluate(manual, org)
    assert result.friendly_name == "Reception Desk Printer"
    assert result.source == "MANUAL" and result.confidence == 100


def test_disabled_and_property_specific_rules_are_isolated():
    org, prop_a, prop_b, department_id = uuid4(), uuid4(), uuid4(), uuid4()
    department = SimpleNamespace(name="Security")
    disabled = rule(org, prop_a, department_id, enabled=False)
    active = rule(org, prop_a, department_id, pattern="SEC")
    service = DeterministicIdentity([disabled, active], {department_id: department})
    assert service.evaluate(device(prop_a, hostname="SEC-PC-01"), org).friendly_name
    assert service.evaluate(device(prop_b, hostname="SEC-PC-01"), org).friendly_name is None
