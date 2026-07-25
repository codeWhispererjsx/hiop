import ipaddress
from datetime import datetime, timezone
from time import monotonic
from copy import copy
from fnmatch import fnmatchcase

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.hierarchy import NetworkZone, Room
from app.models.snmp import SNMPCredential, SNMPDeviceProfile, SNMPTarget
from app.models.device import Device
from app.models.discovered_device import DiscoveredDevice
from app.schemas.snmp import SNMPTargetCreate, SNMPTargetUpdate
from app.services.audit_service import create_audit_log
from app.services.settings_service import read_discovery
from app.services.snmp_runtime import target_active
from app.services.snmp_runtime import snmp_operation_lock
from app.services.snmp_client_service import SecureSNMPClient, SNMPClientError
from app.services.snmp_notification_service import notify_snmp
from app.websocket.connection_manager import manager


class SNMPTargetService:
    def __init__(self, db: Session, client_factory=SecureSNMPClient):
        self.db = db
        self.client_factory = client_factory

    def _references(self, values: dict):
        credential = self.db.get(SNMPCredential, values.get("credential_id"))
        if not credential or not credential.enabled:
            raise HTTPException(400, "Enabled SNMP credential was not found.")
        requested_version = values.get("version")
        requested_version = getattr(requested_version, "value", requested_version)
        if requested_version and requested_version != credential.version:
            raise HTTPException(400, "Target and credential SNMP versions must match.")
        for key, model in (("device_id", Device), ("discovered_device_id", DiscoveredDevice), ("network_zone_id", NetworkZone), ("location_id", Room)):
            if values.get(key) and not self.db.get(model, values[key]):
                raise HTTPException(400, f"Referenced {key.removesuffix('_id').replace('_', ' ')} was not found.")

    def _authorized(self, address: str):
        ip = ipaddress.ip_address(address)
        ranges = read_discovery(self.db)["authorized_cidr_ranges"]
        if isinstance(ranges, str):
            ranges = [part.strip() for part in ranges.split(",") if part.strip()]
        if not ranges or not any(ip in ipaddress.ip_network(cidr, strict=False) for cidr in ranges):
            raise HTTPException(400, "SNMP target must be inside an authorized discovery network.")
        if not ip.is_private:
            raise HTTPException(400, "Public SNMP targets are not permitted.")

    def create_target(self, payload: SNMPTargetCreate, actor):
        values = payload.model_dump(mode="json")
        self._references(values)
        self._authorized(values["ip_address"])
        row = SNMPTarget(**values, created_by=actor.id, updated_by=actor.id)
        self.db.add(row)
        create_audit_log(self.db, actor.username, "SNMP_TARGET_CREATED", "SNMPTarget", str(row.id), f"Created SNMP target '{row.name}'.")
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise HTTPException(409, "An SNMP target already exists for this endpoint and context.") from error
        self.db.refresh(row)
        return row

    def update_target(self, row: SNMPTarget, payload: SNMPTargetUpdate, actor):
        values = payload.model_dump(exclude_unset=True)
        merged = {"credential_id": values.get("credential_id", row.credential_id), "version": row.version}
        merged.update(values)
        self._references(merged)
        self._authorized(values.get("ip_address", row.ip_address))
        for key, value in values.items():
            setattr(row, key, value)
        row.updated_by = actor.id
        create_audit_log(self.db, actor.username, "SNMP_TARGET_UPDATED", "SNMPTarget", str(row.id), f"Updated SNMP target '{row.name}'.")
        self.db.commit()
        self.db.refresh(row)
        return row

    def disable_target(self, row: SNMPTarget, actor):
        if target_active(row.id):
            raise HTTPException(409, "Target has an active SNMP operation.")
        row.enabled = False
        row.polling_enabled = False
        row.updated_by = actor.id
        create_audit_log(self.db, actor.username, "SNMP_TARGET_DISABLED", "SNMPTarget", str(row.id), f"Disabled SNMP target '{row.name}'.")
        self.db.commit()
        self.db.refresh(row)
        return row

    def test_target(self, row: SNMPTarget, actor, *, include_optional_identity=True, temporary_timeout=None):
        credential = self.db.get(SNMPCredential, row.credential_id)
        discovery = read_discovery(self.db)
        networks = discovery["authorized_cidr_ranges"]
        ignored = discovery.get("ignore_ranges", "")
        networks = [item.strip() for item in networks.split(",") if item.strip()] if isinstance(networks, str) else networks
        ignored = [item.strip() for item in ignored.split(",") if item.strip()] if isinstance(ignored, str) else ignored
        operation_target = copy(row)
        if temporary_timeout is not None:
            operation_target.timeout_seconds = temporary_timeout
        started = monotonic()
        tested_at = datetime.now(timezone.utc)
        manager.broadcast_from_thread({"type": "snmp_target_test_started", "target_id": str(row.id)})
        create_audit_log(self.db, actor.username, "SNMP_TARGET_TEST_REQUESTED", "SNMPTarget", str(row.id), "Requested authorized SNMP target test.")
        client = None
        try:
            with snmp_operation_lock(row.id, row.credential_id):
                client = self.client_factory(operation_target, credential, authorized_networks=networks, ignored_networks=ignored)
                result = client.test_target(include_optional_identity)
            row.last_tested_at = tested_at
            row.last_test_status = "success"
            row.last_test_message = "SNMP target responded successfully."
            row.last_response_time_ms = result["response_time_ms"]
            row.consecutive_failures = 0
            identity = result.get("identity", {})
            sys_object_id = getattr(identity.get("system.object_id"), "value_text", None)
            sys_description = getattr(identity.get("system.description"), "value_text", None)
            row.detected_sys_object_id = sys_object_id
            profiles = self.db.scalars(select(SNMPDeviceProfile).where(
                SNMPDeviceProfile.enabled.is_(True)
            ).order_by(SNMPDeviceProfile.priority)).all()
            suggestion = next((
                profile for profile in profiles
                if (not profile.sys_object_id_pattern or fnmatchcase(sys_object_id or "", profile.sys_object_id_pattern))
                and (not profile.sys_descr_pattern or fnmatchcase((sys_description or "").lower(), profile.sys_descr_pattern.lower()))
            ), None)
            row.detected_profile_id = suggestion.id if suggestion else None
            result["detected_profile_suggestion_id"] = row.detected_profile_id
            result["duration_ms"] = round((monotonic() - started) * 1000)
            create_audit_log(self.db, actor.username, "SNMP_TARGET_TEST_SUCCEEDED", "SNMPTarget", str(row.id), "SNMP target test succeeded.")
            manager.broadcast_from_thread({"type": "snmp_target_test_completed", "target_id": str(row.id), "status": "success", "duration_ms": result["duration_ms"]})
            self.db.commit()
            return result
        except SNMPClientError as error:
            row.last_tested_at = tested_at
            row.last_test_status = "failed"
            row.last_test_message = error.safe_message
            row.consecutive_failures += 1
            create_audit_log(self.db, actor.username, "SNMP_TARGET_TEST_FAILED", "SNMPTarget", str(row.id), f"SNMP target test failed: {error.category}.")
            manager.broadcast_from_thread({"type": "snmp_target_test_completed", "target_id": str(row.id), "status": "failed", "error_category": error.category})
            notify_snmp(self.db, "HIOP SNMP target test failed", f"Target {row.id} failed with category {error.category}.")
            self.db.commit()
            raise HTTPException(502, {"category": error.category, "message": error.safe_message}) from error
        finally:
            if client:
                client.close()
