import ipaddress

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.hierarchy import NetworkZone, Room
from app.models.snmp import SNMPCredential, SNMPTarget
from app.models.device import Device
from app.models.discovered_device import DiscoveredDevice
from app.schemas.snmp import SNMPTargetCreate, SNMPTargetUpdate
from app.services.audit_service import create_audit_log
from app.services.settings_service import read_discovery


class SNMPTargetService:
    def __init__(self, db: Session):
        self.db = db

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
        row.enabled = False
        row.polling_enabled = False
        row.updated_by = actor.id
        create_audit_log(self.db, actor.username, "SNMP_TARGET_DISABLED", "SNMPTarget", str(row.id), f"Disabled SNMP target '{row.name}'.")
        self.db.commit()
        self.db.refresh(row)
        return row

    def test_target(self, *args, **kwargs):
        raise NotImplementedError("Live SNMP target testing is reserved for Epic 4B.")
