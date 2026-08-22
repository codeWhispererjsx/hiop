"""Deterministic, explainable, tenant-scoped human device identity."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from sqlalchemy import func, or_

from app.models.discovery_intelligence import DiscoveryEvidence, DiscoveryIdentityProfile, DiscoveryResult, IdentityRule
from app.models.hierarchy import Department, Property
from app.services.audit_service import create_audit_log

UNKNOWN = {"", "unknown", "unknown device", "other", "n/a", "not available"}
VALID_TYPES = {
    "Printer", "POS Terminal", "Desktop", "Laptop", "Server", "Switch", "Router",
    "Firewall", "Access Point", "UPS", "Phone", "Other", "Unknown Device",
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

    def _property(self, result: DiscoveryResult) -> Property | None:
        return self.db.get(Property, result.property_id) if result.property_id else None

    def scoped_rules(self, organization_id, property_id=None, include_disabled=False):
        query = self.db.query(IdentityRule).filter(IdentityRule.organization_id == organization_id)
        query = query.filter(or_(IdentityRule.property_id.is_(None), IdentityRule.property_id == property_id)) if property_id else query.filter(IdentityRule.property_id.is_(None))
        if not include_disabled:
            query = query.filter(IdentityRule.enabled.is_(True))
        return query.order_by(IdentityRule.priority.desc(), IdentityRule.property_id.desc().nullslast(), IdentityRule.created_at.asc()).all()

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
        return IdentityDecision(friendly, device_type, department_name, winner.output_location, score, "RULE", evidence, [str(rule.id) for rule in rules], sequence)

    def apply(self, result: DiscoveryResult, organization_id, actor="System") -> IdentityDecision:
        decision = self.evaluate(result, organization_id)
        profile = self.profile(result, organization_id, create=True)
        profile.suggestion = json.dumps({
            "friendly_name": decision.friendly_name, "device_type": decision.device_type,
            "department": decision.department, "location": decision.location,
            "confidence": decision.confidence, "confidence_level": confidence_level(decision.confidence),
            "source": decision.source, "evidence": decision.evidence, "rule_ids": decision.rule_ids,
        })
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
        if decision.device_type and decision.confidence >= 50:
            result.device_type = decision.device_type; profile.classification_source = decision.source; profile.classification_confidence = decision.confidence
        if decision.department and decision.confidence >= 50:
            result.department = decision.department; result.suggested_department = decision.department; profile.department_source = decision.source
        if decision.location and decision.confidence >= 50:
            result.location = decision.location; profile.location_source = decision.source
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
        return {"matched_rules": [{"id": str(rule.id), "name": rule.name, "priority": rule.priority, "scope": "PROPERTY" if rule.property_id else "ORGANIZATION"} for rule in rules], "suggestion": {"friendly_name": suggestion, "device_type": device_type, "department": department.name if department else None, "location": winner.output_location} if suggestion or device_type else None, "confidence": winner.confidence, "confidence_level": confidence_level(winner.confidence), "evidence": [f'{winner.match_field} {winner.match_operator} "{winner.pattern}"']}
