"""Reviewed SNMP onboarding, inventory synchronization, rates, and retention."""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select

from app.models.device import Device
from app.models.discovered_device import DiscoveredDevice
from app.models.snmp import (
    SNMPDeviceLink, SNMPDiscoveryCandidate, SNMPInterface, SNMPInterfaceChange,
    SNMPMatchCandidate, SNMPMetric, SNMPPollRun, SNMPStateChange, SNMPTarget,
)
from app.schemas.device import DeviceCreate
from app.services.audit_service import create_audit_log
from app.services.device_service import create_device
from app.websocket.connection_manager import manager

COUNTER_BITS = {
    "interface.in_octets": 32, "interface.out_octets": 32,
    "interface.hc_in_octets": 64, "interface.hc_out_octets": 64,
    "interface.in_packets": 32, "interface.out_packets": 32,
    "interface.in_errors": 32, "interface.out_errors": 32,
    "interface.in_discards": 32, "interface.out_discards": 32,
}
RATE_KEYS = {
    "interface.in_octets": ("interface.in_bps", "bits_per_second", 8),
    "interface.out_octets": ("interface.out_bps", "bits_per_second", 8),
    "interface.hc_in_octets": ("interface.in_bps", "bits_per_second", 8),
    "interface.hc_out_octets": ("interface.out_bps", "bits_per_second", 8),
    "interface.in_packets": ("interface.in_packets_per_second", "packets_per_second", 1),
    "interface.out_packets": ("interface.out_packets_per_second", "packets_per_second", 1),
    "interface.in_errors": ("interface.in_errors_per_second", "errors_per_second", 1),
    "interface.out_errors": ("interface.out_errors_per_second", "errors_per_second", 1),
    "interface.in_discards": ("interface.in_discards_per_second", "discards_per_second", 1),
    "interface.out_discards": ("interface.out_discards_per_second", "discards_per_second", 1),
}


@dataclass(frozen=True)
class RateResult:
    value: float | None
    quality: str
    reason: str | None = None


def calculate_counter_rate(current: int, previous: int, elapsed_seconds: float, *,
                           bits: int = 64, rebooted: bool = False,
                           max_gap_seconds: int = 3600) -> RateResult:
    if rebooted:
        return RateResult(None, "reset", "Device uptime decreased.")
    if elapsed_seconds <= 0:
        return RateResult(None, "invalid", "Observation interval is not positive.")
    if elapsed_seconds > max_gap_seconds:
        return RateResult(None, "stale", "Observation gap exceeds the configured rate window.")
    if current < 0 or previous < 0:
        return RateResult(None, "invalid", "Counter values must be non-negative.")
    quality = "good"
    delta = current - previous
    if delta < 0:
        modulus = 1 << bits
        wrapped_delta = current + modulus - previous
        # A wrap is credible only when the previous sample was in the upper quartile.
        if previous >= modulus * 0.75 and 0 <= wrapped_delta < modulus * 0.5:
            delta, quality = wrapped_delta, "wrapped"
        else:
            return RateResult(None, "reset", "Counter decreased without a credible wrap.")
    rate = delta / elapsed_seconds
    if not math.isfinite(rate) or rate < 0:
        return RateResult(None, "invalid", "Calculated rate is invalid.")
    return RateResult(rate, quality)


def calculate_utilization(bits_per_second: float | None, speed_bps: int | None) -> RateResult:
    if bits_per_second is None or not speed_bps:
        return RateResult(None, "unsupported", "Interface speed is unknown.")
    value = round(bits_per_second / speed_bps * 100, 8)
    if value < 0 or not math.isfinite(value):
        return RateResult(None, "invalid", "Utilization is invalid.")
    if value > 100:
        return RateResult(value, "warning", "Utilization exceeds reported interface capacity.")
    return RateResult(value, "good")


def _norm(value) -> str:
    return str(value or "").strip().lower()


def score_inventory_match(candidate: SNMPDiscoveryCandidate, target: SNMPTarget, device: Device) -> dict:
    matching, conflicting, score = [], [], 0
    if target.device_id == device.id:
        return {"score": 100, "level": "exact", "matching_fields": ["explicit_target_link"],
                "conflicting_fields": [], "recommended_action": "link"}
    if candidate.matched_device_id == device.id:
        return {"score": 99, "level": "exact", "matching_fields": ["explicit_candidate_link"],
                "conflicting_fields": [], "recommended_action": "link"}
    if _norm(candidate.sys_name) and _norm(candidate.sys_name) == _norm(device.hostname):
        matching.append("sys_name"); score += 35
    elif candidate.sys_name and device.hostname:
        conflicting.append("hostname")
    if target.ip_address == device.ip_address:
        matching.append("management_ip"); score += 30
    elif device.ip_address:
        conflicting.append("ip_address")
    if _norm(candidate.vendor_guess) and _norm(candidate.vendor_guess) == _norm(device.brand):
        matching.append("vendor"); score += 15
    if _norm(candidate.device_type_guess) and _norm(candidate.device_type_guess) == _norm(device.device_type):
        matching.append("device_type"); score += 10
    if target.network_zone_id and target.network_zone_id == device.network_zone_id:
        matching.append("network_zone"); score += 10
    score = min(score, 95)
    level = "strong" if score >= 80 else "probable" if score >= 60 else "weak" if score >= 30 else "none"
    action = "enrich" if level in {"strong", "probable"} else "review" if level == "weak" else "ignore"
    if score >= 60 and len(conflicting) >= 2:
        action = "conflict"
    return {"score": score, "level": level, "matching_fields": matching,
            "conflicting_fields": conflicting, "recommended_action": action}


class SNMPOperationalService:
    def __init__(self, db):
        self.db = db

    def generate_matches(self, candidate, actor):
        target = self.db.get(SNMPTarget, candidate.target_id)
        if not target:
            raise HTTPException(409, "Candidate target is no longer available.")
        self.db.execute(delete(SNMPMatchCandidate).where(SNMPMatchCandidate.snmp_candidate_id == candidate.id))
        rows = []
        for device in self.db.scalars(select(Device).limit(1000)).all():
            result = score_inventory_match(candidate, target, device)
            if result["score"]:
                rows.append(SNMPMatchCandidate(
                    snmp_candidate_id=candidate.id, candidate_type="inventory_device",
                    candidate_device_id=device.id, match_score=result["score"],
                    match_level=result["level"], matching_fields=result["matching_fields"],
                    conflicting_fields=result["conflicting_fields"], evidence={"algorithm": "snmp-v1"},
                    recommended_action=result["recommended_action"],
                ))
        for discovered in self.db.scalars(select(DiscoveredDevice).limit(1000)).all():
            score, fields = 0, []
            if candidate.matched_discovery_id == discovered.id or target.discovered_device_id == discovered.id:
                score, fields = 100, ["explicit_discovery_link"]
            elif target.ip_address == discovered.ip_address and _norm(candidate.sys_name) == _norm(discovered.hostname):
                score, fields = 90, ["management_ip", "sys_name"]
            elif target.ip_address == discovered.ip_address:
                score, fields = 40, ["management_ip"]
            if score:
                rows.append(SNMPMatchCandidate(
                    snmp_candidate_id=candidate.id, candidate_type="discovered_device",
                    candidate_discovery_id=discovered.id, match_score=score,
                    match_level="exact" if score >= 95 else "strong" if score >= 80 else "weak",
                    matching_fields=fields, conflicting_fields=[], evidence={"algorithm": "snmp-v1"},
                    recommended_action="link" if score >= 80 else "review",
                ))
        self.db.add_all(rows)
        candidate.review_status = "conflict" if sum(r.match_score >= 80 for r in rows) > 1 else "matched"
        create_audit_log(self.db, actor.username, "SNMP_CANDIDATE_MATCHED", "SNMPDiscoveryCandidate", str(candidate.id), f"Generated {len(rows)} bounded inventory candidates.")
        self.db.commit()
        return sorted(rows, key=lambda row: row.match_score, reverse=True)

    def _fresh(self, candidate, expected_updated_at):
        if expected_updated_at and candidate.updated_at != expected_updated_at:
            raise HTTPException(409, "Candidate changed after review; recompute the onboarding plan.")
        if candidate.review_status == "approved":
            raise HTTPException(409, "Candidate has already been approved.")

    def link(self, candidate, device, actor, expected_updated_at=None):
        self._fresh(candidate, expected_updated_at)
        target = self.db.get(SNMPTarget, candidate.target_id)
        if target.device_id and target.device_id != device.id:
            raise HTTPException(409, "SNMP target is already linked to a different device.")
        link = self.db.scalar(select(SNMPDeviceLink).where(SNMPDeviceLink.target_id == target.id))
        if link and link.device_id != device.id:
            raise HTTPException(409, "Contradictory SNMP device linkage.")
        if not link:
            link = SNMPDeviceLink(target_id=target.id, device_id=device.id, linked_by=actor.id)
            self.db.add(link)
        link.profile_id, link.management_ip = candidate.profile_id, target.ip_address
        link.sys_object_id, link.last_seen_at = candidate.sys_object_id, datetime.now(timezone.utc)
        target.device_id = device.id
        candidate.matched_device_id, candidate.review_status = device.id, "approved"
        candidate.reviewed_by, candidate.reviewed_at = actor.id, datetime.now(timezone.utc)
        create_audit_log(self.db, actor.username, "SNMP_CANDIDATE_LINKED", "Device", str(device.id), "Linked reviewed SNMP candidate to inventory.")
        self.db.commit()
        manager.broadcast_from_thread({"type": "snmp_candidate_reviewed", "candidate_id": str(candidate.id), "device_id": str(device.id), "action": "link"})
        return link

    def onboard(self, candidate, payload, actor, expected_updated_at=None):
        self._fresh(candidate, expected_updated_at)
        # DeviceCreate deliberately enforces every mandatory inventory field.
        device_payload = DeviceCreate.model_validate(payload)
        device = create_device(self.db, device_payload, actor, commit=False)
        self.link(candidate, device, actor)
        create_audit_log(self.db, actor.username, "SNMP_DEVICE_ONBOARDED", "Device", str(device.id), "Created inventory device from administrator-reviewed SNMP plan.")
        self.db.commit()
        manager.broadcast_from_thread({"type": "snmp_device_onboarded", "device_id": str(device.id), "candidate_id": str(candidate.id)})
        return device

    def enrich(self, candidate, device, fields, actor, *, overwrite=False, expected_updated_at=None):
        self._fresh(candidate, expected_updated_at)
        allowed = {"hostname", "brand", "model", "device_type", "ip_address", "location"}
        changes = {}
        suggestions = {
            "hostname": candidate.sys_name, "brand": candidate.vendor_guess,
            "device_type": candidate.device_type_guess, "ip_address": self.db.get(SNMPTarget, candidate.target_id).ip_address,
            "location": candidate.sys_location,
        }
        for field in fields:
            if field not in allowed:
                raise HTTPException(400, f"Field '{field}' is not approved for SNMP enrichment.")
            value = suggestions.get(field)
            if value and (overwrite or not getattr(device, field, None)):
                changes[field] = {"before": getattr(device, field, None), "after": value}
                setattr(device, field, value)
        if not changes:
            raise HTTPException(400, "No approved enrichment changes were applicable.")
        create_audit_log(self.db, actor.username, "SNMP_DEVICE_ENRICHED", "Device", str(device.id), f"Applied reviewed fields: {', '.join(sorted(changes))}.")
        self.db.commit()
        self.link(candidate, device, actor)
        return {"device_id": device.id, "changes": changes}

    def review(self, candidate, status, actor):
        if status not in {"ignored", "rejected", "pending"}:
            raise HTTPException(400, "Unsupported candidate review status.")
        candidate.review_status = status
        candidate.reviewed_by = None if status == "pending" else actor.id
        candidate.reviewed_at = None if status == "pending" else datetime.now(timezone.utc)
        create_audit_log(self.db, actor.username, f"SNMP_CANDIDATE_{status.upper()}", "SNMPDiscoveryCandidate", str(candidate.id), f"Candidate review status changed to {status}.")
        self.db.commit()
        return candidate

    def sync_interfaces(self, target, run, records, *, complete=True, grace_polls=2, max_interfaces=1000):
        if len(records) > max_interfaces:
            raise HTTPException(413, "Interface inventory exceeds the configured maximum.")
        now, seen = datetime.now(timezone.utc), set()
        existing = {row.interface_index: row for row in self.db.scalars(select(SNMPInterface).where(SNMPInterface.target_id == target.id)).all()}
        change_count = 0
        for record in records:
            index = int(record["interface_index"]); seen.add(index)
            row = existing.get(index)
            created = row is None
            if not row:
                row = SNMPInterface(target_id=target.id, interface_index=index)
                self.db.add(row); self.db.flush()
            fields = ("name", "description", "alias", "interface_type", "mac_address", "admin_status",
                      "operational_status", "speed_bps", "duplex", "mtu", "last_change", "connector_present")
            before, after, changed = {}, {}, []
            if row.is_missing:
                before["is_missing"], after["is_missing"] = True, False; changed.append("is_missing")
            for field in fields:
                value = record.get(field)
                if value is not None and getattr(row, field) != value:
                    before[field], after[field] = getattr(row, field), value; changed.append(field)
                    setattr(row, field, value)
            if not created and "mac_address" in changed and before["mac_address"] and after["mac_address"]:
                self.db.add(SNMPStateChange(target_id=target.id, interface_id=row.id, poll_run_id=run.id, state_type="interface_identity_conflict", severity_hint="warning", previous_value=before["mac_address"], current_value=after["mac_address"], evidence={"interface_index": index}))
            row.is_missing, row.missed_polls, row.missing_since, row.last_seen_at = False, 0, None, now
            if created or changed:
                kind = "created" if created else "restored" if "is_missing" in changed else "updated"
                self.db.add(SNMPInterfaceChange(interface_id=row.id, poll_run_id=run.id, change_type=kind, changed_fields=changed, before_values=before, after_values=after))
                change_count += 1
        if complete:
            for index, row in existing.items():
                if index in seen:
                    continue
                row.missed_polls += 1
                if row.missed_polls >= grace_polls and not row.is_missing:
                    row.is_missing, row.missing_since = True, now
                    self.db.add(SNMPInterfaceChange(interface_id=row.id, poll_run_id=run.id, change_type="missing", changed_fields=["is_missing"], before_values={"is_missing": False}, after_values={"is_missing": True}))
                    change_count += 1
        create_audit_log(self.db, "system", "SNMP_INTERFACE_INVENTORY_SYNCED", "SNMPTarget", str(target.id), f"Synchronized {len(records)} interfaces with {change_count} changes.")
        self.db.commit()
        return {"seen": len(seen), "changes": change_count, "complete": complete}

    def persist_rates(self, target_id, run_id, observations, *, max_gap_seconds=3600, rebooted=False):
        created = []
        for observation in observations:
            key, index = observation["metric_key"], observation.get("interface_index")
            if key not in RATE_KEYS or index is None:
                continue
            previous = self.db.scalar(select(SNMPMetric).where(
                SNMPMetric.target_id == target_id, SNMPMetric.interface_index == index,
                SNMPMetric.metric_key == key, SNMPMetric.observed_at < observation["observed_at"],
            ).order_by(SNMPMetric.observed_at.desc()).limit(1))
            if not previous or previous.value_numeric is None:
                continue
            elapsed = (observation["observed_at"] - previous.observed_at).total_seconds()
            rate = calculate_counter_rate(int(observation["value"]), int(previous.value_numeric), elapsed,
                                          bits=COUNTER_BITS[key], rebooted=rebooted, max_gap_seconds=max_gap_seconds)
            rate_key, unit, multiplier = RATE_KEYS[key]
            metric = SNMPMetric(target_id=target_id, poll_run_id=run_id, metric_key=rate_key,
                                oid=observation["oid"], interface_index=index,
                                interface_name=observation.get("interface_name"),
                                value_numeric=Decimal(str(rate.value * multiplier)) if rate.value is not None else None,
                                value_text=None if rate.value is not None else rate.reason,
                                unit=unit, quality=rate.quality, quality_reason=rate.reason,
                                observed_at=observation["observed_at"])
            self.db.add(metric); created.append(metric)
        self.db.flush()
        return created

    def retention_preview(self, metric_days=90, poll_run_days=180):
        from app.models.snmp import SNMPAlertEvent
        now = datetime.now(timezone.utc)
        metric_cutoff, run_cutoff = now - timedelta(days=metric_days), now - timedelta(days=poll_run_days)
        protected_runs = select(SNMPAlertEvent.poll_run_id).where(SNMPAlertEvent.is_open.is_(True), SNMPAlertEvent.poll_run_id.isnot(None))
        eligible_metrics = SNMPMetric.observed_at < metric_cutoff, SNMPMetric.poll_run_id.not_in(protected_runs)
        metrics = self.db.scalar(select(func.count()).select_from(SNMPMetric).where(*eligible_metrics)) or 0
        protected = self.db.scalar(select(func.count()).select_from(SNMPMetric).where(
            SNMPMetric.observed_at < metric_cutoff, SNMPMetric.poll_run_id.in_(protected_runs))) or 0
        runs = self.db.scalar(select(func.count()).select_from(SNMPPollRun).where(SNMPPollRun.completed_at < run_cutoff, ~SNMPPollRun.metrics.any())) or 0
        return {"metric_cutoff": metric_cutoff, "poll_run_cutoff": run_cutoff, "expired_metrics": metrics, "protected_alert_metrics": protected, "expired_empty_poll_runs": runs}

    def cleanup(self, actor, metric_days=90, poll_run_days=180):
        from app.models.snmp import SNMPAlertEvent
        preview = self.retention_preview(metric_days, poll_run_days)
        protected_runs = select(SNMPAlertEvent.poll_run_id).where(SNMPAlertEvent.is_open.is_(True), SNMPAlertEvent.poll_run_id.isnot(None))
        deleted_metrics = self.db.execute(delete(SNMPMetric).where(
            SNMPMetric.observed_at < preview["metric_cutoff"], SNMPMetric.poll_run_id.not_in(protected_runs))).rowcount
        deleted_runs = self.db.execute(delete(SNMPPollRun).where(SNMPPollRun.completed_at < preview["poll_run_cutoff"], ~SNMPPollRun.metrics.any())).rowcount
        create_audit_log(self.db, actor.username, "SNMP_RETENTION_CLEANUP", "SNMPMetric", None, f"Removed {deleted_metrics} expired metrics and {deleted_runs} empty poll runs.")
        self.db.commit()
        return {**preview, "deleted_metrics": deleted_metrics, "deleted_poll_runs": deleted_runs}
