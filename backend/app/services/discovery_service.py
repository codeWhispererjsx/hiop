"""Discovery engine and administrator review workflow."""

import csv
import io
import ipaddress
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.discovery.fingerprinting import fingerprint, lookup_vendor
from app.discovery.network import (
    ensure_authorized,
    icmp_probe,
    inspect_arp_table,
    is_ignored,
    normalize_mac,
    reverse_dns,
)
from app.models.discovered_device import (
    DiscoveredDevice,
    DiscoveryRun,
    DiscoveryStatus,
    RunStatus,
    ReviewStatus,
)
from app.models.device import Device
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.repositories.discovery_repository import DiscoveryRepository, DiscoveryRunRepository
from app.schemas.device import DeviceCreate
from app.schemas.discovery import InventoryApproval
from app.services.audit_service import create_audit_log
from app.services.email_service import send_email
from app.services.hierarchy_service import resolve_device_hierarchy
from app.services.settings_service import DEFAULTS, read_discovery
from app.websocket.connection_manager import manager


Observation = dict[str, Any]
Probe = Callable[[str, int], tuple[bool, float | None]]
logger = logging.getLogger(__name__)


class DiscoveryNotFoundError(ValueError):
    pass


class DiscoveryConflictError(ValueError):
    pass


class DiscoveryStateError(ValueError):
    pass


def _csv_safe(value: Any) -> str:
    text = str(value) if value is not None else ""
    return f"'{text}" if text.startswith(("=", "+", "-", "@")) else text


class DiscoveryService:
    def __init__(
        self,
        db: Session,
        *,
        config: dict[str, Any] | None = None,
        probe: Probe = icmp_probe,
        arp_reader: Callable[[], dict[str, str]] = inspect_arp_table,
        resolver: Callable[[str, float], str | None] = reverse_dns,
        publisher: Callable[[dict[str, Any]], None] = manager.broadcast_from_thread,
        email_sender: Callable[..., None] = send_email,
    ) -> None:
        self.db = db
        self.devices = DiscoveryRepository(db)
        self.runs = DiscoveryRunRepository(db)
        self.config = config
        self.probe = probe
        self.arp_reader = arp_reader
        self.resolver = resolver
        self.publisher = publisher
        self.email_sender = email_sender

    def _email_notification(self, subject: str, body: str) -> None:
        try:
            stored = {
                row.key: row.value
                for row in self.db.query(SystemSetting)
                .filter(SystemSetting.key.in_([
                    "notifications.email_notifications",
                    "notifications.recipient_email",
                ]))
                .all()
            }
            enabled = stored.get(
                "notifications.email_notifications",
                DEFAULTS["notifications.email_notifications"],
            ).lower() == "true"
            recipient = stored.get(
                "notifications.recipient_email",
                DEFAULTS["notifications.recipient_email"],
            ) or None
            if enabled:
                self.email_sender(subject=subject, body=body, recipient=recipient)
        except Exception:
            logger.exception("Discovery email notification failed")

    def _notify(self, event: dict[str, Any], subject: str, body: str) -> None:
        try:
            self.publisher(event)
        except Exception:
            logger.exception("Discovery WebSocket notification failed")
        self._email_notification(subject, body)

    def _publish(self, event: dict[str, Any]) -> None:
        try:
            self.publisher(event)
        except Exception:
            logger.exception("Discovery WebSocket notification failed")

    def _settings(self) -> dict[str, Any]:
        return self.config.copy() if self.config is not None else read_discovery(self.db)

    def _validated_range(self, range_scanned: str) -> tuple[ipaddress.IPv4Network, list[ipaddress.IPv4Network]]:
        settings = self._settings()
        return ensure_authorized(
            range_scanned,
            settings["authorized_cidr_ranges"],
            settings.get("ignore_ranges", ""),
            max_hosts=settings["max_hosts_per_run"],
        )

    def start_run(self, range_scanned: str, trigger_type: str, triggered_by: str | None = None) -> DiscoveryRun:
        network, _ = self._validated_range(range_scanned)
        run = DiscoveryRun(
            range_scanned=str(network),
            status=RunStatus.RUNNING,
            trigger_type=trigger_type,
            triggered_by=triggered_by,
            hosts_attempted=0,
            hosts_responded=0,
            new_devices=0,
            matched_devices=0,
            updated_devices=0,
            error_count=0,
        )
        self.runs.add(run)
        self.db.flush()
        return run

    def _inventory_match(self, observation: Observation) -> Device | None:
        mac = normalize_mac(observation.get("mac_address"))
        if mac:
            device = self.devices.find_inventory_by_mac(mac)
            if device:
                return device
        approved_id = observation.get("approved_device_id")
        if approved_id:
            try:
                device = self.db.get(Device, UUID(str(approved_id)))
            except ValueError:
                device = None
            if device:
                return device
        hostname = observation.get("hostname")
        ip_address = observation["ip_address"]
        if hostname:
            device = self.devices.find_inventory_by_ip_hostname(ip_address, hostname)
            if device:
                return device
        return self.devices.find_inventory_by_ip(ip_address)

    def match_observation(self, observation: Observation) -> DiscoveredDevice | None:
        mac = normalize_mac(observation.get("mac_address"))
        if mac:
            matched = self.devices.find_by_mac(mac)
            if matched:
                return matched
        approved_id = observation.get("approved_device_id")
        if approved_id:
            try:
                approved_uuid = UUID(str(approved_id))
            except ValueError:
                approved_uuid = None
            matched = self.devices.find_by_approved_device(approved_uuid) if approved_uuid else None
            if matched:
                return matched
        hostname = observation.get("hostname")
        ip_address = observation["ip_address"]
        if hostname:
            matched = self.devices.find_by_ip_hostname(ip_address, hostname)
            if matched:
                return matched
        return self.devices.find_by_ip(ip_address)

    def _record_observation(self, observation: Observation) -> tuple[DiscoveredDevice, bool, bool]:
        now = datetime.now(timezone.utc)
        observation = observation.copy()
        observation["mac_address"] = normalize_mac(observation.get("mac_address"))
        inventory = self._inventory_match(observation)
        if inventory:
            observation["approved_device_id"] = inventory.id
        existing = self.match_observation(observation)
        if existing:
            for field in (
                "ip_address", "mac_address", "hostname", "vendor",
                "operating_system_guess", "device_type_guess", "subnet",
                "discovery_method", "response_time", "status", "confidence_score",
                "approved_device_id", "network_zone_id",
            ):
                if field in observation and observation[field] is not None:
                    setattr(existing, field, observation[field])
            existing.last_seen_at = now
            existing.times_seen += 1
            self.db.flush()
            return existing, False, inventory is not None

        device = DiscoveredDevice(
            ip_address=observation["ip_address"],
            mac_address=observation.get("mac_address"),
            hostname=observation.get("hostname"),
            vendor=observation.get("vendor"),
            operating_system_guess=observation.get("operating_system_guess"),
            device_type_guess=observation.get("device_type_guess", "unknown"),
            network_zone_id=observation.get("network_zone_id"),
            subnet=observation.get("subnet"),
            discovery_method=observation.get("discovery_method", "icmp"),
            response_time=observation.get("response_time"),
            status=observation.get("status", DiscoveryStatus.UNKNOWN),
            confidence_score=observation.get("confidence_score"),
            approved_device_id=inventory.id if inventory else observation.get("approved_device_id"),
            first_seen_at=now,
            last_seen_at=now,
        )
        self.devices.add(device)
        self.db.flush()
        return device, True, inventory is not None

    def record_observation(self, run_id: UUID, observation: Observation) -> DiscoveredDevice:
        if not self.runs.get(run_id):
            raise ValueError("Discovery run not found")
        return self._record_observation(observation)[0]

    def _observe_host(
        self,
        address: str,
        subnet: str,
        mac_address: str | None,
        settings: dict[str, Any],
    ) -> tuple[Observation | None, bool]:
        online, response_time = self.probe(address, settings["ping_timeout_seconds"])
        if not online and not mac_address:
            return None, False
        hostname = None
        if settings.get("automatic_hostname_lookup", True):
            hostname = self.resolver(address, float(settings["ping_timeout_seconds"]))
        vendor = lookup_vendor(mac_address) if settings.get("automatic_vendor_lookup", True) else None
        identity = fingerprint(hostname, vendor)
        method = "icmp+arp" if online and mac_address else "icmp" if online else "arp-cache"
        return {
            "ip_address": address,
            "mac_address": mac_address,
            "hostname": hostname,
            "vendor": vendor,
            "operating_system_guess": identity.operating_system_guess,
            "device_type_guess": identity.device_type_guess,
            "subnet": subnet,
            "discovery_method": method,
            "response_time": response_time,
            "status": DiscoveryStatus.ONLINE if online else DiscoveryStatus.UNKNOWN,
            "confidence_score": identity.confidence_score,
        }, online

    def discover_range(
        self,
        range_scanned: str,
        *,
        trigger_type: str = "manual",
        triggered_by: str | None = None,
        audit_actor: str | None = None,
    ) -> DiscoveryRun:
        settings = self._settings()
        if not settings.get("enabled", False):
            raise ValueError("Discovery is disabled")
        network, ignored = self._validated_range(range_scanned)
        run = self.start_run(str(network), trigger_type, triggered_by)
        started = time.monotonic()
        errors: list[str] = []
        try:
            arp_entries = {
                address: normalize_mac(mac)
                for address, mac in self.arp_reader().items()
                if ipaddress.ip_address(address) in network
            }
            hosts = [address for address in network.hosts() if not is_ignored(address, ignored)]
            run.hosts_attempted = len(hosts)
            workers = max(1, min(int(settings["concurrency_limit"]), 32, len(hosts) or 1))
            observations: list[tuple[Observation, bool]] = []
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="hiop-discovery") as executor:
                futures = {
                    executor.submit(
                        self._observe_host,
                        str(address),
                        str(network),
                        arp_entries.get(str(address)),
                        settings,
                    ): str(address)
                    for address in hosts
                }
                for future in as_completed(futures):
                    try:
                        observation, online = future.result()
                        if observation:
                            observations.append((observation, online))
                    except Exception as exc:
                        errors.append(f"{futures[future]}: {type(exc).__name__}")

            for observation, online in observations:
                _, is_new, inventory_matched = self._record_observation(observation)
                run.hosts_responded += int(online)
                run.new_devices += int(is_new)
                run.updated_devices += int(not is_new)
                run.matched_devices += int(inventory_matched)
            run.error_count = len(errors)
            run.error_summary = "; ".join(errors)[:4000] or None
            run.status = RunStatus.PARTIAL if errors else RunStatus.COMPLETED
            run.completed_at = datetime.now(timezone.utc)
            run.duration = round(time.monotonic() - started, 3)
            if audit_actor:
                create_audit_log(
                    self.db,
                    actor=audit_actor,
                    action="RUN_DISCOVERY",
                    entity_type="DiscoveryRun",
                    entity_id=str(run.id),
                    description=f"Completed discovery run for {network}",
                )
            self.db.commit()
            self.db.refresh(run)
            event = {
                    "event": "discovery_run_completed",
                    "run_id": str(run.id),
                    "status": run.status.value,
                    "new_devices": run.new_devices,
                    "matched_devices": run.matched_devices,
                }
            self._publish(event)
            threshold = max(0, int(settings.get("admin_notification_threshold", 0)))
            if run.new_devices >= threshold:
                self._email_notification(
                    "HIOP discovery run completed",
                    f"Discovery run {run.id} completed with {run.new_devices} new device(s).",
                )
            return run
        except Exception as exc:
            self.db.rollback()
            failed = DiscoveryRun(
                range_scanned=str(network),
                status=RunStatus.FAILED,
                trigger_type=trigger_type,
                triggered_by=triggered_by,
                error_count=1,
                error_summary=f"{type(exc).__name__}: {exc}"[:4000],
                completed_at=datetime.now(timezone.utc),
                duration=round(time.monotonic() - started, 3),
            )
            self.runs.add(failed)
            if audit_actor:
                create_audit_log(
                    self.db,
                    actor=audit_actor,
                    action="RUN_DISCOVERY_FAILED",
                    entity_type="DiscoveryRun",
                    entity_id=str(failed.id),
                    description=f"Discovery run failed for {network}",
                )
            self.db.commit()
            self._notify(
                {
                    "event": "discovery_run_failed",
                    "run_id": str(failed.id),
                    "status": RunStatus.FAILED.value,
                },
                "HIOP discovery run failed",
                f"Discovery run {failed.id} failed for {network}.",
            )
            raise

    def complete_run(self, run_id: UUID, summary: dict[str, Any]) -> DiscoveryRun:
        run = self.runs.get(run_id)
        if not run:
            raise ValueError("Discovery run not found")
        for field in (
            "hosts_attempted", "hosts_responded", "new_devices", "matched_devices",
            "updated_devices", "error_count", "duration", "error_summary",
        ):
            if field in summary:
                setattr(run, field, summary[field])
        run.status = RunStatus.PARTIAL if run.error_count else RunStatus.COMPLETED
        run.completed_at = datetime.now(timezone.utc)
        self.db.flush()
        return run

    def fail_run(self, run_id: UUID, error_summary: str) -> DiscoveryRun:
        run = self.runs.get(run_id)
        if not run:
            raise ValueError("Discovery run not found")
        run.status = RunStatus.FAILED
        run.error_count += 1
        run.error_summary = error_summary[:4000]
        run.completed_at = datetime.now(timezone.utc)
        self.db.flush()
        return run

    def history(self, *, offset: int = 0, limit: int = 100) -> list[DiscoveryRun]:
        return list(self.runs.list(offset=offset, limit=limit))

    def statistics(self) -> dict[str, Any]:
        values: dict[str, Any] = self.devices.statistics()
        latest = self.runs.latest()
        values["total_runs"] = self.runs.count()
        values["last_run"] = latest
        return values

    def get_discovered_device(self, discovery_id: UUID) -> DiscoveredDevice:
        device = self.devices.get(discovery_id)
        if not device:
            raise DiscoveryNotFoundError("Discovered device not found")
        return device

    def list_discovered_devices(
        self,
        *,
        search: str | None = None,
        status: str | None = None,
        review_status: str | None = None,
        sort_by: str = "last_seen_at",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 25,
    ) -> dict[str, Any]:
        items, total = self.devices.page(
            search=search,
            status=status,
            review_status=review_status,
            sort_by=sort_by,
            sort_order=sort_order,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        pages = max(1, (total + page_size - 1) // page_size)
        if total and page > pages:
            raise DiscoveryStateError("Requested page is outside the result set")
        return {"items": items, "total": total, "page": page, "page_size": page_size, "pages": pages}

    def _pending(self, discovery_id: UUID) -> DiscoveredDevice:
        discovered = self.get_discovered_device(discovery_id)
        if discovered.review_status != ReviewStatus.PENDING:
            raise DiscoveryStateError("Only pending discoveries can be reviewed")
        return discovered

    def _approve_one(
        self,
        discovery_id: UUID,
        payload: InventoryApproval,
        reviewer: User,
    ) -> tuple[DiscoveredDevice, Device]:
        discovered = self._pending(discovery_id)
        if discovered.approved_device_id:
            raise DiscoveryConflictError("Discovery is already linked to inventory")

        hostname = payload.hostname or discovered.hostname
        device_type = payload.device_type or discovered.device_type_guess
        ip_address = payload.ip_address or discovered.ip_address
        mac_address = payload.mac_address or discovered.mac_address
        missing = [
            name for name, value in (
                ("hostname", hostname), ("device_type", device_type),
                ("ip_address", ip_address), ("mac_address", mac_address),
            ) if not value
        ]
        if missing:
            raise DiscoveryStateError(f"Approval requires: {', '.join(missing)}")

        device_data = DeviceCreate(
            **payload.model_dump(exclude={"hostname", "device_type", "ip_address", "mac_address"}),
            hostname=hostname,
            device_type=device_type,
            ip_address=ip_address,
            mac_address=mac_address,
        )
        duplicate = self.db.query(Device).filter(or_(
            Device.asset_tag == device_data.asset_tag,
            Device.serial_number == device_data.serial_number,
            Device.mac_address == device_data.mac_address,
        )).first()
        if duplicate:
            raise DiscoveryConflictError("Approval would duplicate an existing inventory device")

        values = resolve_device_hierarchy(self.db, device_data.model_dump(exclude={"status"}))
        device = Device(
            **values,
            status=values["inventory_status"],
            network_status="Unknown",
        )
        self.db.add(device)
        self.db.flush()
        now = datetime.now(timezone.utc)
        discovered.approved_device_id = device.id
        discovered.review_status = ReviewStatus.APPROVED
        discovered.reviewed_by = reviewer.id
        discovered.reviewed_at = now
        create_audit_log(
            self.db,
            actor=reviewer.username,
            action="APPROVE_DISCOVERY",
            entity_type="DiscoveredDevice",
            entity_id=str(discovered.id),
            description=f"Approved discovery {discovered.ip_address} as inventory device {device.asset_tag}",
        )
        create_audit_log(
            self.db,
            actor=reviewer.username,
            action="CREATE_DEVICE_FROM_DISCOVERY",
            entity_type="Device",
            entity_id=str(device.id),
            description=f"Created inventory device {device.hostname} from discovery {discovered.id}",
        )
        self.db.flush()
        return discovered, device

    def approve(
        self,
        discovery_id: UUID,
        payload: InventoryApproval,
        reviewer: User,
    ) -> tuple[DiscoveredDevice, Device]:
        try:
            discovered, device = self._approve_one(discovery_id, payload, reviewer)
            self.db.commit()
            self.db.refresh(discovered)
            self.db.refresh(device)
        except IntegrityError as exc:
            self.db.rollback()
            raise DiscoveryConflictError("Approval conflicts with existing inventory") from exc
        except Exception:
            self.db.rollback()
            raise
        self._notify(
            {
                "event": "discovery_approved",
                "discovery_id": str(discovered.id),
                "device_id": str(device.id),
                "reviewed_by": reviewer.username,
            },
            "HIOP discovery approved",
            f"{reviewer.username} approved {discovered.ip_address} as {device.asset_tag}.",
        )
        return discovered, device

    def _review_one(
        self,
        discovery_id: UUID,
        review_status: ReviewStatus,
        reviewer: User,
        reason: str | None = None,
    ) -> DiscoveredDevice:
        discovered = self._pending(discovery_id)
        discovered.review_status = review_status
        discovered.reviewed_by = reviewer.id
        discovered.reviewed_at = datetime.now(timezone.utc)
        if reason:
            entry = f"Rejected by {reviewer.username}: {reason}"
            discovered.notes = f"{discovered.notes}\n{entry}".strip() if discovered.notes else entry
        action = "IGNORE_DISCOVERY" if review_status == ReviewStatus.IGNORED else "REJECT_DISCOVERY"
        create_audit_log(
            self.db,
            actor=reviewer.username,
            action=action,
            entity_type="DiscoveredDevice",
            entity_id=str(discovered.id),
            description=f"{review_status.value.title()} discovery {discovered.ip_address}",
        )
        self.db.flush()
        return discovered

    def review(
        self,
        discovery_id: UUID,
        review_status: ReviewStatus,
        reviewer: User,
        reason: str | None = None,
    ) -> DiscoveredDevice:
        if review_status not in (ReviewStatus.IGNORED, ReviewStatus.REJECTED):
            raise DiscoveryStateError("Unsupported review action")
        try:
            discovered = self._review_one(discovery_id, review_status, reviewer, reason)
            self.db.commit()
            self.db.refresh(discovered)
        except Exception:
            self.db.rollback()
            raise
        self._notify(
            {
                "event": f"discovery_{review_status.value}",
                "discovery_id": str(discovered.id),
                "reviewed_by": reviewer.username,
            },
            f"HIOP discovery {review_status.value}",
            f"{reviewer.username} marked {discovered.ip_address} as {review_status.value}.",
        )
        return discovered

    def bulk_approve(
        self,
        items: list[tuple[UUID, InventoryApproval]],
        reviewer: User,
    ) -> list[tuple[DiscoveredDevice, Device]]:
        try:
            results = [self._approve_one(discovery_id, payload, reviewer) for discovery_id, payload in items]
            self.db.commit()
            for discovered, device in results:
                self.db.refresh(discovered)
                self.db.refresh(device)
        except IntegrityError as exc:
            self.db.rollback()
            raise DiscoveryConflictError("Bulk approval conflicts with existing inventory") from exc
        except Exception:
            self.db.rollback()
            raise
        for discovered, device in results:
            self._notify(
                {"event": "discovery_approved", "discovery_id": str(discovered.id), "device_id": str(device.id), "reviewed_by": reviewer.username},
                "HIOP discovery approved",
                f"{reviewer.username} approved {discovered.ip_address} as {device.asset_tag}.",
            )
        return results

    def bulk_review(
        self,
        discovery_ids: list[UUID],
        review_status: ReviewStatus,
        reviewer: User,
        reason: str | None = None,
    ) -> list[DiscoveredDevice]:
        if review_status not in (ReviewStatus.IGNORED, ReviewStatus.REJECTED):
            raise DiscoveryStateError("Unsupported review action")
        try:
            results = [self._review_one(discovery_id, review_status, reviewer, reason) for discovery_id in discovery_ids]
            self.db.commit()
            for discovered in results:
                self.db.refresh(discovered)
        except Exception:
            self.db.rollback()
            raise
        for discovered in results:
            self._notify(
                {"event": f"discovery_{review_status.value}", "discovery_id": str(discovered.id), "reviewed_by": reviewer.username},
                f"HIOP discovery {review_status.value}",
                f"{reviewer.username} marked {discovered.ip_address} as {review_status.value}.",
            )
        return results

    def export_csv(self) -> tuple[str, str]:
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow([
            "ID", "IP Address", "MAC Address", "Hostname", "Vendor",
            "Device Type Guess", "Confidence Score", "Status", "Review Status",
            "First Seen", "Last Seen", "Times Seen", "Notes",
        ])
        for device in self.devices.list(offset=0, limit=1_000_000):
            writer.writerow([_csv_safe(value) for value in (
                device.id, device.ip_address, device.mac_address, device.hostname,
                device.vendor, device.device_type_guess, device.confidence_score,
                device.status.value, device.review_status.value,
                device.first_seen_at.isoformat(), device.last_seen_at.isoformat(),
                device.times_seen, device.notes,
            )])
        generated = datetime.now(timezone.utc)
        return "\ufeff" + output.getvalue(), f"hiop-discovery-{generated.strftime('%Y%m%d-%H%M%S')}.csv"
