import json
from types import SimpleNamespace
from uuid import uuid4

from app.api.v1.discovery_intelligence import IdentityRuleWrite
from app.services.device_identity_service import DeviceIdentityService, IdentityDecision, _matches, confidence_level


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


class ReapplyingIdentity(DeviceIdentityService):
    def __init__(self, decisions, profile):
        super().__init__(None)
        self.decisions = decisions
        self.identity_profile = profile

    def profile(self, result, organization_id, create=False):
        return self.identity_profile

    def evaluate(self, result, organization_id):
        return self.decisions.pop(0)

    def _sync_inventory(self, result, profile, previous_suggestion, previous_values, actor):
        pass


class LinkedInventoryIdentity(DeviceIdentityService):
    def __init__(self, devices):
        super().__init__(None)
        self.devices = devices

    def _linked_devices(self, result):
        return self.devices


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
                  suggested_department=None, location=None, identity_sequence=None)
    values.update(overrides); return SimpleNamespace(**values)


def test_deterministic_match_operators_and_confidence_bands():
    assert _matches("FO-PRN-01", "contains", "prn")
    assert _matches("HELLOSHALt1408", "contains", "LT")
    assert _matches("FO-PRN-01", "starts_with", "fo")
    assert _matches("FO-PRN-01", "ends_with", "01")
    assert not _matches("FO-PRN-01", "equals", "FO")
    assert [confidence_level(x) for x in (20, 60, 90)] == ["LOW", "MEDIUM", "HIGH"]


def test_empty_department_id_is_treated_as_unassigned_not_an_invalid_uuid():
    rule = IdentityRuleWrite(
        name="Laptop hostname rule",
        match_field="hostname",
        match_operator="contains",
        pattern="LT",
        output_device_type="Laptop",
        output_department_id="",
    )
    assert rule.output_department_id is None


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


def test_department_only_rule_suggests_department_without_replacing_device_type():
    org, prop, department_id = uuid4(), uuid4(), uuid4()
    department = SimpleNamespace(id=department_id, name="Front Office")
    department_rule = rule(
        org,
        prop,
        department_id,
        output_device_type=None,
    )
    service = DeterministicIdentity([department_rule], {department_id: department})
    result = service.evaluate(device(prop, device_type="Laptop"), org)

    assert result.device_type == "Laptop"
    assert result.department == "Front Office"
    assert result.friendly_name == "Front Office Laptop 1"


def test_department_only_rule_preview_returns_department_without_device_type():
    org, prop, department_id = uuid4(), uuid4(), uuid4()
    department = SimpleNamespace(id=department_id, name="Front Office")
    service = DeterministicIdentity(
        [rule(org, prop, department_id, output_device_type=None)],
        {department_id: department},
    )

    preview = service.preview(
        org,
        prop,
        {"primary_hostname": "FO-PRN-01"},
    )

    assert preview["suggestion"]["department"] == "Front Office"
    assert preview["suggestion"]["device_type"] is None
    assert preview["suggestion"]["friendly_name"] is None


def test_rule_re_evaluation_replaces_only_previously_rule_managed_values():
    profile = SimpleNamespace(
        suggestion="{}",
        classification_source="DISCOVERY",
        classification_confidence=None,
        department_source=None,
        friendly_name_source=None,
        friendly_name_confidence=None,
        identity_sequence=None,
        location_source=None,
        organization_id=uuid4(),
    )
    result = device(
        uuid4(),
        device_type="Unknown Device",
        classification="Unknown Device",
        department=None,
        suggested_department=None,
        identity_confirmed=False,
    )
    decisions = [
        IdentityDecision(
            None, "Laptop", "IT", None, 80, "RULE",
            ["hostname contains LT"], [], None, uuid4(), True, True,
        ),
        IdentityDecision(
            None, "Desktop", "Support", None, 85, "RULE",
            ["hostname contains LT"], [], None, uuid4(), True, True,
        ),
    ]
    service = ReapplyingIdentity(decisions, profile)

    service.apply(result, uuid4())
    assert (result.device_type, result.department) == ("Laptop", "IT")
    service.apply(result, uuid4())

    assert (result.device_type, result.department) == ("Desktop", "Support")
    saved = json.loads(profile.suggestion)
    assert saved["rule_managed"]["device_type"]["baseline"] == "Unknown Device"
    assert saved["rule_managed"]["department"]["baseline"] is None


def test_manual_discovery_values_are_not_overwritten_by_rule_re_evaluation():
    profile = SimpleNamespace(
        suggestion="{}",
        classification_source="MANUAL",
        classification_confidence=100,
        department_source="MANUAL",
        friendly_name_source=None,
        friendly_name_confidence=None,
        identity_sequence=None,
        location_source=None,
        organization_id=uuid4(),
    )
    result = device(
        uuid4(),
        device_type="Manually selected",
        department="Manually assigned",
        identity_confirmed=False,
    )
    service = ReapplyingIdentity(
        [
            IdentityDecision(
                None, "Laptop", "IT", None, 90, "RULE",
                ["hostname contains LT"], [], None, uuid4(), True, True,
            )
        ],
        profile,
    )

    service.apply(result, uuid4())

    assert result.device_type == "Manually selected"
    assert result.department == "Manually assigned"


def test_rule_sync_updates_linked_inventory_and_preserves_manual_edits(monkeypatch):
    monkeypatch.setattr("app.services.device_identity_service.create_audit_log", lambda *args, **kwargs: None)
    device_id, department_id = uuid4(), uuid4()
    inventory = SimpleNamespace(
        id=device_id,
        device_type="Old type",
        department="Old department",
        department_id=None,
    )
    tracked = {
        "device_type": {"baseline": {"value": "Old type"}, "applied": "Old type"},
        "department": {
            "baseline": {"value": "Old department", "department_id": None},
            "applied": "Old department",
            "applied_id": None,
        },
    }
    previous = {
        "inventory_sync": {str(device_id): tracked},
    }
    profile = SimpleNamespace(
        suggestion=json.dumps({
            "rule_managed": {
                "device_type": {"baseline": "Old type"},
                "department": {"baseline": "Old department", "department_id": str(department_id)},
            },
            "inventory_sync": previous["inventory_sync"],
        }),
        classification_source="RULE",
        department_source="RULE",
        organization_id=uuid4(),
    )
    result = SimpleNamespace(
        id=uuid4(),
        property_id=uuid4(),
        identity_confirmed=False,
        device_type="New type",
        department="New department",
    )
    service = LinkedInventoryIdentity([inventory])

    service._sync_inventory(result, profile, previous, {}, "admin")

    assert (inventory.device_type, inventory.department, inventory.department_id) == (
        "New type",
        "New department",
        department_id,
    )
    saved = json.loads(profile.suggestion)["inventory_sync"][str(device_id)]
    assert saved["device_type"]["applied"] == "New type"
    assert saved["department"]["applied_id"] == str(department_id)

    inventory.device_type = "Manually selected"
    result.device_type = "Rule-selected type"
    service._sync_inventory(result, profile, json.loads(profile.suggestion), {}, "admin")

    assert inventory.device_type == "Manually selected"
    assert profile.classification_source == "MANUAL"
    assert "device_type" not in json.loads(profile.suggestion)["rule_managed"]


def test_hostname_rule_overrides_imported_asset_type_and_department(monkeypatch):
    monkeypatch.setattr(
        "app.services.device_identity_service.create_audit_log",
        lambda *args, **kwargs: None,
    )
    organization_id, property_id, department_id = uuid4(), uuid4(), uuid4()
    department = SimpleNamespace(id=department_id, name="Infrastructure")
    hostname_rule = rule(
        organization_id,
        property_id,
        department_id,
        pattern="svr",
        output_device_type="SERVER",
    )
    service = DeterministicIdentity([hostname_rule], {department_id: department})
    asset = SimpleNamespace(
        id=uuid4(),
        property_id=property_id,
        name="SVR-FILE-01",
        source="inventory_import",
        device_type="Windows Computer",
        department_id=None,
        department_name=None,
        field_sources={"device_type": "Inventory import"},
    )

    assert service.apply_managed_asset_rules(asset, organization_id, "admin")

    assert asset.device_type == "Server"
    assert asset.department_id == department_id
    assert asset.department_name == "Infrastructure"
    assert asset.field_sources["device_type"]["source"] == "identity_rule"
    assert asset.field_sources["department"]["source"] == "identity_rule"


def test_hostname_rule_updates_auto_asset_and_linked_device(monkeypatch):
    monkeypatch.setattr(
        "app.services.device_identity_service.create_audit_log",
        lambda *args, **kwargs: None,
    )
    organization_id, property_id, department_id, device_id = (
        uuid4(), uuid4(), uuid4(), uuid4()
    )
    department = SimpleNamespace(id=department_id, name="Front Office")
    inventory_device = SimpleNamespace(
        id=device_id,
        device_type="Windows Computer",
        department="Unassigned",
        department_id=None,
    )
    hostname_rule = rule(
        organization_id,
        property_id,
        department_id,
        pattern="dt",
        output_device_type="Desktop",
    )
    service = DeterministicIdentity([hostname_rule], {department_id: department})
    service.db.get = lambda model, key: (
        inventory_device if key == device_id else {department_id: department}.get(key)
    )
    asset = SimpleNamespace(
        id=uuid4(),
        device_id=device_id,
        property_id=property_id,
        name="HELOSHADTFO1115",
        source="manual",
        device_type="Windows Computer",
        department_id=None,
        department_name=None,
        field_sources={
            "technical_identity": "Device",
            "organizational_metadata": "Imported from existing inventory",
        },
    )

    assert service.apply_managed_asset_rules(asset, organization_id, "admin")

    assert asset.device_type == inventory_device.device_type == "Desktop"
    assert asset.department_name == inventory_device.department == "Front Office"
    assert asset.department_id == inventory_device.department_id == department_id


def test_separate_hostname_rules_compose_device_type_and_department(monkeypatch):
    monkeypatch.setattr(
        "app.services.device_identity_service.create_audit_log",
        lambda *args, **kwargs: None,
    )
    organization_id, property_id, department_id, device_id = (
        uuid4(), uuid4(), uuid4(), uuid4()
    )
    department = SimpleNamespace(id=department_id, name="Front Office")
    inventory_device = SimpleNamespace(
        id=device_id,
        device_type="Windows Computer",
        department="Unassigned",
        department_id=None,
    )
    type_rule = rule(
        organization_id,
        property_id,
        None,
        name="Hostname contains DT = Desktop",
        pattern="dt",
        output_device_type="Desktop",
        output_department_id=None,
    )
    department_rule = rule(
        organization_id,
        property_id,
        department_id,
        name="Hostname contains FO = Front Office",
        pattern="fo",
        output_device_type=None,
    )
    service = DeterministicIdentity(
        [type_rule, department_rule], {department_id: department}
    )
    service.db.get = lambda model, key: (
        inventory_device if key == device_id else {department_id: department}.get(key)
    )
    asset = SimpleNamespace(
        id=uuid4(),
        device_id=device_id,
        property_id=property_id,
        name="HELOSHADTFO1115",
        source="inventory_import",
        device_type="Windows Computer",
        department_id=None,
        department_name=None,
        field_sources={},
    )

    assert service.apply_managed_asset_rules(asset, organization_id, "admin")

    assert asset.device_type == inventory_device.device_type == "Desktop"
    assert asset.department_id == inventory_device.department_id == department_id
    assert asset.department_name == inventory_device.department == "Front Office"
    assert asset.field_sources["device_type"]["rule_id"] == str(type_rule.id)
    assert asset.field_sources["department"]["rule_id"] == str(department_rule.id)


def test_removed_hostname_rule_restores_baseline_but_preserves_manual_changes(monkeypatch):
    monkeypatch.setattr(
        "app.services.device_identity_service.create_audit_log",
        lambda *args, **kwargs: None,
    )
    organization_id, property_id, department_id = uuid4(), uuid4(), uuid4()
    department = SimpleNamespace(id=department_id, name="Infrastructure")
    hostname_rule = rule(
        organization_id,
        property_id,
        department_id,
        pattern="svr",
        output_device_type="Server",
    )
    asset = SimpleNamespace(
        id=uuid4(),
        property_id=property_id,
        name="SVR-FILE-01",
        source="inventory_import",
        device_type="Windows Computer",
        department_id=None,
        department_name=None,
        field_sources={},
    )
    DeterministicIdentity([hostname_rule], {department_id: department}).apply_managed_asset_rules(
        asset, organization_id, "admin"
    )
    asset.device_type = "Administrator-selected type"
    asset.field_sources["device_type"] = "Manual"

    DeterministicIdentity([], {department_id: department}).apply_managed_asset_rules(
        asset, organization_id, "admin"
    )

    assert asset.device_type == "Administrator-selected type"
    assert asset.department_id is None
    assert asset.department_name is None
    assert asset.field_sources["device_type"] == "Manual"


def test_rule_removal_restores_only_unchanged_rule_managed_inventory(monkeypatch):
    monkeypatch.setattr("app.services.device_identity_service.create_audit_log", lambda *args, **kwargs: None)
    device_id, baseline_department_id = uuid4(), uuid4()
    inventory = SimpleNamespace(
        id=device_id,
        device_type="Rule type",
        department="Rule department",
        department_id=uuid4(),
    )
    tracked = {
        "device_type": {"baseline": {"value": "Original type"}, "applied": "Rule type"},
        "department": {
            "baseline": {"value": "Original department", "department_id": str(baseline_department_id)},
            "applied": "Rule department",
            "applied_id": str(inventory.department_id),
        },
    }
    previous = {"inventory_sync": {str(device_id): tracked}}
    profile = SimpleNamespace(
        suggestion=json.dumps({"rule_managed": {}, "inventory_sync": previous["inventory_sync"]}),
        classification_source="DISCOVERY",
        department_source="ACTIVE_DIRECTORY",
        organization_id=uuid4(),
    )
    result = SimpleNamespace(
        id=uuid4(),
        property_id=uuid4(),
        identity_confirmed=False,
        device_type="Original type",
        department="Original department",
    )

    LinkedInventoryIdentity([inventory])._sync_inventory(result, profile, previous, {}, "admin")

    assert inventory.device_type == "Original type"
    assert inventory.department == "Original department"
    assert inventory.department_id == baseline_department_id
    assert json.loads(profile.suggestion)["inventory_sync"] == {}


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
