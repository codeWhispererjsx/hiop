"""Administrator-reviewed AD reconciliation and onboarding."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.active_directory import (
    ActiveDirectoryMatchCandidate,
    ActiveDirectoryObject,
    ActiveDirectoryReconciliationResult,
    ActiveDirectoryRecordLink,
)
from app.models.device import Device
from app.models.discovered_device import DiscoveredDevice, ReviewStatus
from app.models.hierarchy import Department
from app.models.user import User
from app.schemas.device import DeviceCreate
from app.services.audit_service import create_audit_log
from app.services.hierarchy_service import resolve_device_hierarchy
from app.websocket.connection_manager import manager


USER_ACTIONS = {
    "link_existing_user", "create_new_user", "enrich_existing_user",
    "ignore", "conflict", "review_disable",
}
COMPUTER_ACTIONS = {
    "link_existing_device", "create_new_device", "enrich_existing_device",
    "link_discovery", "ignore", "conflict", "review_retire",
}
GROUP_ACTIONS = {"suggest_role_mapping", "ignore", "conflict"}


class ActiveDirectoryReconciliationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _object(self, object_id: str) -> ActiveDirectoryObject:
        obj = self.db.get(ActiveDirectoryObject, object_id)
        if not obj:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Directory object was not found.")
        return obj

    def _candidate(self, obj: ActiveDirectoryObject, candidate_id: str | None):
        if not candidate_id:
            return None
        candidate = self.db.get(ActiveDirectoryMatchCandidate, candidate_id)
        if not candidate or candidate.directory_object_id != obj.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Match candidate was not found for this object.")
        return candidate

    @staticmethod
    def _version(value):
        return value.astimezone(timezone.utc).isoformat() if value else None

    def _validate_fresh(self, obj, candidate, target) -> None:
        if candidate and self._version(candidate.source_version) != self._version(obj.when_changed):
            raise HTTPException(status.HTTP_409_CONFLICT, "Directory object changed; recompute matches before review.")
        if candidate and candidate.target_version and target:
            if self._version(candidate.target_version) != self._version(getattr(target, "updated_at", None)):
                raise HTTPException(status.HTTP_409_CONFLICT, "Target record changed; recompute matches before review.")

    def plan(self, object_id: str, candidate_id: str | None = None) -> dict[str, Any]:
        obj = self._object(object_id)
        candidate = self._candidate(obj, candidate_id)
        target = None
        if candidate:
            if candidate.candidate_user_id: target = self.db.get(User, candidate.candidate_user_id)
            elif candidate.candidate_device_id: target = self.db.get(Device, candidate.candidate_device_id)
            elif candidate.candidate_discovery_id: target = self.db.get(DiscoveredDevice, candidate.candidate_discovery_id)
        source = {
            "username": obj.sam_account_name, "upn": obj.user_principal_name,
            "email": obj.email, "display_name": obj.display_name,
            "department": obj.department, "job_title": obj.job_title,
            "hostname": obj.sam_account_name.removesuffix("$") if obj.sam_account_name else None,
            "dns_hostname": obj.dns_hostname, "operating_system": obj.operating_system,
            "operating_system_version": obj.operating_system_version,
            "enabled": obj.enabled, "sync_status": obj.sync_status,
        }
        existing = {}
        if isinstance(target, User):
            existing = {"username": target.username, "email": target.email, "role": target.role, "is_active": target.is_active}
        elif isinstance(target, Device):
            existing = {key: getattr(target, key) for key in (
                "asset_tag", "hostname", "serial_number", "mac_address", "ip_address",
                "department", "location", "inventory_status",
            )}
        elif isinstance(target, DiscoveredDevice):
            existing = {"hostname": target.hostname, "ip_address": target.ip_address,
                        "mac_address": target.mac_address, "approved_device_id": target.approved_device_id}
        proposed = []
        preserved = []
        for key, value in source.items():
            if key in existing and value and not existing[key]:
                proposed.append({"field": key, "value": value})
            elif key in existing and existing[key] is not None:
                preserved.append({"field": key, "value": existing[key]})
        warnings = []
        if obj.object_type == "user" and (not obj.enabled or obj.sync_status == "missing"):
            warnings.append("Directory account is disabled or missing; no HIOP status change will occur automatically.")
        if isinstance(target, User) and target.role == "admin":
            warnings.append("Target is an administrator; role and active status will be preserved.")
        if obj.object_type == "computer" and (not obj.enabled or obj.sync_status == "missing"):
            warnings.append("Directory computer is disabled or missing; no inventory retirement will occur automatically.")
        return {
            "directory_object_id": obj.id, "object_type": obj.object_type,
            "candidate_id": candidate.id if candidate else None, "source": source,
            "existing": existing, "proposed_fill_missing": proposed,
            "preserved": preserved, "conflicts": candidate.conflicting_fields if candidate else [],
            "evidence": candidate.evidence if candidate else {}, "warnings": warnings,
            "requires_confirmation": True, "password_synchronized": False,
        }

    def review_candidate(self, object_id: str, candidate_id: str, actor: User, *, accept: bool):
        obj = self._object(object_id)
        candidate = self._candidate(obj, candidate_id)
        if candidate.match_status != "pending":
            raise HTTPException(status.HTTP_409_CONFLICT, "Candidate was already reviewed.")
        if accept and candidate.conflicting_fields:
            raise HTTPException(status.HTTP_409_CONFLICT, "Conflicting candidate requires explicit resolution.")
        candidate.match_status = "accepted" if accept else "rejected"
        candidate.reviewed_by, candidate.reviewed_at = actor.id, datetime.now(timezone.utc)
        create_audit_log(self.db, actor.username, "AD_MATCH_ACCEPTED" if accept else "AD_MATCH_REJECTED",
                         "ActiveDirectoryMatchCandidate", candidate.id, "Administrator reviewed an AD match candidate.")
        self.db.commit(); self.db.refresh(candidate)
        return candidate

    def _link(self, obj, actor, *, user=None, device=None, discovery=None):
        existing = self.db.scalar(select(ActiveDirectoryRecordLink).where(
            ActiveDirectoryRecordLink.directory_object_id == obj.id
        ))
        if existing:
            same = (user and existing.user_id == user.id) or (device and existing.device_id == device.id)
            if same: return existing
            raise HTTPException(status.HTTP_409_CONFLICT, "Directory object is already linked to another HIOP record.")
        if user:
            contradiction = self.db.scalar(select(ActiveDirectoryRecordLink.id).where(
                ActiveDirectoryRecordLink.connection_id == obj.connection_id,
                ActiveDirectoryRecordLink.user_id == user.id,
            ).limit(1))
        else:
            contradiction = self.db.scalar(select(ActiveDirectoryRecordLink.id).where(
                ActiveDirectoryRecordLink.connection_id == obj.connection_id,
                ActiveDirectoryRecordLink.device_id == device.id,
            ).limit(1))
        if contradiction:
            raise HTTPException(status.HTTP_409_CONFLICT, "Target HIOP record is linked to another directory object.")
        link = ActiveDirectoryRecordLink(
            connection_id=obj.connection_id, directory_object_id=obj.id,
            user_id=user.id if user else None, device_id=device.id if device else None,
            discovery_id=discovery.id if discovery else None, linked_by=actor.id,
            source_version=obj.when_changed,
        )
        self.db.add(link)
        obj.review_status = "matched"
        obj.matched_user_id = user.id if user else None
        obj.matched_device_id = device.id if device else None
        return link

    def _result(self, obj, actor, action, result_status, *, user=None, device=None,
                before=None, after=None, error=None):
        result = ActiveDirectoryReconciliationResult(
            directory_object_id=obj.id, action=action, status=result_status,
            target_user_id=user.id if user else None, target_device_id=device.id if device else None,
            before_values=before or {}, after_values=after or {}, safe_error=error,
            reviewed_by=actor.id,
        )
        self.db.add(result)
        return result

    def resolve(self, object_id: str, actor: User, *, action: str, candidate_id: str | None,
                approved_fields: list[str], device_payload: dict[str, Any] | None,
                role: str | None, active: bool | None, confirm: bool,
                confirm_privileged_role: bool = False):
        if not confirm:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Explicit reconciliation confirmation is required.")
        obj = self._object(object_id)
        allowed = USER_ACTIONS if obj.object_type == "user" else COMPUTER_ACTIONS if obj.object_type == "computer" else GROUP_ACTIONS
        if action not in allowed:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Disposition is invalid for this directory object type.")
        candidate = self._candidate(obj, candidate_id)
        user = self.db.get(User, candidate.candidate_user_id) if candidate and candidate.candidate_user_id else None
        device = self.db.get(Device, candidate.candidate_device_id) if candidate and candidate.candidate_device_id else None
        discovery = self.db.get(DiscoveredDevice, candidate.candidate_discovery_id) if candidate and candidate.candidate_discovery_id else None
        self._validate_fresh(obj, candidate, user or device or discovery)
        if candidate and candidate.conflicting_fields and action not in {"conflict", "ignore"}:
            raise HTTPException(status.HTTP_409_CONFLICT, "Candidate conflicts must be deferred or explicitly resolved.")
        try:
            if action == "ignore":
                obj.review_status = "ignored"
                if candidate: candidate.match_status = "ignored"
                result = self._result(obj, actor, action, "completed")
            elif action in {"conflict", "review_disable", "review_retire"}:
                obj.review_status = "conflict"
                result = self._result(obj, actor, action, "review_required")
            elif action == "create_new_user":
                if not obj.sam_account_name or not obj.email or not role:
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Username, email, and role are required.")
                if role == "admin" and not confirm_privileged_role:
                    raise HTTPException(status.HTTP_409_CONFLICT, "Admin onboarding requires separate privileged-role confirmation.")
                # There is no invitation workflow. Never invent, receive, or synchronize an AD password.
                result = self._result(
                    obj, actor, action, "pending_manual_setup",
                    after={"username": obj.sam_account_name, "email": obj.email, "role": role,
                           "is_active": bool(active), "password_required": True},
                    error="Local password or invitation setup is required before HIOP account creation.",
                )
            elif action in {"link_existing_user", "enrich_existing_user"}:
                if not user: raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A HIOP user candidate is required.")
                before = {"username": user.username, "email": user.email, "role": user.role, "is_active": user.is_active}
                if action == "enrich_existing_user":
                    updates = {}
                    if "email" in approved_fields and not user.email and obj.email: updates["email"] = obj.email
                    if "username" in approved_fields and not user.username and obj.sam_account_name: updates["username"] = obj.sam_account_name
                    for key, value in updates.items(): setattr(user, key, value)
                self._link(obj, actor, user=user)
                after = {"username": user.username, "email": user.email, "role": user.role, "is_active": user.is_active}
                result = self._result(obj, actor, action, "completed", user=user, before=before, after=after)
            elif action == "create_new_device":
                if not device_payload:
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Complete inventory fields are required.")
                try:
                    payload = DeviceCreate.model_validate(device_payload)
                except ValidationError as exc:
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_CONTENT,
                        "Complete valid inventory fields are required for device onboarding.",
                    ) from exc
                values = resolve_device_hierarchy(self.db, payload.model_dump(exclude={"status"}))
                if self.db.scalar(select(Device.id).where(or_(
                    func.lower(Device.asset_tag) == payload.asset_tag.casefold(),
                    func.lower(Device.mac_address) == payload.mac_address.casefold(),
                    func.lower(Device.serial_number) == payload.serial_number.casefold(),
                )).limit(1)):
                    raise HTTPException(status.HTTP_409_CONFLICT, "Device identifiers already exist.")
                device = Device(**values, status=values["inventory_status"], network_status="Unknown")
                self.db.add(device); self.db.flush()
                self._link(obj, actor, device=device, discovery=discovery)
                result = self._result(obj, actor, action, "completed", device=device,
                                      after={"device_id": str(device.id), "hostname": device.hostname})
            elif action in {"link_existing_device", "enrich_existing_device"}:
                if not device: raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A HIOP device candidate is required.")
                before = {"hostname": device.hostname, "department": device.department,
                          "asset_tag": device.asset_tag, "mac_address": device.mac_address,
                          "serial_number": device.serial_number}
                if action == "enrich_existing_device":
                    if "hostname" in approved_fields and not device.hostname:
                        device.hostname = obj.dns_hostname or (obj.sam_account_name or "").removesuffix("$")
                    if "department" in approved_fields and not device.department and obj.department:
                        device.department = obj.department
                self._link(obj, actor, device=device, discovery=discovery)
                after = {"hostname": device.hostname, "department": device.department,
                         "asset_tag": device.asset_tag, "mac_address": device.mac_address,
                         "serial_number": device.serial_number}
                result = self._result(obj, actor, action, "completed", device=device, before=before, after=after)
            elif action == "link_discovery":
                if not discovery:
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A Discovery candidate is required.")
                if discovery.approved_device_id:
                    device = self.db.get(Device, discovery.approved_device_id)
                if not device:
                    raise HTTPException(status.HTTP_409_CONFLICT, "Discovery record must already be linked to inventory.")
                self._link(obj, actor, device=device, discovery=discovery)
                result = self._result(obj, actor, action, "completed", device=device)
            else:  # reviewed group role suggestion
                if not candidate or candidate.candidate_type != "role":
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A mapped role candidate is required.")
                if candidate.candidate_role_id == "admin" and not confirm_privileged_role:
                    raise HTTPException(status.HTTP_409_CONFLICT, "Admin role mapping requires extra confirmation.")
                candidate.match_status = "resolved"
                obj.review_status = "approved"
                result = self._result(obj, actor, action, "completed",
                                      after={"suggested_role": candidate.candidate_role_id})
            if candidate and candidate.match_status in {"pending", "accepted"}:
                candidate.match_status = "resolved"
                candidate.reviewed_by, candidate.reviewed_at = actor.id, datetime.now(timezone.utc)
            create_audit_log(self.db, actor.username, "AD_OBJECT_RECONCILED", "ActiveDirectoryObject",
                             obj.id, f"Reviewed AD reconciliation action '{action}' completed as {result.status}.")
            self.db.commit(); self.db.refresh(result)
            manager.broadcast_from_thread({"type": "ad_object_resolved", "directory_object_id": obj.id,
                                           "action": action, "status": result.status})
            if action == "create_new_device":
                manager.broadcast_from_thread({"type": "ad_device_onboarded", "directory_object_id": obj.id,
                                               "device_id": str(device.id)})
            return result
        except HTTPException:
            self.db.rollback(); raise
        except IntegrityError as exc:
            self.db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, "Reconciliation conflicts with an existing identity or link.") from exc

    def bulk(self, object_ids: list[str], actor: User, *, action: str, confirm: bool):
        if not confirm:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Bulk confirmation is required.")
        results = []
        for object_id in object_ids:
            try:
                obj = self._object(object_id)
                candidate = self.db.scalar(select(ActiveDirectoryMatchCandidate).where(
                    ActiveDirectoryMatchCandidate.directory_object_id == obj.id,
                    ActiveDirectoryMatchCandidate.match_level == "exact",
                    ActiveDirectoryMatchCandidate.match_status == "pending",
                ).order_by(ActiveDirectoryMatchCandidate.match_score.desc()).limit(1))
                if action.startswith("link_") and (not candidate or candidate.conflicting_fields):
                    raise HTTPException(status.HTTP_409_CONFLICT, "No conflict-free exact candidate.")
                result = self.resolve(
                    obj.id, actor, action=action, candidate_id=candidate.id if candidate else None,
                    approved_fields=[], device_payload=None, role=None, active=None, confirm=True,
                )
                results.append({"object_id": obj.id, "status": result.status, "result_id": result.id})
            except HTTPException as error:
                results.append({"object_id": object_id, "status": "failed", "error": str(error.detail)})
        return {"items": results, "completed": sum(item["status"] != "failed" for item in results),
                "failed": sum(item["status"] == "failed" for item in results)}
