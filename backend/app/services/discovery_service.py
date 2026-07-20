"""Conservative Discovery orchestration with no transport or approval workflow."""

import ipaddress
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID

from sqlalchemy.orm import Session

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
)
from app.models.device import Device
from app.repositories.discovery_repository import DiscoveryRepository, DiscoveryRunRepository
from app.services.settings_service import read_discovery


Observation = dict[str, Any]
Probe = Callable[[str, int], tuple[bool, float | None]]


class DiscoveryService:
    def __init__(
        self,
        db: Session,
        *,
        config: dict[str, Any] | None = None,
        probe: Probe = icmp_probe,
        arp_reader: Callable[[], dict[str, str]] = inspect_arp_table,
        resolver: Callable[[str, float], str | None] = reverse_dns,
    ) -> None:
        self.db = db
        self.devices = DiscoveryRepository(db)
        self.runs = DiscoveryRunRepository(db)
        self.config = config
        self.probe = probe
        self.arp_reader = arp_reader
        self.resolver = resolver

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
            self.db.commit()
            self.db.refresh(run)
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
            self.db.commit()
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
