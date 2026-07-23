"""Explainable, conservative matching for staged Active Directory objects."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from fnmatch import fnmatchcase
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.models.active_directory import (
    ActiveDirectoryConnection,
    ActiveDirectoryDepartmentMapping,
    ActiveDirectoryGroupRoleMapping,
    ActiveDirectoryOUMapping,
    ActiveDirectoryMatchCandidate,
    ActiveDirectoryObject,
    ActiveDirectoryRecordLink,
)
from app.models.device import Device
from app.models.discovered_device import DiscoveredDevice
from app.models.hierarchy import Department
from app.models.user import User
from app.models.system_setting import SystemSetting
from app.services.audit_service import create_audit_log
from app.services.email_service import send_email
from app.services.settings_service import DEFAULTS
from app.services.settings_service import read_ad_matching_settings
from app.websocket.connection_manager import manager


def normalized(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def similarity(left: Any, right: Any) -> int:
    a, b = normalized(left), normalized(right)
    return round(SequenceMatcher(None, a, b).ratio() * 100) if a and b else 0


def score_level(score: float, settings: dict[str, Any]) -> str:
    if score >= settings["exact_threshold"]:
        return "exact"
    if score >= settings["strong_threshold"]:
        return "strong"
    if score >= settings["probable_threshold"]:
        return "probable"
    if score >= settings["weak_threshold"]:
        return "weak"
    return "none"


def _result(score: float, matching: list[str], conflicts: list[dict], evidence: list[dict],
            settings: dict[str, Any]) -> dict[str, Any]:
    bounded = max(0, min(100, score))
    level = score_level(bounded, settings)
    return {
        "score": bounded, "level": level, "matching_fields": matching,
        "conflicting_fields": conflicts, "evidence": {"signals": evidence},
        "recommended_action": "conflict" if conflicts else "link" if level in {"exact", "strong"} else "review",
    }


def score_user(source: ActiveDirectoryObject, target: User, settings: dict[str, Any]) -> dict[str, Any]:
    score, matching, conflicts, evidence = 0.0, [], [], []
    source_email, target_email = normalized(source.email), normalized(target.email)
    upn, username = normalized(source.user_principal_name), normalized(target.username)
    sam = normalized(source.sam_account_name)
    if source_email and source_email == target_email:
        score += 96; matching.append("email"); evidence.append({"field": "email", "kind": "exact", "weight": 96})
    elif source_email and target_email:
        score -= settings["conflict_penalty"]; conflicts.append({"field": "email", "source": source_email, "target": target_email})
    if upn and (upn == target_email or upn == username):
        score += 94; matching.append("user_principal_name"); evidence.append({"field": "user_principal_name", "kind": "exact", "weight": 94})
    if sam and sam == username:
        score += 88; matching.append("username"); evidence.append({"field": "username", "kind": "exact", "weight": 88})
    elif sam and username and similarity(sam, username) >= 88:
        score += 38; evidence.append({"field": "username", "kind": "similar", "similarity": similarity(sam, username), "weight": 38})
    source_name = normalized(source.display_name or source.common_name)
    if source_name and similarity(source_name, target.username) >= 90:
        score += 24; evidence.append({"field": "display_name", "kind": "similar", "similarity": similarity(source_name, target.username), "weight": 24})
    # Multiple independent exact identities cap at 100; fuzzy-only never becomes exact.
    if not any(field in matching for field in ("email", "user_principal_name", "username")):
        score = min(score, settings["strong_threshold"] - 1)
    return _result(score, matching, conflicts, evidence, settings)


def score_device(source: ActiveDirectoryObject, target: Device, settings: dict[str, Any],
                 discovery: DiscoveredDevice | None = None) -> dict[str, Any]:
    score, matching, conflicts, evidence = 0.0, [], [], []
    dns = normalized(source.dns_hostname)
    short = normalized(source.sam_account_name).removesuffix("$")
    hostname = normalized(target.hostname)
    if dns and dns == hostname:
        score += 96; matching.append("dns_hostname"); evidence.append({"field": "dns_hostname", "kind": "exact", "weight": 96})
    elif short and short == hostname:
        score += 88; matching.append("hostname"); evidence.append({"field": "hostname", "kind": "exact", "weight": 88})
    elif (dns or short) and similarity(dns or short, hostname) >= 88:
        score += 45; evidence.append({"field": "hostname", "kind": "similar", "similarity": similarity(dns or short, hostname), "weight": 45})
    if discovery:
        if normalized(discovery.mac_address) and normalized(discovery.mac_address) == normalized(target.mac_address):
            score += 94; matching.append("discovery_mac"); evidence.append({"field": "mac_address", "kind": "discovery_exact", "weight": 94})
        elif discovery.mac_address and target.mac_address:
            score -= settings["conflict_penalty"]; conflicts.append({"field": "mac_address", "source": discovery.mac_address, "target": target.mac_address})
        if discovery.ip_address and discovery.ip_address == target.ip_address:
            score += 55; matching.append("discovery_ip"); evidence.append({"field": "ip_address", "kind": "discovery_exact", "weight": 55})
    if source.department and normalized(source.department) == normalized(target.department):
        score += 12; matching.append("department"); evidence.append({"field": "department", "kind": "exact", "weight": 12})
    if "hostname" in matching and not any(field in matching for field in ("dns_hostname", "discovery_mac")):
        score = min(score, settings["exact_threshold"] - 1)
    if not any(field in matching for field in ("dns_hostname", "hostname", "discovery_mac")):
        score = min(score, settings["strong_threshold"] - 1)
    return _result(score, matching, conflicts, evidence, settings)


def score_discovery(source: ActiveDirectoryObject, target: DiscoveredDevice,
                    settings: dict[str, Any]) -> dict[str, Any]:
    source_host = normalized(source.dns_hostname or source.sam_account_name).removesuffix("$")
    target_host = normalized(target.hostname)
    if source_host and source_host == target_host:
        return _result(90, ["hostname"], [], [{"field": "hostname", "kind": "exact", "weight": 90}], settings)
    value = similarity(source_host, target_host)
    return _result(45 if value >= 88 else 0, [], [], [{"field": "hostname", "kind": "similar", "similarity": value, "weight": 45}], settings)


class ActiveDirectoryMatchingService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _notify(self, summary: dict[str, int]) -> None:
        try:
            stored = {row.key: row.value for row in self.db.query(SystemSetting).filter(
                SystemSetting.key.in_(("notifications.email_notifications", "notifications.recipient_email"))
            ).all()}
            if stored.get("notifications.email_notifications", DEFAULTS["notifications.email_notifications"]).lower() == "true":
                send_email(
                    subject="HIOP directory matching completed",
                    body=(
                        f"Candidates: {summary.get('candidates', 0)}; "
                        f"conflicts: {summary.get('conflicts', 0)}; "
                        f"unmatched: {summary.get('unmatched', 0)}."
                    ),
                    recipient=stored.get("notifications.recipient_email") or None,
                )
        except Exception:
            # Notification delivery must not roll back completed matching.
            pass

    def _object(self, object_id: str) -> ActiveDirectoryObject:
        obj = self.db.get(ActiveDirectoryObject, object_id)
        if not obj:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Directory object was not found.")
        return obj

    def _existing_link_candidate(self, obj: ActiveDirectoryObject):
        return self.db.scalar(select(ActiveDirectoryRecordLink).where(
            ActiveDirectoryRecordLink.directory_object_id == obj.id
        ))

    def _user_candidates(self, obj, settings):
        exact = self.db.scalars(select(User).where(or_(
            func.lower(User.email).in_([normalized(obj.email), normalized(obj.user_principal_name)]),
            func.lower(User.username) == normalized(obj.sam_account_name),
        )).limit(25)).all()
        pool = list(exact)
        if settings["fuzzy_enabled"] and len(pool) < 25:
            pool.extend(self.db.scalars(select(User).order_by(User.updated_at.desc()).limit(200)).all())
        unique = {item.id: item for item in pool}
        return [(user, score_user(obj, user, settings)) for user in unique.values()]

    def _device_candidates(self, obj, settings):
        names = {normalized(obj.dns_hostname), normalized(obj.sam_account_name).removesuffix("$")}
        names.discard("")
        devices = list(self.db.scalars(select(Device).where(func.lower(Device.hostname).in_(names)).limit(50)).all())
        discoveries = list(self.db.scalars(select(DiscoveredDevice).where(
            func.lower(DiscoveredDevice.hostname).in_(names)
        ).limit(25)).all())
        linked_discovery = next((item for item in discoveries if item.approved_device_id), None)
        if linked_discovery and all(item.id != linked_discovery.approved_device_id for item in devices):
            linked = self.db.get(Device, linked_discovery.approved_device_id)
            if linked: devices.append(linked)
        if settings["fuzzy_enabled"] and len(devices) < 25:
            devices.extend(self.db.scalars(select(Device).order_by(Device.updated_at.desc()).limit(200)).all())
        return (
            [(item, score_device(obj, item, settings, linked_discovery)) for item in {d.id: d for d in devices}.values()],
            [(item, score_discovery(obj, item, settings)) for item in discoveries],
        )

    def _mapping_candidates(self, obj, settings):
        candidates = []
        if obj.department and settings["department_mapping_enabled"]:
            aliases = self.db.scalars(select(ActiveDirectoryDepartmentMapping).where(
                ActiveDirectoryDepartmentMapping.connection_id == obj.connection_id,
                ActiveDirectoryDepartmentMapping.enabled.is_(True),
                func.lower(ActiveDirectoryDepartmentMapping.source_value) == normalized(obj.department),
            )).all()
            departments = [self.db.get(Department, row.department_id) for row in aliases]
            departments += self.db.scalars(select(Department).where(
                func.lower(Department.name) == normalized(obj.department)
            )).all()
            for department in {d.id: d for d in departments if d}.values():
                candidates.append(("department", department, _result(
                    95, ["department"], [], [{"field": "department", "kind": "mapped_exact", "weight": 95}], settings
                )))
        if obj.object_type == "group" and settings["role_mapping_enabled"]:
            name = normalized(obj.sam_account_name or obj.common_name)
            mappings = self.db.scalars(select(ActiveDirectoryGroupRoleMapping).where(
                ActiveDirectoryGroupRoleMapping.connection_id == obj.connection_id,
                ActiveDirectoryGroupRoleMapping.enabled.is_(True),
                func.lower(ActiveDirectoryGroupRoleMapping.source_group) == name,
            )).all()
            for mapping in mappings:
                result = _result(98, ["group"], [], [{
                    "field": "group", "kind": "explicit_mapping", "weight": 98,
                    "privileged": mapping.target_role == "admin",
                    "requires_confirmation": mapping.requires_confirmation,
                }], settings)
                result["recommended_action"] = "review"
                candidates.append(("role", mapping, result))
        if obj.organizational_unit and settings["ou_mapping_enabled"]:
            rules = self.db.scalars(select(ActiveDirectoryOUMapping).where(
                ActiveDirectoryOUMapping.connection_id == obj.connection_id,
                ActiveDirectoryOUMapping.enabled.is_(True),
            ).order_by(ActiveDirectoryOUMapping.priority, ActiveDirectoryOUMapping.id)).all()
            matched = [
                rule for rule in rules
                if fnmatchcase(normalized(obj.organizational_unit), normalized(rule.pattern))
            ]
            ambiguous = len(matched) > 1 and matched[0].priority == matched[1].priority
            for rule in matched[:1]:
                if rule.department_id:
                    department = self.db.get(Department, rule.department_id)
                    if department:
                        conflicts = [{"field": "organizational_unit", "code": "ambiguous_rules"}] if ambiguous else []
                        result = _result(
                            90, ["organizational_unit"], conflicts,
                            [{"field": "organizational_unit", "kind": "ordered_rule",
                              "rule_id": rule.id, "priority": rule.priority, "weight": 90}],
                            settings,
                        )
                        candidates.append(("department", department, result))
        return candidates

    def generate_for_object(self, obj: ActiveDirectoryObject, settings: dict[str, Any]) -> list[ActiveDirectoryMatchCandidate]:
        scored: list[tuple[str, Any, dict]] = []
        link = self._existing_link_candidate(obj)
        if link:
            target = self.db.get(User, link.user_id) if link.user_id else self.db.get(Device, link.device_id)
            if target:
                scored.append(("hiop_user" if link.user_id else "hiop_device", target, _result(
                    100, ["directory_link"], [], [{"field": "object_guid", "kind": "existing_link", "weight": 100}], settings
                )))
        if obj.object_type == "user":
            scored.extend(("hiop_user", target, result) for target, result in self._user_candidates(obj, settings))
        elif obj.object_type == "computer":
            devices, discoveries = self._device_candidates(obj, settings)
            scored.extend(("hiop_device", target, result) for target, result in devices)
            scored.extend(("discovered_device", target, result) for target, result in discoveries)
        scored.extend(self._mapping_candidates(obj, settings))
        scored = [item for item in scored if item[2]["level"] != "none"]
        scored.sort(key=lambda item: (-item[2]["score"], item[0], str(getattr(item[1], "id", ""))))
        models = []
        for candidate_type, target, result in scored[:settings["candidate_limit"]]:
            kwargs = {
                "candidate_user_id": None, "candidate_device_id": None,
                "candidate_discovery_id": None, "candidate_department_id": None,
                "candidate_role_id": None,
            }
            field = {
                "hiop_user": "candidate_user_id", "hiop_device": "candidate_device_id",
                "discovered_device": "candidate_discovery_id", "department": "candidate_department_id",
                "role": "candidate_role_id",
            }[candidate_type]
            kwargs[field] = target.target_role if candidate_type == "role" else target.id
            recommended = result["recommended_action"]
            if obj.object_type == "user" and (not obj.enabled or obj.sync_status == "missing"):
                recommended = "disable_review"
            elif obj.object_type == "computer" and (not obj.enabled or obj.sync_status == "missing"):
                recommended = "review"
            models.append(ActiveDirectoryMatchCandidate(
                directory_object_id=obj.id, candidate_type=candidate_type,
                match_score=result["score"], match_level=result["level"],
                match_status="pending", matching_fields=result["matching_fields"],
                conflicting_fields=result["conflicting_fields"], evidence=result["evidence"],
                recommended_action=recommended, source_version=obj.when_changed,
                target_version=getattr(target, "updated_at", None), **kwargs,
            ))
        return models

    def run(self, connection_id: str, actor: User, *, object_types: list[str] | None = None,
            recompute: bool = False, dry_run: bool = False, limit: int = 1000) -> dict[str, Any]:
        if not self.db.get(ActiveDirectoryConnection, connection_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Active Directory connection was not found.")
        settings = read_ad_matching_settings(self.db)
        filters = [ActiveDirectoryObject.connection_id == connection_id]
        if object_types:
            filters.append(ActiveDirectoryObject.object_type.in_(object_types))
        objects = self.db.scalars(select(ActiveDirectoryObject).where(*filters).order_by(
            ActiveDirectoryObject.updated_at.desc()
        ).limit(limit)).all()
        create_audit_log(self.db, actor.username, "AD_MATCHING_STARTED", "ActiveDirectoryConnection",
                         connection_id, f"Started reviewed matching for {len(objects)} staged objects.")
        self.db.commit()
        manager.broadcast_from_thread({"type": "ad_matching_started", "connection_id": connection_id, "total": len(objects)})
        counts = Counter()
        for index, obj in enumerate(objects, 1):
            existing_candidate = self.db.scalar(select(ActiveDirectoryMatchCandidate.id).where(
                ActiveDirectoryMatchCandidate.directory_object_id == obj.id
            ).limit(1))
            if existing_candidate and not recompute:
                counts["preserved_existing"] += 1
                continue
            if recompute and not dry_run:
                accepted = self.db.scalar(select(ActiveDirectoryMatchCandidate.id).where(
                    ActiveDirectoryMatchCandidate.directory_object_id == obj.id,
                    ActiveDirectoryMatchCandidate.match_status.in_(("accepted", "resolved")),
                ).limit(1))
                if accepted:
                    counts["preserved_reviewed"] += 1
                    continue
                self.db.execute(delete(ActiveDirectoryMatchCandidate).where(
                    ActiveDirectoryMatchCandidate.directory_object_id == obj.id
                ))
            models = self.generate_for_object(obj, settings)
            counts["objects"] += 1
            counts["candidates"] += len(models)
            if not models: counts["unmatched"] += 1
            elif models[0].conflicting_fields:
                counts["conflicts"] += 1
                manager.broadcast_from_thread({"type": "ad_conflict_detected", "directory_object_id": obj.id})
            else: counts[models[0].match_level] += 1
            if not dry_run:
                self.db.add_all(models)
            if index % max(1, settings["reconciliation_batch_size"]) == 0:
                self.db.commit()
                manager.broadcast_from_thread({"type": "ad_matching_progress", "connection_id": connection_id, "processed": index, "total": len(objects)})
        create_audit_log(self.db, actor.username, "AD_MATCHING_COMPLETED", "ActiveDirectoryConnection",
                         connection_id, f"Matching completed with {counts['candidates']} candidates and {counts['conflicts']} conflicts.")
        self.db.commit()
        manager.broadcast_from_thread({"type": "ad_matching_completed", "connection_id": connection_id, "summary": dict(counts), "dry_run": dry_run})
        self._notify(dict(counts))
        return dict(counts)

    def candidates_for_object(self, object_id: str):
        self._object(object_id)
        return self.db.scalars(select(ActiveDirectoryMatchCandidate).where(
            ActiveDirectoryMatchCandidate.directory_object_id == object_id
        ).order_by(ActiveDirectoryMatchCandidate.match_score.desc())).all()
