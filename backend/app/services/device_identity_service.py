"""Deterministic, explainable, tenant-scoped human device identity."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import or_, select

from app.models.device import Device
from app.models.discovered_device import DiscoveredDevice
from app.models.discovery_intelligence import (
    DiscoveryApprovalLink,
    DiscoveryIdentityProfile,
    DiscoveryResult,
    IdentityRule,
)
from app.models.hierarchy import Department, Property
from app.services.audit_service import create_audit_log

UNKNOWN = {"", "unknown", "unknown device", "other", "n/a", "not available"}
VALID_TYPES = {
    "Printer", "POS Terminal", "Desktop", "Laptop", "Windows Computer", "Server", "Switch", "Router",
    "Firewall", "Access Point", "UPS", "Phone", "Camera", "CCTV Camera", "Security Device", "Other", "Unknown Device",
}
SOURCE_RANK = {"MANUAL": 100, "DISCOVERY": 90, "ACTIVE_DIRECTORY": 80, "RULE": 70, "INFERENCE": 40}


@dataclass(frozen=True)
class IdentityDecision:
    friendly_name: str | None
    device_type: str | None
    department: str | None
    location: str | None
    confidence: int
    source: str
    evidence: list[str]
    rule_ids: list[str]
    sequence: int | None = None
    department_id: UUID | None = None
    rule_device_type: bool = False
    rule_department: bool = False


def confidence_level(score: int) -> str:
    return "HIGH" if score >= 80 else "MEDIUM" if score >= 50 else "LOW"


def _matches(value: str | None, operator: str, pattern: str) -> bool:
    left, right = str(value or "").strip().casefold(), pattern.strip().casefold()
    if not left or not right:
        return False
    return {"contains": right in left, "starts_with": left.startswith(right), "ends_with": left.endswith(right), "equals": left == right}[operator]


def _safe_type(value: str | None) -> str | None:
    if not value:
        return None
    aliases = {"PC": "Desktop", "Point of Sale": "POS Terminal", "Wireless AP": "Access Point", "IP Phone": "Phone"}
    value = aliases.get(value, value)
    return value if value in VALID_TYPES else "Other"


class DeviceIdentityService:
    """Uses only stored evidence and configured rules; it never guesses from global hotel tokens."""

    def __init__(self, db):
        self.db = db
        self._rule_cache = {}

    def _property(self, result: DiscoveryResult) -> Property | None:
        return self.db.get(Property, result.property_id) if result.property_id else None

    def scoped_rules(self, organization_id, property_id=None, include_disabled=False):
        cache_key = (organization_id, property_id, include_disabled)
        if cache_key in self._rule_cache:
            return self._rule_cache[cache_key]
        query = self.db.query(IdentityRule).filter(IdentityRule.organization_id == organization_id)
        query = query.filter(or_(IdentityRule.property_id.is_(None), IdentityRule.property_id == property_id)) if property_id else query.filter(IdentityRule.property_id.is_(None))
        if not include_disabled:
            query = query.filter(IdentityRule.enabled.is_(True))
        rules = query.order_by(IdentityRule.priority.desc(), IdentityRule.property_id.desc().nullslast(), IdentityRule.created_at.asc()).all()
        self._rule_cache[cache_key] = rules
        return rules

    @staticmethod
    def _suggestion(profile: DiscoveryIdentityProfile) -> dict:
        try:
            value = json.loads(profile.suggestion or "{}")
        except (TypeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _normalized(value):
        normalized = str(value or "").strip().casefold()
        return "" if normalized in {"unassigned", "unknown", "unknown device"} else normalized

    def _linked_devices(self, result: DiscoveryResult) -> list[Device]:
        result_ids = [result.id]
        result_ids.extend(
            self.db.scalars(
                select(DiscoveryResult.id).where(
                    DiscoveryResult.canonical_result_id == result.id
                )
            ).all()
        )
        device_ids = set(
            self.db.scalars(
                select(DiscoveryApprovalLink.device_id).where(
                    DiscoveryApprovalLink.result_id.in_(result_ids)
                )
            ).all()
        )
        discovered_ids = self.db.scalars(
            select(DiscoveryResult.discovered_device_id).where(
                DiscoveryResult.id.in_(result_ids),
                DiscoveryResult.discovered_device_id.is_not(None),
            )
        ).all()
        if discovered_ids:
            device_ids.update(
                self.db.scalars(
                    select(DiscoveredDevice.approved_device_id).where(
                        DiscoveredDevice.id.in_(discovered_ids),
                        DiscoveredDevice.approved_device_id.is_not(None),
                    )
                ).all()
            )
        return list(self.db.scalars(select(Device).where(Device.id.in_(device_ids))).all()) if device_ids else []

    def _sync_inventory(
        self,
        result: DiscoveryResult,
        profile: DiscoveryIdentityProfile,
        previous_suggestion: dict,
        previous_values: dict[str, object],
        actor: str,
    ) -> None:
        if result.identity_confirmed:
            return
        suggestion = self._suggestion(profile)
        rule_fields = suggestion.get("rule_managed", {})
        sync_state = suggestion.get("inventory_sync", {})
        previous_sync = previous_suggestion.get("inventory_sync", {})
        if not isinstance(rule_fields, dict) or not isinstance(sync_state, dict):
            return
        if not isinstance(previous_sync, dict):
            previous_sync = {}
        devices = self._linked_devices(result)
        changed_by_device: dict[str, set[str]] = {}
        for device in devices:
            device_key = str(device.id)
            device_sync = sync_state.get(device_key, {})
            if not isinstance(device_sync, dict):
                device_sync = {}
            previous_device_sync = previous_sync.get(device_key, {})
            if not isinstance(previous_device_sync, dict):
                previous_device_sync = {}
            for field, device_attr in (("device_type", "device_type"), ("department", "department")):
                state = rule_fields.get(field)
                if not isinstance(state, dict):
                    state = None
                tracked = device_sync.get(field) or previous_device_sync.get(field)
                source = profile.classification_source if field == "device_type" else profile.department_source
                target_value = getattr(result, field)

                if source == "MANUAL":
                    continue
                if state:
                    previous_value = tracked.get("applied") if isinstance(tracked, dict) else previous_values.get(field)
                    current_value = getattr(device, device_attr)
                    changed_manually = self._normalized(current_value) != self._normalized(previous_value)
                    if field == "department" and isinstance(tracked, dict):
                        changed_manually = changed_manually or tracked.get("applied_id") != (
                            str(device.department_id) if device.department_id else None
                        )
                    if changed_manually:
                        if field == "device_type":
                            profile.classification_source = "MANUAL"
                        else:
                            profile.department_source = "MANUAL"
                        device_sync.pop(field, None)
                        rule_fields.pop(field, None)
                        continue
                    baseline = tracked.get("baseline") if isinstance(tracked, dict) else None
                    if baseline is None:
                        if field == "department":
                            baseline = {
                                "value": previous_values.get(field) or "Unassigned",
                                "department_id": (
                                    str(device.department_id) if device.department_id else None
                                ),
                            }
                        else:
                            baseline = {"value": previous_values.get(field) or "Unknown Device"}
                    if field == "department":
                        department_id = state.get("department_id")
                        desired_id = UUID(department_id) if department_id else None
                        if self._normalized(current_value) != self._normalized(target_value) or device.department_id != desired_id:
                            device.department = target_value or "Unassigned"
                            device.department_id = desired_id
                            changed_by_device.setdefault(str(device.id), set()).add(field)
                        device_sync[field] = {
                            "baseline": baseline,
                            "applied": target_value,
                            "applied_id": department_id,
                        }
                    else:
                        if self._normalized(current_value) != self._normalized(target_value):
                            device.device_type = target_value
                            changed_by_device.setdefault(str(device.id), set()).add(field)
                        device_sync[field] = {"baseline": baseline, "applied": target_value}
                    continue

                if isinstance(tracked, dict):
                    current_value = getattr(device, device_attr)
                    unchanged = self._normalized(current_value) == self._normalized(tracked.get("applied"))
                    if field == "department":
                        unchanged = unchanged and tracked.get("applied_id") == (
                            str(device.department_id) if device.department_id else None
                        )
                    if unchanged:
                        baseline = tracked.get("baseline", {})
                        if field == "department":
                            device.department = baseline.get("value") or "Unassigned"
                            device.department_id = UUID(baseline["department_id"]) if baseline.get("department_id") else None
                        else:
                            device.device_type = baseline.get("value") or "Unknown Device"
                        changed_by_device.setdefault(str(device.id), set()).add(field)
                        device_sync.pop(field, None)
                    else:
                        if field == "device_type":
                            profile.classification_source = "MANUAL"
                        else:
                            profile.department_source = "MANUAL"
                        device_sync.pop(field, None)

            if device_sync:
                sync_state[str(device.id)] = device_sync
            else:
                sync_state.pop(str(device.id), None)

        for device_id, fields in changed_by_device.items():
            create_audit_log(
                self.db,
                actor,
                "IDENTITY_RULE_INVENTORY_SYNC",
                "Device",
                device_id,
                f"Synchronized rule-managed identity fields: {', '.join(sorted(fields))}",
                organization_id=profile.organization_id,
                property_id=result.property_id,
            )
        suggestion["rule_managed"] = rule_fields
        suggestion["inventory_sync"] = sync_state
        profile.suggestion = json.dumps(suggestion)

    def sync_approved_inventory(
        self,
        result: DiscoveryResult,
        device: Device,
        organization_id,
        actor: str,
    ) -> None:
        profile = self.profile(result, organization_id, create=False)
        if not profile or result.identity_confirmed:
            return
        suggestion = self._suggestion(profile)
        rule_fields = suggestion.get("rule_managed", {})
        if not isinstance(rule_fields, dict):
            return
        sync_state = suggestion.get("inventory_sync", {})
        if not isinstance(sync_state, dict):
            sync_state = {}
        device_sync = sync_state.get(str(device.id), {})
        if not isinstance(device_sync, dict):
            device_sync = {}
        initialized = []
        for field, value in (("device_type", device.device_type), ("department", device.department)):
            state = rule_fields.get(field)
            if not isinstance(state, dict):
                continue
            source = profile.classification_source if field == "device_type" else profile.department_source
            if not state or source != "RULE":
                continue
            if self._normalized(value) != self._normalized(getattr(result, field)):
                if field == "device_type":
                    result.device_type = device.device_type
                else:
                    result.department = device.department
                if field == "device_type":
                    profile.classification_source = "MANUAL"
                else:
                    profile.department_source = "MANUAL"
                continue
            if field == "department":
                baseline = {
                    "value": state.get("baseline") or "Unassigned",
                    "department_id": None,
                }
                device_sync[field] = {
                    "baseline": baseline,
                    "applied": device.department,
                    "applied_id": str(device.department_id) if device.department_id else None,
                }
            else:
                device_sync[field] = {
                    "baseline": {"value": state.get("baseline") or "Unknown Device"},
                    "applied": device.device_type,
                }
            initialized.append(field)
        suggestion["rule_managed"] = rule_fields
        sync_state[str(device.id)] = device_sync
        suggestion["inventory_sync"] = sync_state
        profile.suggestion = json.dumps(suggestion)
        if initialized:
            create_audit_log(
                self.db,
                actor,
                "IDENTITY_RULE_INVENTORY_SYNC",
                "Device",
                str(device.id),
                f"Initialized rule-managed identity fields: {', '.join(sorted(initialized))}",
                organization_id=organization_id,
                property_id=result.property_id,
            )

    def mark_inventory_identity_manual(
        self,
        device: Device,
        fields: set[str],
        organization_id,
    ) -> None:
        if not fields:
            return
        result_ids = set(
            self.db.scalars(
                select(DiscoveryApprovalLink.result_id).where(
                    DiscoveryApprovalLink.device_id == device.id
                )
            ).all()
        )
        result_ids.update(
            self.db.scalars(
                select(DiscoveryResult.id)
                .join(
                    DiscoveredDevice,
                    DiscoveryResult.discovered_device_id == DiscoveredDevice.id,
                )
                .where(DiscoveredDevice.approved_device_id == device.id)
            ).all()
        )
        for result in self.db.scalars(
            select(DiscoveryResult).where(DiscoveryResult.id.in_(result_ids))
        ).all():
            profile = self.profile(result, organization_id, create=True)
            suggestion = self._suggestion(profile)
            sync_state = suggestion.get("inventory_sync", {})
            if not isinstance(sync_state, dict):
                sync_state = {}
            device_sync = sync_state.get(str(device.id), {})
            if not isinstance(device_sync, dict):
                device_sync = {}
            rule_managed = suggestion.get("rule_managed", {})
            if not isinstance(rule_managed, dict):
                rule_managed = {}
            if "device_type" in fields:
                result.device_type = device.device_type
                profile.classification_source = "MANUAL"
                profile.classification_confidence = 100
                device_sync.pop("device_type", None)
                rule_managed.pop("device_type", None)
            if "department" in fields:
                result.department = device.department
                profile.department_source = "MANUAL"
                device_sync.pop("department", None)
                rule_managed.pop("department", None)
            if device_sync:
                sync_state[str(device.id)] = device_sync
            else:
                sync_state.pop(str(device.id), None)
            suggestion["rule_managed"] = rule_managed
            suggestion["inventory_sync"] = sync_state
            profile.suggestion = json.dumps(suggestion)

    def reevaluate_rules(self, organization_id, property_id, actor: str) -> dict[str, int]:
        query = (
            self.db.query(DiscoveryResult)
            .join(Property, DiscoveryResult.property_id == Property.id)
            .filter(
                Property.organization_id == organization_id,
                DiscoveryResult.canonical_result_id.is_(None),
            )
        )
        if property_id:
            query = query.filter(DiscoveryResult.property_id == property_id)
        results = query.order_by(DiscoveryResult.id).all()
        updated = 0
        for result in results:
            decision = self.apply(result, organization_id, actor)
            if decision.rule_ids:
                updated += 1
        return {"evaluated": len(results), "matched": updated}

    @staticmethod
    def _input(result: DiscoveryResult, field: str) -> str | None:
        return {
            "hostname": result.primary_hostname,
            "fqdn": result.fqdn,
            "vendor": result.vendor,
            "snmp": result.sys_description,
            "ad_ou": result.ad_organizational_unit,
            "device_type": result.device_type,
        }.get(field)

    def matching_rules(self, result: DiscoveryResult, organization_id) -> list[IdentityRule]:
        return [rule for rule in self.scoped_rules(organization_id, result.property_id) if _matches(self._input(result, rule.match_field), rule.match_operator, rule.pattern)]

    def profile(self, result: DiscoveryResult, organization_id, create=False):
        row = self.db.query(DiscoveryIdentityProfile).filter(DiscoveryIdentityProfile.result_id == result.id, DiscoveryIdentityProfile.organization_id == organization_id).first()
        if not row and create:
            row = DiscoveryIdentityProfile(result_id=result.id, organization_id=organization_id, property_id=result.property_id)
            self.db.add(row); self.db.flush()
        return row

    def _next_sequence(self, result: DiscoveryResult, department: str, device_type: str) -> int:
        profile = self.profile(result, self._property(result).organization_id, create=True)
        if profile.identity_sequence:
            return profile.identity_sequence
        prefix = f"{department} {device_type} ".casefold()
        values = self.db.query(DiscoveryResult.friendly_name, DiscoveryIdentityProfile.identity_sequence).join(DiscoveryIdentityProfile, DiscoveryIdentityProfile.result_id == DiscoveryResult.id).filter(DiscoveryResult.property_id == result.property_id, DiscoveryResult.id != result.id, DiscoveryResult.canonical_result_id.is_(None), DiscoveryResult.friendly_name.is_not(None)).all()
        used = {int(sequence) for name, sequence in values if sequence and str(name).casefold().startswith(prefix)}
        number = 1
        while number in used:
            number += 1
        return number

    def evaluate(self, result: DiscoveryResult, organization_id) -> IdentityDecision:
        if result.identity_confirmed:
            profile = self.profile(result, organization_id, create=False)
            return IdentityDecision(result.friendly_name, result.device_type, result.department, result.location, 100, "MANUAL", ["Administrator-confirmed identity"], [], profile.identity_sequence if profile else None)
        rules = self.matching_rules(result, organization_id)
        if not rules:
            evidence = []
            if result.device_type and result.device_type.casefold() not in UNKNOWN:
                evidence.append(f"Discovery classified the device as {result.device_type}")
            return IdentityDecision(None, _safe_type(result.device_type), None, None, min(result.confidence_score or 0, 49), "DISCOVERY" if evidence else "INFERENCE", evidence, [])
        winner = rules[0]
        department = self.db.get(Department, winner.output_department_id) if winner.output_department_id else None
        device_type = _safe_type(winner.output_device_type) or _safe_type(result.device_type)
        department_name = department.name if department else None
        evidence = [f'{winner.match_field.replace("_", " ").title()} {winner.match_operator.replace("_", " ")} "{winner.pattern}"']
        score = winner.confidence
        if device_type and result.device_type and device_type.casefold() == result.device_type.casefold():
            score = min(100, score + 10); evidence.append(f"Discovery agrees on device type: {device_type}")
        if result.vendor:
            evidence.append(f"Observed vendor: {result.vendor}")
        sequence = self._next_sequence(result, department_name or "", device_type or "Device") if department_name and device_type and score >= 50 else None
        friendly = None
        if sequence:
            values = {"department": department_name, "device_type": device_type, "location": winner.output_location or "", "sequence": sequence, "hostname": result.primary_hostname or ""}
            try:
                friendly = re.sub(r"\s+", " ", winner.friendly_name_template.format_map(values)).strip()[:120]
            except (KeyError, ValueError):
                friendly = f"{department_name} {device_type} {sequence}"[:120]
        return IdentityDecision(
            friendly,
            device_type,
            department_name,
            winner.output_location,
            score,
            "RULE",
            evidence,
            [str(rule.id) for rule in rules],
            sequence,
            winner.output_department_id,
            winner.output_device_type is not None,
            winner.output_department_id is not None,
        )

    def apply(self, result: DiscoveryResult, organization_id, actor="System") -> IdentityDecision:
        profile = self.profile(result, organization_id, create=True)
        if result.identity_confirmed:
            return self.evaluate(result, organization_id)
        previous_suggestion = self._suggestion(profile)
        previous_values = {
            "device_type": result.device_type,
            "department": result.department,
        }
        previous_managed = previous_suggestion.get("rule_managed", {})
        if not isinstance(previous_managed, dict):
            previous_managed = {}
        manual_type = profile.classification_source == "MANUAL"
        manual_department = profile.department_source == "MANUAL"

        type_state = previous_managed.get("device_type", {})
        if not isinstance(type_state, dict):
            type_state = {}
        if profile.classification_source == "RULE":
            result.device_type = type_state.get("baseline") or result.classification or "Unknown Device"
        department_state = previous_managed.get("department", {})
        if not isinstance(department_state, dict):
            department_state = {}
        if profile.department_source == "RULE":
            result.department = department_state.get("baseline") or result.suggested_department

        baseline_values = {
            "device_type": result.device_type,
            "department": result.department,
        }
        baseline_sources = {
            "device_type": type_state.get("baseline_source") if profile.classification_source == "RULE" else "DISCOVERY",
            "department": department_state.get("baseline_source") if profile.department_source == "RULE" else (
                "ACTIVE_DIRECTORY" if result.suggested_department else None
            ),
        }
        decision = self.evaluate(result, organization_id)
        rule_managed = {}
        if decision.rule_device_type and decision.confidence >= 50 and not manual_type:
            result.device_type = decision.device_type or baseline_values["device_type"] or "Unknown Device"
            profile.classification_source = "RULE"
            profile.classification_confidence = decision.confidence
            rule_managed["device_type"] = {
                "baseline": baseline_values["device_type"],
                "baseline_source": baseline_sources["device_type"],
                "applied": result.device_type,
            }
        else:
            if profile.classification_source == "RULE" and not manual_type:
                result.device_type = baseline_values["device_type"] or "Unknown Device"
                profile.classification_source = baseline_sources["device_type"]
                profile.classification_confidence = None
            elif not manual_type and decision.device_type:
                result.device_type = decision.device_type

        if decision.rule_department and decision.confidence >= 50 and not manual_department:
            result.department = decision.department
            profile.department_source = "RULE"
            rule_managed["department"] = {
                "baseline": baseline_values["department"],
                "baseline_source": baseline_sources["department"],
                "department_id": str(decision.department_id) if decision.department_id else None,
                "applied": result.department,
            }
        else:
            if profile.department_source == "RULE" and not manual_department:
                result.department = baseline_values["department"]
                profile.department_source = baseline_sources["department"]
            elif not manual_department and decision.department:
                result.department = decision.department

        if result.identity_confirmed:
            return decision
        if decision.friendly_name and decision.confidence >= 50:
            changed = result.friendly_name != decision.friendly_name
            result.friendly_name = decision.friendly_name
            profile.friendly_name_source = decision.source
            profile.friendly_name_confidence = decision.confidence
            profile.identity_sequence = decision.sequence
            if changed:
                create_audit_log(self.db, actor, "IDENTITY_GENERATED", "discovery_result", str(result.id), f"Generated friendly identity from configured rule at {decision.confidence}% confidence", organization_id=organization_id, property_id=result.property_id)
        if decision.rule_device_type and decision.confidence >= 50 and not manual_type:
            profile.classification_confidence = decision.confidence
        if decision.rule_department and decision.confidence >= 50 and not manual_department:
            profile.department_source = "RULE"
        if decision.location and decision.confidence >= 50:
            result.location = decision.location
            profile.location_source = decision.source
        suggestion = {
            "friendly_name": decision.friendly_name, "device_type": decision.device_type,
            "department": decision.department, "location": decision.location,
            "confidence": decision.confidence, "confidence_level": confidence_level(decision.confidence),
            "source": decision.source, "evidence": decision.evidence, "rule_ids": decision.rule_ids,
            "rule_managed": rule_managed,
            "inventory_sync": previous_suggestion.get("inventory_sync", {}),
        }
        profile.suggestion = json.dumps(suggestion)
        self._sync_inventory(result, profile, previous_suggestion, previous_values, actor)
        if decision.rule_ids:
            create_audit_log(self.db, actor, "IDENTITY_RULE_APPLIED", "discovery_result", str(result.id), f"Applied {len(decision.rule_ids)} scoped identity rule(s)", organization_id=organization_id, property_id=result.property_id)
        return decision

    def preview(self, organization_id, property_id, values: dict):
        sample = DiscoveryResult(property_id=property_id, job_id=values.get("job_id"), ip_address=values.get("ip_address", "0.0.0.0"))
        for field in ("primary_hostname", "fqdn", "vendor", "sys_description", "ad_organizational_unit", "device_type"):
            setattr(sample, field, values.get(field))
        sample.id = values.get("result_id")
        # Preview must not allocate or persist identity state.
        rules = [rule for rule in self.scoped_rules(organization_id, property_id) if _matches(self._input(sample, rule.match_field), rule.match_operator, rule.pattern)]
        if not rules:
            return {"matched_rules": [], "suggestion": None, "confidence": 0, "confidence_level": "LOW", "evidence": ["No configured rule matched"]}
        winner = rules[0]; department = self.db.get(Department, winner.output_department_id) if winner.output_department_id else None
        device_type = _safe_type(winner.output_device_type) or _safe_type(sample.device_type)
        suggestion = None
        if department and device_type:
            suggestion = winner.friendly_name_template.format_map({"department": department.name, "device_type": device_type, "location": winner.output_location or "", "sequence": "#", "hostname": sample.primary_hostname or ""})
        return {"matched_rules": [{"id": str(rule.id), "name": rule.name, "priority": rule.priority, "scope": "PROPERTY" if rule.property_id else "ORGANIZATION"} for rule in rules], "suggestion": {"friendly_name": suggestion, "device_type": device_type, "department": department.name if department else None, "location": winner.output_location} if department or device_type else None, "confidence": winner.confidence, "confidence_level": confidence_level(winner.confidence), "evidence": [f'{winner.match_field} {winner.match_operator} "{winner.pattern}"']}
