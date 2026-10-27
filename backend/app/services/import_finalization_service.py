from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
import logging
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.asset_intelligence import AssetLifecycleEvent, ManagedAsset
from app.models.discovered_device import DiscoveredDevice, ReviewStatus
from app.models.hierarchy import Building, Department, Floor, NetworkZone, Property, Room
from app.models.inventory_import import (
    ImportExecutionResult,
    ImportExecutionStatus,
    ImportLocationSuggestion,
    ImportSession,
    ImportSessionStatus,
    ImportedDevice,
    ImportValidationStatus,
    LocationSuggestionStatus,
)
from app.models.user import User
from app.schemas.device import DeviceCreate
from app.services.audit_service import create_audit_log
from app.services.settings_service import read_import_settings
from app.services.settings_service import read_bundle
from app.services.email_service import send_email
from app.websocket.connection_manager import manager


class FinalizationNotFoundError(ValueError):
    pass


class FinalizationConflictError(ValueError):
    pass


class FinalizationValidationError(ValueError):
    pass


FINAL_DISPOSITIONS = {
    "create_new",
    "create_asset",
    "link_existing",
    "enrich_existing",
    "merge_reviewed",
    "link_discovery",
    "skip",
}
MUTATING_DISPOSITIONS = {"create_new", "create_asset", "enrich_existing", "merge_reviewed"}
ENRICHABLE_FIELDS = {
    "hostname",
    "device_type",
    "brand",
    "model",
    "serial_number",
    "department",
    "location",
    "ip_address",
    "mac_address",
    "inventory_status",
    "department_id",
    "room_id",
    "network_zone_id",
}
IDENTIFIER_FIELDS = {"asset_tag", "hostname", "serial_number", "mac_address"}
logger = logging.getLogger(__name__)


class ImportFinalizationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _session(self, session_id: UUID, *, lock: bool = False) -> ImportSession:
        statement = select(ImportSession).where(ImportSession.id == session_id)
        if lock:
            statement = statement.with_for_update()
        session = self.db.scalar(statement)
        if not session:
            raise FinalizationNotFoundError("Import session not found")
        return session

    def _hierarchy_query(self, model):
        query = select(model).where(model.is_active.is_(True))
        organization_id = self.db.info.get("organization_id")
        if organization_id is None:
            return query
        properties = select(Property.id).where(Property.organization_id == organization_id)
        property_id = self.db.info.get("property_id")
        if property_id is not None:
            properties = properties.where(Property.id == property_id)
        if model in (Department, Building, NetworkZone):
            return query.where(model.property_id.in_(properties))
        buildings = select(Building.id).where(Building.property_id.in_(properties))
        if model is Floor:
            return query.where(Floor.organization_id == organization_id, Floor.building_id.in_(buildings))
        floors = select(Floor.id).where(
            Floor.organization_id == organization_id,
            Floor.building_id.in_(buildings),
        )
        return query.where(Room.organization_id == organization_id, Room.floor_id.in_(floors))

    def _rows(self, session_id: UUID) -> list[ImportedDevice]:
        return list(
            self.db.scalars(
                select(ImportedDevice)
                .where(ImportedDevice.import_session_id == session_id)
                .order_by(ImportedDevice.source_row_number)
            ).all()
        )

    @staticmethod
    def _event(event: str, session_id: UUID, **values: Any) -> None:
        manager.broadcast_from_thread(
            {"event": event, "session_id": str(session_id), **values}
        )

    def _notify(self, subject: str, body: str, *, failure: bool = False) -> None:
        bundle = read_bundle(self.db)
        notifications = bundle["notifications"]
        if not notifications.get("email_notifications"):
            return
        if failure and not notifications.get("critical_alerts"):
            return
        recipient = notifications.get("recipient_email")
        if not recipient:
            return
        try:
            send_email(subject, body, recipient)
        except Exception:
            logger.exception("Import completion notification failed")

    @staticmethod
    def _safe_snapshot(device: Device) -> dict[str, Any]:
        fields = (
            "asset_tag",
            "hostname",
            "device_type",
            "brand",
            "model",
            "serial_number",
            "department",
            "location",
            "ip_address",
            "mac_address",
            "inventory_status",
            "department_id",
            "room_id",
            "network_zone_id",
            "updated_at",
        )
        return {
            field: (
                value.isoformat()
                if hasattr((value := getattr(device, field, None)), "isoformat")
                else str(value)
                if isinstance(value, UUID)
                else value
            )
            for field in fields
        }

    def set_disposition(
        self,
        session_id: UUID,
        row_id: UUID,
        disposition: str,
        approved_fields: list[str],
        approved_overwrites: list[str],
        actor: User,
    ) -> ImportedDevice:
        session = self._session(session_id, lock=True)
        if session.plan_locked_at or session.status in {
            ImportSessionStatus.IMPORTING,
            ImportSessionStatus.COMPLETED,
            ImportSessionStatus.ROLLED_BACK,
        }:
            raise FinalizationConflictError("The execution plan is locked")
        row = self.db.scalar(
            select(ImportedDevice).where(
                ImportedDevice.id == row_id,
                ImportedDevice.import_session_id == session_id,
            )
        )
        if not row:
            raise FinalizationNotFoundError("Imported row not found")
        if disposition not in FINAL_DISPOSITIONS:
            raise FinalizationValidationError("Unsupported final disposition")
        if disposition in {"link_existing", "enrich_existing", "merge_reviewed"} and not row.linked_device_id:
            raise FinalizationValidationError("An accepted inventory target is required")
        if disposition == "link_discovery" and not row.linked_discovery_id:
            raise FinalizationValidationError("An accepted Discovery target is required")
        approved = set(approved_fields)
        overwrites = set(approved_overwrites)
        if not approved.issubset(ENRICHABLE_FIELDS) or not overwrites.issubset(approved):
            raise FinalizationValidationError("Approved fields contain unsupported values")
        if overwrites and not read_import_settings(self.db)["allow_reviewed_field_overwrite"]:
            raise FinalizationValidationError("Reviewed overwrites are disabled")
        row.final_disposition = disposition
        row.approved_changes = {
            "fields": sorted(approved),
            "overwrites": sorted(overwrites),
            "reviewer": actor.username,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }
        session.plan_version += 1
        create_audit_log(
            self.db,
            actor.username,
            "IMPORT_DISPOSITION_REVIEWED",
            "ImportedDevice",
            str(row.id),
            f"Reviewed row {row.source_row_number} for {disposition}",
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def _location(self, row: ImportedDevice) -> ImportLocationSuggestion | None:
        return self.db.scalar(
            select(ImportLocationSuggestion).where(
                ImportLocationSuggestion.imported_device_id == row.id
            )
        )

    def _plan_row(self, row: ImportedDevice) -> dict[str, Any]:
        disposition = row.final_disposition
        if not disposition:
            disposition = {
                "create_new": "create_new",
                "linked": "link_existing",
                "skip": "skip",
            }.get(row.resolution_action or "", "unresolved")
        location = self._location(row)
        approved_location = (
            location
            if location
            and location.status
            in {
                LocationSuggestionStatus.ACCEPTED,
                LocationSuggestionStatus.OVERRIDDEN,
            }
            else None
        )
        hierarchy = {
            "department_id": str(approved_location.department_id) if approved_location and approved_location.department_id else None,
            "building_id": str(approved_location.building_id) if approved_location and approved_location.building_id else None,
            "floor_id": str(approved_location.floor_id) if approved_location and approved_location.floor_id else None,
            "room_id": str(approved_location.room_id) if approved_location and approved_location.room_id else None,
            "network_zone_id": str(approved_location.network_zone_id) if approved_location and approved_location.network_zone_id else None,
        }
        department_name = row.department_name
        room_name = row.room_name
        if approved_location and approved_location.department_id:
            department = self.db.scalar(self._hierarchy_query(Department).where(Department.id == approved_location.department_id))
            if department:
                department_name = department.name
        if approved_location and approved_location.room_id:
            room = self.db.scalar(self._hierarchy_query(Room).where(Room.id == approved_location.room_id))
            if room:
                room_name = room.name
        values = {
            "asset_tag": row.asset_tag,
            "hostname": row.hostname,
            "device_type": row.device_type,
            "brand": row.brand or row.vendor,
            "model": row.model,
            "serial_number": row.serial_number,
            "department": department_name,
            "location": room_name,
            "ip_address": row.ip_address,
            "mac_address": row.mac_address,
            "inventory_status": row.inventory_status or "Active",
            "department_id": hierarchy["department_id"],
            "room_id": hierarchy["room_id"],
            "network_zone_id": hierarchy["network_zone_id"],
            "business_owner": (row.normalized_data or {}).get("business_owner"),
            "deployment_date": (row.normalized_data or {}).get("deployment_date"),
            "description": row.notes,
        }
        target_device_id = row.linked_device_id
        if not target_device_id and row.linked_discovery_id:
            discovery = self.db.get(DiscoveredDevice, row.linked_discovery_id)
            target_device_id = discovery.approved_device_id if discovery else None
        target = self.db.get(Device, target_device_id) if target_device_id else None
        return {
            "imported_device_id": str(row.id),
            "source_row_number": row.source_row_number,
            "disposition": disposition,
            "target_device_id": str(target_device_id) if target_device_id else None,
            "target_discovery_id": str(row.linked_discovery_id) if row.linked_discovery_id else None,
            "target_updated_at": target.updated_at.isoformat() if target and target.updated_at else None,
            "values": values,
            "hierarchy": hierarchy,
            "approved_fields": (row.approved_changes or {}).get("fields", []),
            "approved_overwrites": (row.approved_changes or {}).get("overwrites", []),
            "reviewer": (row.approved_changes or {}).get("reviewer") or row.resolved_by,
            "reviewed_at": (row.approved_changes or {}).get("reviewed_at") or (
                row.resolved_at.isoformat() if row.resolved_at else None
            ),
        }

    def _validate_hierarchy(self, plan: dict[str, Any], blockers: list[dict]) -> None:
        ids = plan["hierarchy"]
        models = {
            "department_id": Department,
            "building_id": Building,
            "floor_id": Floor,
            "room_id": Room,
            "network_zone_id": NetworkZone,
        }
        loaded: dict[str, Any] = {}
        for field, model in models.items():
            value = ids.get(field)
            if value:
                loaded[field] = self.db.scalar(
                    self._hierarchy_query(model).where(model.id == UUID(value))
                )
                if not loaded[field]:
                    blockers.append({"code": "hierarchy_unavailable", "row": plan["source_row_number"], "message": f"Selected {field.removesuffix('_id')} is unavailable"})
        if loaded.get("room_id") and loaded.get("floor_id") and loaded["room_id"].floor_id != loaded["floor_id"].id:
            blockers.append({"code": "hierarchy_conflict", "row": plan["source_row_number"], "message": "Room does not belong to the selected floor"})
        if loaded.get("floor_id") and loaded.get("building_id") and loaded["floor_id"].building_id != loaded["building_id"].id:
            blockers.append({"code": "hierarchy_conflict", "row": plan["source_row_number"], "message": "Floor does not belong to the selected building"})

    def readiness(self, session_id: UUID) -> dict[str, Any]:
        session = self._session(session_id)
        rows = self._rows(session_id)
        blockers: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        if session.import_type != "device_inventory":
            blockers.append({"code": "unsupported_import_type", "message": "Only device inventory sessions can be finalized"})
        if session.matching_state != "completed":
            blockers.append({"code": "matching_incomplete", "message": "Matching must complete before finalization"})
        if session.status in {ImportSessionStatus.IMPORTING, ImportSessionStatus.ROLLED_BACK} or session.finalization_completed_at:
            blockers.append({"code": "terminal_state", "message": f"Session is already {session.status.value}"})
        plans = [self._plan_row(row) for row in rows]
        intended = [plan for plan in plans if plan["disposition"] not in {"invalid", "skip"}]
        for row, plan in zip(rows, plans):
            disposition = plan["disposition"]
            if row.validation_status == ImportValidationStatus.INVALID:
                plan["disposition"] = "invalid"
                continue
            if disposition not in FINAL_DISPOSITIONS:
                blockers.append({"code": "unresolved_row", "row": row.source_row_number, "message": "Row has no approved final disposition"})
                continue
            if disposition in {"link_existing", "enrich_existing", "merge_reviewed"} and not plan["target_device_id"]:
                blockers.append({"code": "missing_target", "row": row.source_row_number, "message": "Inventory target is missing"})
            if disposition == "link_discovery" and not plan["target_discovery_id"]:
                blockers.append({"code": "missing_discovery", "row": row.source_row_number, "message": "Discovery target is missing"})
            if disposition == "link_discovery" and not plan["target_device_id"]:
                blockers.append({"code": "missing_discovery_inventory_target", "row": row.source_row_number, "message": "Discovery must already reference the reviewed official device"})
            if disposition == "merge_reviewed" and not plan["approved_fields"]:
                blockers.append({"code": "merge_not_reviewed", "row": row.source_row_number, "message": "Merge has no explicitly approved fields"})
            if disposition == "create_new":
                try:
                    DeviceCreate(**plan["values"])
                except ValidationError as exc:
                    details = "; ".join(
                        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                        for error in exc.errors()
                    )
                    blockers.append({
                        "code": "invalid_device",
                        "row": row.source_row_number,
                        "message": f"Complete the missing or invalid Device fields in the source data: {details}"[:500],
                    })
            if disposition == "create_asset":
                asset_name = plan["values"].get("hostname")
                if not asset_name:
                    blockers.append({"code": "missing_asset_name", "row": row.source_row_number, "message": "A system name is required to create a managed asset"})
                elif len(asset_name) > 180:
                    blockers.append({"code": "asset_name_too_long", "row": row.source_row_number, "message": "Managed asset names cannot exceed 180 characters"})
                vendor = plan["values"].get("brand") or plan["values"].get("vendor")
                if vendor and len(vendor) > 120:
                    blockers.append({"code": "asset_vendor_too_long", "row": row.source_row_number, "message": "Managed asset vendor names cannot exceed 120 characters"})
                deployment_date = plan["values"].get("deployment_date")
                if deployment_date:
                    try:
                        datetime.fromisoformat(deployment_date).date()
                    except (TypeError, ValueError):
                        blockers.append({"code": "invalid_deployment_date", "row": row.source_row_number, "message": "Deployment date must be a valid ISO date"})
            self._validate_hierarchy(plan, blockers)
        asset_counts = Counter(
            (plan["values"].get("asset_tag") or "").casefold()
            for plan in intended
            if plan["disposition"] in {"create_new", "create_asset"}
        )
        mac_counts = Counter(
            (plan["values"].get("mac_address") or "").casefold()
            for plan in intended if plan["disposition"] in {"create_new", "create_asset"}
        )
        serial_counts = Counter(
            (plan["values"].get("serial_number") or "").casefold()
            for plan in intended if plan["disposition"] in {"create_new", "create_asset"}
        )
        hostname_counts = Counter(
            (plan["values"].get("hostname") or "").casefold()
            for plan in intended if plan["disposition"] in {"create_new", "create_asset"}
        )
        for label, counts in (
            ("asset_tag", asset_counts),
            ("mac_address", mac_counts),
            ("serial_number", serial_counts),
            ("hostname", hostname_counts),
        ):
            duplicates = [value for value, count in counts.items() if value and count > 1]
            if duplicates:
                blockers.append({"code": f"duplicate_final_{label}", "message": f"Planned creates contain duplicate {label.replace('_', ' ')} values"})
        planned_asset_tags = [
            plan["values"]["asset_tag"]
            for plan in intended
            if plan["disposition"] in {"create_new", "create_asset"}
            and plan["values"].get("asset_tag")
        ]
        if planned_asset_tags and self.db.scalar(
            select(func.count(ManagedAsset.id)).where(
                func.lower(ManagedAsset.asset_tag).in_(
                    {value.casefold() for value in planned_asset_tags}
                )
            )
        ):
            blockers.append({
                "code": "managed_asset_identifier_conflict",
                "message": "A planned asset tag already exists on a managed asset",
            })
        planned_hostnames = {
            plan["values"]["hostname"].casefold()
            for plan in intended
            if plan["disposition"] in {"create_new", "create_asset"}
            and plan["values"].get("hostname")
        }
        planned_serials = {
            plan["values"]["serial_number"]
            for plan in intended
            if plan["disposition"] in {"create_new", "create_asset"}
            and plan["values"].get("serial_number")
        }
        raw_property_id = session.mapping_metadata.get("tenant_property_id")
        try:
            import_property_id = UUID(raw_property_id) if raw_property_id else None
        except ValueError:
            import_property_id = None
        organization_id = self.db.info.get("organization_id")
        if planned_hostnames and import_property_id:
            existing_devices = self.db.scalar(
                select(func.count(Device.id)).where(
                    Device.property_id == import_property_id,
                    func.lower(Device.hostname).in_(planned_hostnames),
                )
            )
            existing_assets = self.db.scalar(
                select(func.count(ManagedAsset.id)).where(
                    ManagedAsset.organization_id == organization_id,
                    ManagedAsset.property_id == import_property_id,
                    func.lower(ManagedAsset.name).in_(planned_hostnames),
                )
            )
            if existing_devices or existing_assets:
                blockers.append({
                    "code": "inventory_hostname_conflict",
                    "message": "A planned hostname already exists in this property's inventory; review the match instead of creating a duplicate",
                })
        if planned_serials and self.db.scalar(
            select(func.count(ManagedAsset.id)).where(
                ManagedAsset.organization_id == organization_id,
                ManagedAsset.property_id == import_property_id,
                func.lower(ManagedAsset.serial_number).in_(
                    {value.casefold() for value in planned_serials}
                ),
            )
        ):
            blockers.append({
                "code": "managed_asset_serial_conflict",
                "message": "A planned serial number already exists on a managed asset",
            })
        macs = [
            plan["values"]["mac_address"]
            for plan in intended
            if plan["disposition"] in {"create_new", "create_asset"}
            and plan["values"].get("mac_address")
        ]
        serials = list(planned_serials)
        if planned_asset_tags or macs or serials:
            identifier_conflicts = []
            if planned_asset_tags:
                identifier_conflicts.append(
                    func.lower(Device.asset_tag).in_(
                        {value.casefold() for value in planned_asset_tags}
                    )
                )
            if macs:
                identifier_conflicts.append(Device.mac_address.in_(macs))
            if serials:
                identifier_conflicts.append(Device.serial_number.in_(serials))
            if self.db.scalar(
                select(func.count(Device.id)).where(or_(*identifier_conflicts))
            ):
                blockers.append({"code": "inventory_identifier_conflict", "message": "A planned identifier now exists in inventory"})
        counts = Counter(plan["disposition"] for plan in plans)
        if import_property_id is None or organization_id is None or not self.db.scalar(
            select(Property.id).where(
                Property.id == import_property_id,
                Property.organization_id == organization_id,
                Property.is_active.is_(True),
            )
        ):
            blockers.append({
                "code": "missing_import_property",
                "message": "Select an active property in this organization before final inventory changes",
            })
        return {
            "ready": not blockers,
            "status": session.status.value,
            "plan_version": session.plan_version + 1,
            "blocking_issues": blockers,
            "warnings": warnings,
            "counts": dict(counts),
            "estimated_changes": {
                "creates": counts["create_new"] + counts["create_asset"],
                "device_creates": counts["create_new"],
                "asset_creates": counts["create_asset"],
                "updates": counts["enrich_existing"] + counts["merge_reviewed"],
                "links": counts["link_existing"] + counts["link_discovery"],
                "skips": counts["skip"] + counts["invalid"],
            },
            "plans": plans,
        }

    def execution_plan(self, session_id: UUID, actor: User | None = None) -> dict[str, Any]:
        readiness = self.readiness(session_id)
        session = self._session(session_id, lock=actor is not None)
        if actor:
            session.plan_version = readiness["plan_version"]
            session.status = (
                ImportSessionStatus.READY
                if readiness["ready"]
                else ImportSessionStatus.REVIEW_REQUIRED
            )
            existing = {
                item.imported_device_id: item
                for item in session.execution_results
            }
            for plan in readiness["plans"]:
                row_id = UUID(plan["imported_device_id"])
                result = existing.get(row_id)
                if not result:
                    result = ImportExecutionResult(
                        import_session_id=session.id,
                        imported_device_id=row_id,
                        action=plan["disposition"],
                    )
                    self.db.add(result)
                if result.status in {ImportExecutionStatus.PENDING, ImportExecutionStatus.FAILED}:
                    result.action = plan["disposition"]
                    result.plan = plan
            create_audit_log(self.db, actor.username, "IMPORT_EXECUTION_PLAN_GENERATED", "ImportSession", str(session.id), f"Generated immutable candidate plan version {session.plan_version}")
            self.db.commit()
        return readiness

    def _create_device(self, result: ImportExecutionResult, row: ImportedDevice, actor: User) -> Device:
        payload = DeviceCreate(**result.plan["values"])
        values = payload.model_dump(exclude={"status"})
        session = self._session(row.import_session_id)
        raw_property_id = session.mapping_metadata.get("tenant_property_id")
        try:
            property_id = UUID(raw_property_id) if raw_property_id else None
        except ValueError as error:
            raise FinalizationValidationError("Import property is invalid; re-review the session") from error
        organization_id = self.db.info.get("organization_id")
        if property_id is None or not self.db.scalar(
            select(Property.id).where(
                Property.id == property_id,
                Property.organization_id == organization_id,
                Property.is_active.is_(True),
            )
        ):
            raise FinalizationValidationError("Import property is no longer active in this organization")
        device = Device(
            **values,
            property_id=property_id,
            status=values["inventory_status"],
            network_status="Unknown",
        )
        self.db.add(device)
        self.db.flush()
        row.linked_device_id = device.id
        result.target_device_id = device.id
        result.after_snapshot = self._safe_snapshot(device)
        create_audit_log(self.db, actor.username, "IMPORT_DEVICE_CREATED", "Device", str(device.id), f"Created device {device.hostname} from reviewed import row {row.source_row_number}")
        return device

    @staticmethod
    def _asset_snapshot(asset: ManagedAsset) -> dict[str, Any]:
        fields = (
            "asset_number", "name", "asset_tag", "device_type", "status", "ci_category",
            "vendor", "model", "serial_number", "department_id", "department_name",
            "room_id", "location_name", "business_owner", "description", "deployment_date",
            "source",
        )
        return {
            field: value.isoformat() if hasattr((value := getattr(asset, field, None)), "isoformat")
            else str(value) if isinstance(value, UUID) else value
            for field in fields
        }

    def _create_asset(self, result: ImportExecutionResult, row: ImportedDevice, actor: User) -> ManagedAsset:
        values = result.plan["values"]
        session = self._session(row.import_session_id)
        raw_property_id = session.mapping_metadata.get("tenant_property_id")
        try:
            property_id = UUID(raw_property_id) if raw_property_id else None
        except ValueError as error:
            raise FinalizationValidationError("Import property is invalid; re-review the session") from error
        organization_id = self.db.info.get("organization_id")
        if property_id is None or organization_id is None or not self.db.scalar(
            select(Property.id).where(
                Property.id == property_id,
                Property.organization_id == organization_id,
                Property.is_active.is_(True),
            )
        ):
            raise FinalizationValidationError("Import property is no longer active in this organization")
        department_id = UUID(values["department_id"]) if values.get("department_id") else None
        room_id = UUID(values["room_id"]) if values.get("room_id") else None
        deployment_date = date.fromisoformat(values["deployment_date"]) if values.get("deployment_date") else None
        asset_number = int(self.db.scalar(text("SELECT nextval('managed_asset_number_seq')")))
        asset = ManagedAsset(
            asset_number=f"HIOP-{asset_number:06d}",
            organization_id=organization_id,
            property_id=property_id,
            name=values["hostname"],
            asset_tag=values.get("asset_tag"),
            device_type=values.get("device_type") or "Computer (type not specified)",
            status="deployed" if deployment_date else "active",
            ci_category="device",
            vendor=values.get("brand") or values.get("vendor"),
            model=values.get("model"),
            serial_number=values.get("serial_number"),
            department_id=department_id,
            department_name=values.get("department"),
            room_id=room_id,
            location_name=values.get("location"),
            business_owner=values.get("business_owner"),
            description=values.get("description"),
            deployment_date=deployment_date,
            source="inventory_import",
            field_sources={"organizational_metadata": "Inventory import"},
            created_by=str(actor.id),
            updated_by=str(actor.id),
        )
        self.db.add(asset)
        self.db.flush()
        result.plan = {**result.plan, "target_asset_id": str(asset.id)}
        result.after_snapshot = self._asset_snapshot(asset)
        self.db.add(AssetLifecycleEvent(
            asset_id=asset.id,
            organization_id=organization_id,
            previous_status=None,
            new_status=asset.status,
            reason="Inventory import",
            notes=f"Created from reviewed import row {row.source_row_number}",
            changed_by=str(actor.id),
            changed_by_name=actor.username,
        ))
        create_audit_log(
            self.db, actor.username, "IMPORT_MANAGED_ASSET_CREATED", "ManagedAsset",
            str(asset.id), f"Created {asset.asset_number} from reviewed import row {row.source_row_number}",
        )
        return asset

    def _target(self, result: ImportExecutionResult) -> Device:
        target_id = result.plan.get("target_device_id")
        target = self.db.get(Device, UUID(target_id)) if target_id else None
        if not target:
            raise FinalizationConflictError("Reviewed inventory target no longer exists")
        reviewed_updated_at = result.plan.get("target_updated_at")
        current_updated_at = target.updated_at.isoformat() if target.updated_at else None
        if reviewed_updated_at and reviewed_updated_at != current_updated_at:
            raise FinalizationConflictError(
                "Reviewed inventory target changed after plan approval; re-review is required"
            )
        return target

    def _link_discovery(
        self,
        result: ImportExecutionResult,
        row: ImportedDevice,
        target: Device,
        actor: User,
    ) -> None:
        discovery_id = result.plan.get("target_discovery_id")
        if not discovery_id:
            return
        discovery = self.db.get(DiscoveredDevice, UUID(discovery_id))
        if not discovery:
            raise FinalizationConflictError("Reviewed Discovery record no longer exists")
        if discovery.approved_device_id and discovery.approved_device_id != target.id:
            raise FinalizationConflictError("Discovery was linked to another inventory device")
        discovery.approved_device_id = target.id
        discovery.review_status = ReviewStatus.APPROVED
        discovery.reviewed_by = actor.id
        discovery.reviewed_at = datetime.now(timezone.utc)
        row.linked_discovery_id = discovery.id
        result.target_discovery_id = discovery.id
        create_audit_log(self.db, actor.username, "IMPORT_DISCOVERY_LINKED", "DiscoveredDevice", str(discovery.id), f"Linked reviewed Discovery record to device {target.id}")

    def _link_existing(self, result: ImportExecutionResult, row: ImportedDevice, actor: User) -> Device:
        target = self._target(result)
        result.before_snapshot = self._safe_snapshot(target)
        row.linked_device_id = target.id
        result.target_device_id = target.id
        self._link_discovery(result, row, target, actor)
        result.after_snapshot = self._safe_snapshot(target)
        create_audit_log(self.db, actor.username, "IMPORT_EXISTING_DEVICE_LINKED", "Device", str(target.id), f"Linked reviewed import row {row.source_row_number} without overwriting inventory")
        return target

    def _enrich(self, result: ImportExecutionResult, row: ImportedDevice, actor: User) -> Device:
        target = self._target(result)
        before = self._safe_snapshot(target)
        approved = set(result.plan.get("approved_fields", []))
        overwrites = set(result.plan.get("approved_overwrites", []))
        values = result.plan["values"]
        changed: list[str] = []
        for field in approved:
            if field not in ENRICHABLE_FIELDS:
                raise FinalizationValidationError("Execution plan contains an unsupported field")
            incoming = values.get(field)
            current = getattr(target, field, None)
            if incoming in (None, ""):
                continue
            if current not in (None, "") and field not in overwrites:
                continue
            if field in IDENTIFIER_FIELDS and current not in (None, "") and field not in overwrites:
                raise FinalizationConflictError(f"{field.replace('_', ' ')} overwrite was not approved")
            if field.endswith("_id") and incoming:
                incoming = UUID(str(incoming))
            setattr(target, field, incoming)
            changed.append(field)
        if "inventory_status" in changed:
            target.status = target.inventory_status
        result.before_snapshot = before
        result.after_snapshot = self._safe_snapshot(target)
        row.linked_device_id = target.id
        result.target_device_id = target.id
        self._link_discovery(result, row, target, actor)
        create_audit_log(self.db, actor.username, "IMPORT_DEVICE_MERGED" if result.action == "merge_reviewed" else "IMPORT_DEVICE_ENRICHED", "Device", str(target.id), f"Applied {len(changed)} explicitly reviewed fields from import row {row.source_row_number}")
        return target

    def _execute_result(self, result: ImportExecutionResult, actor: User) -> None:
        row = self.db.get(ImportedDevice, result.imported_device_id)
        if not row or row.import_session_id != result.import_session_id:
            raise FinalizationConflictError("Execution row no longer belongs to this session")
        result.status = ImportExecutionStatus.RUNNING
        result.started_at = datetime.now(timezone.utc)
        self.db.flush()
        if result.action in {"skip", "invalid"}:
            result.status = ImportExecutionStatus.SKIPPED
        elif result.action == "create_new":
            self._create_device(result, row, actor)
            result.status = ImportExecutionStatus.COMPLETED
        elif result.action == "create_asset":
            self._create_asset(result, row, actor)
            result.status = ImportExecutionStatus.COMPLETED
        elif result.action in {"link_existing", "link_discovery"}:
            target = self._link_existing(result, row, actor)
            if result.action == "link_discovery" and not result.target_discovery_id:
                self._link_discovery(result, row, target, actor)
            result.status = ImportExecutionStatus.COMPLETED
        elif result.action in {"enrich_existing", "merge_reviewed"}:
            self._enrich(result, row, actor)
            result.status = ImportExecutionStatus.COMPLETED
        else:
            raise FinalizationValidationError("Execution plan contains an unresolved action")
        result.completed_at = datetime.now(timezone.utc)

    def _summary(self, session: ImportSession) -> dict[str, int]:
        counts = Counter(item.status.value for item in session.execution_results)
        actions = Counter(
            item.action
            for item in session.execution_results
            if item.status == ImportExecutionStatus.COMPLETED
        )
        return {
            "total": len(session.execution_results),
            "completed_rows": counts["completed"],
            "failed_rows": counts["failed"],
            "skipped_rows": counts["skipped"],
            "rollback_completed_rows": counts["rolled_back"],
            "rollback_failed_rows": counts["rollback_failed"],
            "created_devices": actions["create_new"],
            "created_assets": actions["create_asset"],
            "linked_devices": actions["link_existing"] + actions["link_discovery"],
            "enriched_devices": actions["enrich_existing"],
            "merged_devices": actions["merge_reviewed"],
        }

    def finalize(
        self,
        session_id: UUID,
        actor: User,
        *,
        plan_version: int,
        idempotency_key: str,
        confirmed: bool,
    ) -> dict[str, Any]:
        session = self._session(session_id, lock=True)
        if not confirmed:
            raise FinalizationValidationError("Both final confirmation acknowledgements are required")
        existing_key = (session.execution_summary or {}).get("idempotency_key")
        if existing_key == idempotency_key and session.status in {
            ImportSessionStatus.COMPLETED,
            ImportSessionStatus.PARTIAL,
            ImportSessionStatus.FAILED,
        }:
            return self.results(session_id)
        if session.status in {ImportSessionStatus.IMPORTING, ImportSessionStatus.ROLLED_BACK}:
            raise FinalizationConflictError(f"Session is {session.status.value}")
        if session.status == ImportSessionStatus.COMPLETED:
            raise FinalizationConflictError("Completed session cannot be executed again")
        readiness = self.readiness(session_id)
        if not readiness["ready"]:
            raise FinalizationValidationError("Session is not ready for final import")
        if plan_version != session.plan_version:
            raise FinalizationConflictError("Execution plan is stale; generate and review it again")
        settings = read_import_settings(self.db)
        active_imports = self.db.scalar(
            select(func.count(ImportSession.id)).where(
                ImportSession.status == ImportSessionStatus.IMPORTING,
                ImportSession.id != session_id,
            )
        ) or 0
        if active_imports >= settings["maximum_concurrent_imports"]:
            raise FinalizationConflictError("Maximum concurrent final imports reached")
        session.status = ImportSessionStatus.IMPORTING
        session.plan_locked_at = datetime.now(timezone.utc)
        session.finalized_by = actor.id
        session.finalization_started_at = session.plan_locked_at
        session.execution_summary = {"idempotency_key": idempotency_key}
        create_audit_log(self.db, actor.username, "IMPORT_FINALIZATION_STARTED", "ImportSession", str(session.id), f"Started reviewed plan version {plan_version}")
        self.db.commit()
        self._event("import_finalization_started", session.id, total=len(session.execution_results))
        pending = [item for item in session.execution_results if item.status in {ImportExecutionStatus.PENDING, ImportExecutionStatus.FAILED}]
        batch_size = settings["final_import_batch_size"]
        for offset in range(0, len(pending), batch_size):
            batch = pending[offset : offset + batch_size]
            for result in batch:
                try:
                    with self.db.begin_nested():
                        self._execute_result(result, actor)
                    self._event("import_row_completed", session.id, row_id=str(result.imported_device_id), action=result.action)
                except (IntegrityError, ValueError, FinalizationConflictError) as exc:
                    result.status = ImportExecutionStatus.FAILED
                    result.error_code = "state_conflict" if isinstance(exc, FinalizationConflictError) else "validation_or_uniqueness"
                    result.safe_error_message = str(exc)[:500]
                    result.completed_at = datetime.now(timezone.utc)
                    create_audit_log(self.db, actor.username, "IMPORT_ROW_FAILED", "ImportedDevice", str(result.imported_device_id), result.safe_error_message)
                    self._event("import_row_failed", session.id, row_id=str(result.imported_device_id), code=result.error_code)
            self.db.commit()
            self._event("import_finalization_progress", session.id, processed=min(offset + len(batch), len(pending)), total=len(pending))
        session = self._session(session_id, lock=True)
        summary = self._summary(session)
        summary["idempotency_key"] = idempotency_key
        session.execution_summary = summary
        session.finalization_completed_at = datetime.now(timezone.utc)
        session.processing_completed_at = session.finalization_completed_at
        session.status = (
            ImportSessionStatus.COMPLETED
            if summary["failed_rows"] == 0
            else ImportSessionStatus.PARTIAL
            if summary["completed_rows"] > 0
            else ImportSessionStatus.FAILED
        )
        action = {
            ImportSessionStatus.COMPLETED: "IMPORT_FINALIZATION_COMPLETED",
            ImportSessionStatus.PARTIAL: "IMPORT_FINALIZATION_PARTIAL",
            ImportSessionStatus.FAILED: "IMPORT_FINALIZATION_FAILED",
        }[session.status]
        create_audit_log(self.db, actor.username, action, "ImportSession", str(session.id), f"Final import ended with {summary['completed_rows']} completed and {summary['failed_rows']} failed rows")
        self.db.commit()
        self._event(f"import_finalization_{session.status.value}", session.id, summary=summary)
        self._notify(
            f"HIOP inventory import {session.status.value}",
            f"Import {session.original_filename} completed with {summary['completed_rows']} successful and {summary['failed_rows']} failed rows.",
            failure=summary["failed_rows"] > 0,
        )
        return self.results(session_id)

    def results(self, session_id: UUID, *, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        session = self._session(session_id)
        statement = select(ImportExecutionResult).where(ImportExecutionResult.import_session_id == session_id)
        total = self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        items = list(self.db.scalars(statement.order_by(ImportExecutionResult.created_at).offset((page - 1) * page_size).limit(page_size)).all())
        return {
            "session_id": session.id,
            "status": session.status.value,
            "summary": session.execution_summary,
            "rollback_available": (
                session.status in {ImportSessionStatus.COMPLETED, ImportSessionStatus.PARTIAL}
                and any(
                    item.status == ImportExecutionStatus.COMPLETED
                    for item in session.execution_results
                )
            ),
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size),
        }

    def rollback_preview(self, session_id: UUID) -> dict[str, Any]:
        session = self._session(session_id)
        if session.status not in {ImportSessionStatus.COMPLETED, ImportSessionStatus.PARTIAL}:
            raise FinalizationConflictError("Only completed or partial imports can be rolled back")
        reversible, blocked = [], []
        for result in session.execution_results:
            if result.status != ImportExecutionStatus.COMPLETED:
                continue
            if result.action == "create_asset":
                asset_id = (result.plan or {}).get("target_asset_id")
                asset = self.db.get(ManagedAsset, UUID(asset_id)) if asset_id else None
                if not asset:
                    blocked.append({"result_id": str(result.id), "reason": "Imported managed asset no longer exists"})
                    continue
                current = self._asset_snapshot(asset)
                expected = result.after_snapshot
                changed_later = any(current.get(field) != value for field, value in expected.items())
                if changed_later:
                    blocked.append({"result_id": str(result.id), "reason": "Managed asset values changed after import"})
                else:
                    reversible.append({"result_id": str(result.id), "action": result.action, "target_asset_id": str(asset.id)})
                continue
            target = self.db.get(Device, result.target_device_id) if result.target_device_id else None
            if not target:
                blocked.append({"result_id": str(result.id), "reason": "Target device no longer exists"})
                continue
            current = self._safe_snapshot(target)
            expected = result.after_snapshot
            changed_later = any(current.get(field) != value for field, value in expected.items() if field != "updated_at")
            if changed_later:
                blocked.append({"result_id": str(result.id), "reason": "Inventory values changed after import"})
            else:
                reversible.append({"result_id": str(result.id), "action": result.action, "target_device_id": str(target.id)})
        return {"session_id": session.id, "reversible": reversible, "non_reversible": blocked, "can_rollback": bool(reversible) and not blocked}

    def rollback(self, session_id: UUID, actor: User) -> dict[str, Any]:
        preview = self.rollback_preview(session_id)
        if not preview["can_rollback"]:
            raise FinalizationConflictError("Rollback is no longer fully safe")
        session = self._session(session_id, lock=True)
        session.status = ImportSessionStatus.IMPORTING
        create_audit_log(self.db, actor.username, "IMPORT_ROLLBACK_STARTED", "ImportSession", str(session.id), f"Started rollback of {len(preview['reversible'])} actions")
        self.db.commit()
        self._event("import_rollback_started", session.id, total=len(preview["reversible"]))
        for index, item in enumerate(preview["reversible"], 1):
            result = self.db.get(ImportExecutionResult, UUID(item["result_id"]))
            target = self.db.get(Device, result.target_device_id) if result.target_device_id else None
            try:
                if result.action == "create_asset":
                    asset_id = (result.plan or {}).get("target_asset_id")
                    asset = self.db.get(ManagedAsset, UUID(asset_id)) if asset_id else None
                    if not asset:
                        raise FinalizationConflictError("Imported managed asset no longer exists")
                    previous = asset.status
                    asset.status = "retired"
                    asset.retirement_date = datetime.now(timezone.utc).date()
                    asset.retirement_reason = "other"
                    asset.retired_by = str(actor.id)
                    asset.updated_by = str(actor.id)
                    asset.updated_at = datetime.now(timezone.utc)
                    self.db.add(AssetLifecycleEvent(
                        asset_id=asset.id,
                        organization_id=asset.organization_id,
                        previous_status=previous,
                        new_status="retired",
                        reason="other",
                        notes="Retired as a non-destructive inventory-import rollback",
                        changed_by=str(actor.id),
                        changed_by_name=actor.username,
                    ))
                    create_audit_log(self.db, actor.username, "IMPORT_MANAGED_ASSET_ROLLED_BACK", "ManagedAsset", str(asset.id), "Managed asset retired by import rollback")
                elif result.action == "create_new" and target:
                    target.inventory_status = "Retired"
                    target.status = "Retired"
                elif result.action in {"enrich_existing", "merge_reviewed"} and target:
                    for field, value in result.before_snapshot.items():
                        if field == "updated_at":
                            continue
                        if field.endswith("_id") and value:
                            value = UUID(value)
                        setattr(target, field, value)
                if result.target_discovery_id and target:
                    discovery = self.db.get(DiscoveredDevice, result.target_discovery_id)
                    if discovery and discovery.approved_device_id == target.id:
                        discovery.approved_device_id = None
                        discovery.review_status = ReviewStatus.PENDING
                        discovery.reviewed_by = None
                        discovery.reviewed_at = None
                row = self.db.get(ImportedDevice, result.imported_device_id)
                if row and target:
                    row.linked_device_id = None
                    row.linked_discovery_id = None
                result.status = ImportExecutionStatus.ROLLED_BACK
                result.rolled_back_at = datetime.now(timezone.utc)
                create_audit_log(self.db, actor.username, "IMPORT_ROW_ROLLED_BACK", "ImportedDevice", str(result.imported_device_id), f"Compensated {result.action} without deleting import history")
            except Exception:
                logger.exception(
                    "Import rollback failed session=%s result=%s",
                    session.id,
                    result.id,
                )
                result.status = ImportExecutionStatus.ROLLBACK_FAILED
                result.safe_error_message = "Rollback could not safely restore this row"
            self.db.commit()
            self._event("import_rollback_progress", session.id, processed=index, total=len(preview["reversible"]))
        session = self._session(session_id, lock=True)
        summary = self._summary(session)
        session.execution_summary = summary
        if summary["rollback_failed_rows"]:
            session.status = ImportSessionStatus.PARTIAL
            event = "import_rollback_failed"
        else:
            session.status = ImportSessionStatus.ROLLED_BACK
            session.rollback_by = actor.id
            session.rollback_at = datetime.now(timezone.utc)
            event = "import_rollback_completed"
        create_audit_log(self.db, actor.username, event.upper(), "ImportSession", str(session.id), f"Rollback finished with {summary['rollback_failed_rows']} failures")
        self.db.commit()
        self._event(event, session.id, summary=summary)
        if summary["rollback_failed_rows"]:
            self._notify(
                "HIOP import rollback requires attention",
                f"Rollback for {session.original_filename} has {summary['rollback_failed_rows']} failed compensating actions.",
                failure=True,
            )
        return self.results(session_id)

    def retry_failed(self, session_id: UUID, actor: User) -> dict[str, Any]:
        session = self._session(session_id, lock=True)
        settings = read_import_settings(self.db)
        if session.status != ImportSessionStatus.PARTIAL:
            raise FinalizationConflictError("Only partial sessions can retry failed rows")
        if session.retry_count >= settings["final_import_retry_limit"]:
            raise FinalizationConflictError("Retry limit reached")
        failed = [item for item in session.execution_results if item.status == ImportExecutionStatus.FAILED]
        if any(item.error_code == "state_conflict" for item in failed):
            raise FinalizationConflictError("Identifier or stale-state conflicts require re-review")
        for item in failed:
            item.status = ImportExecutionStatus.PENDING
            item.retry_count += 1
            item.error_code = None
            item.safe_error_message = None
        session.retry_count += 1
        session.status = ImportSessionStatus.READY
        session.plan_locked_at = None
        self.db.commit()
        return self.finalize(
            session_id,
            actor,
            plan_version=session.plan_version,
            idempotency_key=f"retry:{session.id}:{session.retry_count}",
            confirmed=True,
        )
