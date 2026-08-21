"""Manual, bounded SNMP polling lifecycle. No scheduler is registered."""
import uuid
from datetime import datetime, timezone
from fnmatch import fnmatchcase
from time import monotonic

from fastapi import HTTPException
from sqlalchemy import select

from app.models.snmp import (
    SNMPCredential, SNMPDeviceProfile, SNMPDiscoveryCandidate, SNMPInterface,
    SNMPMetric, SNMPOIDDefinition, SNMPPollRun, SNMPStateChange, SNMPTarget,
)
from app.services.audit_service import create_audit_log
from app.services.settings_service import read_discovery
from app.core.config import settings
from app.services.snmp_client_service import (
    INTERFACE_OIDS, SYSTEM_OIDS, SNMPClientError, SNMPValue, SecureSNMPClient,
)
from app.services.snmp_notification_service import notify_snmp
from app.services.snmp_operational_service import SNMPOperationalService
from app.services.snmp_runtime import snmp_operation_lock
from app.services.circuit_breaker import circuit_breaker, CircuitBreakerConfig, get_circuit_breaker, CircuitBreakerError
from app.websocket.connection_manager import manager

TRANSITIONS = {
    "pending": {"running", "cancelled"},
    "running": {"completed", "partial", "failed", "cancelled"},
    "completed": set(), "partial": set(), "failed": set(), "cancelled": set(),
}


class SNMPPollingService:
    def __init__(self, db, client_factory=SecureSNMPClient):
        self.db = db
        self.client_factory = client_factory

    @staticmethod
    def transition(run, target):
        if target not in TRANSITIONS.get(run.status, set()):
            raise HTTPException(409, f"Cannot transition SNMP poll from {run.status} to {target}.")
        run.status = target

    def create_poll_run(self, target_id, actor, poll_type="system", trigger_type="manual"):
        active = self.db.scalar(select(SNMPPollRun).where(
            SNMPPollRun.target_id == target_id, SNMPPollRun.status.in_(("pending", "running"))
        ))
        if active:
            raise HTTPException(409, "Target already has an active SNMP poll.")
        run = SNMPPollRun(
            id=uuid.uuid4(), target_id=target_id, triggered_by=actor.id,
            trigger_type=trigger_type, poll_type=poll_type, status="pending",
        )
        self.db.add(run)
        create_audit_log(self.db, actor.username, "SNMP_POLL_STARTED", "SNMPPollRun", str(run.id), f"Created manual {poll_type} SNMP poll.")
        self.db.commit()
        self.db.refresh(run)
        return run

    def _client(self, target, credential):
        discovery = read_discovery(self.db)
        networks = discovery["authorized_cidr_ranges"]
        ignored = discovery.get("ignore_ranges", "")
        networks = [x.strip() for x in networks.split(",") if x.strip()] if isinstance(networks, str) else networks
        ignored = [x.strip() for x in ignored.split(",") if x.strip()] if isinstance(ignored, str) else ignored
        return self.client_factory(target, credential, authorized_networks=networks, ignored_networks=ignored)

    def _cancelled(self, run):
        self.db.refresh(run)
        return run.status == "cancelled"

    def _persist(self, run, target, metric_key, value: SNMPValue, *, interface_index=None, interface_name=None, unit=None, observed_at=None):
        self.db.add(SNMPMetric(
            target_id=target.id, poll_run_id=run.id, metric_key=metric_key,
            oid=value.oid, interface_index=interface_index, interface_name=interface_name,
            value_numeric=value.value_numeric, value_text=value.value_text, unit=unit,
            quality=value.quality, observed_at=observed_at or datetime.now(timezone.utc),
        ))

    def _resolve_profile(self, identity):
        sys_oid = identity.get("system.object_id")
        sys_descr = identity.get("system.description")
        oid_text = sys_oid.value_text if sys_oid else ""
        descr_text = sys_descr.value_text if sys_descr else ""
        profiles = self.db.scalars(select(SNMPDeviceProfile).where(SNMPDeviceProfile.enabled.is_(True)).order_by(SNMPDeviceProfile.priority)).all()
        for profile in profiles:
            oid_match = not profile.sys_object_id_pattern or fnmatchcase(oid_text or "", profile.sys_object_id_pattern)
            descr_match = not profile.sys_descr_pattern or fnmatchcase((descr_text or "").lower(), profile.sys_descr_pattern.lower())
            if oid_match and descr_match:
                return profile, 90 if profile.sys_object_id_pattern and profile.sys_descr_pattern else 70
        return None, 0

    def _candidate(self, target, identity, profile, confidence, actor):
        candidate = self.db.scalar(select(SNMPDiscoveryCandidate).where(SNMPDiscoveryCandidate.target_id == target.id))
        created = candidate is None
        if not candidate:
            candidate = SNMPDiscoveryCandidate(target_id=target.id, review_status="pending")
            self.db.add(candidate)
        candidate.sys_name = identity.get("system.name").value_text if identity.get("system.name") else None
        candidate.sys_descr = identity.get("system.description").value_text if identity.get("system.description") else None
        candidate.sys_object_id = identity.get("system.object_id").value_text if identity.get("system.object_id") else None
        candidate.sys_location = identity.get("system.location").value_text if identity.get("system.location") else None
        candidate.sys_contact = identity.get("system.contact").value_text if identity.get("system.contact") else None
        candidate.profile_id = profile.id if profile else None
        candidate.vendor_guess = profile.vendor if profile else None
        candidate.device_type_guess = profile.device_type if profile else "generic_snmp_device"
        candidate.confidence_score = confidence
        candidate.evidence = {"profile_pattern_match": bool(profile), "target_id": str(target.id)}
        candidate.matched_device_id = target.device_id
        candidate.matched_discovery_id = target.discovered_device_id
        create_audit_log(self.db, actor.username, "SNMP_CANDIDATE_CREATED" if created else "SNMP_CANDIDATE_UPDATED", "SNMPDiscoveryCandidate", str(candidate.id), "Created or updated reviewed SNMP discovery candidate.")
        manager.broadcast_from_thread({"type": "snmp_candidate_updated", "target_id": str(target.id), "candidate_id": str(candidate.id)})

    def _system(self, client, run, target, actor):
        identity = client.get_system_identity(True)
        run.requested_oids = len(identity)
        previous = {}
        for key in ("system.uptime", "system.name", "system.location", "system.object_id"):
            previous[key] = self.db.scalar(select(SNMPMetric).where(
                SNMPMetric.target_id == target.id, SNMPMetric.metric_key == key
            ).order_by(SNMPMetric.observed_at.desc()).limit(1))
        for key, value in identity.items():
            self._persist(run, target, key, value, unit="ticks" if key == "system.uptime" else None)
        current_uptime = identity.get("system.uptime")
        old_uptime = previous.get("system.uptime")
        if current_uptime and old_uptime and current_uptime.value_numeric is not None and old_uptime.value_numeric is not None and current_uptime.value_numeric < old_uptime.value_numeric:
            self.db.add(SNMPStateChange(
                target_id=target.id, poll_run_id=run.id, state_type="device_reboot",
                severity_hint="warning", previous_value=str(old_uptime.value_numeric),
                current_value=str(current_uptime.value_numeric), evidence={"metric": "system.uptime"},
            ))
            manager.broadcast_from_thread({"type": "snmp_device_reboot_detected", "target_id": str(target.id), "poll_run_id": str(run.id)})
        for key, state_type in (("system.name", "sys_name_changed"), ("system.location", "sys_location_changed"), ("system.object_id", "sys_object_id_changed")):
            current, old = identity.get(key), previous.get(key)
            if current and old and current.value_text and old.value_text and current.value_text != old.value_text:
                self.db.add(SNMPStateChange(
                    target_id=target.id, poll_run_id=run.id, state_type=state_type,
                    severity_hint="warning" if key == "system.object_id" else "info",
                    previous_value=old.value_text[:500], current_value=current.value_text[:500],
                    evidence={"metric": key},
                ))
        run.successful_oids = sum(value.quality in {"good", "warning", "truncated"} for value in identity.values())
        run.failed_oids = run.requested_oids - run.successful_oids
        profile, confidence = self._resolve_profile(identity)
        target.detected_profile_id = profile.id if profile else None
        target.detected_sys_object_id = identity.get("system.object_id").value_text if identity.get("system.object_id") else None
        self._candidate(target, identity, profile, confidence, actor)
        return identity

    def _availability(self, client, run, target):
        values = client.get_many([SYSTEM_OIDS["system.uptime"], SYSTEM_OIDS["system.name"]])
        run.requested_oids = 2
        for key, value in zip(("system.uptime", "system.name"), values):
            self._persist(run, target, key, value, unit="ticks" if key == "system.uptime" else None)
        run.successful_oids = sum(value.quality == "good" for value in values)
        run.failed_oids = 2 - run.successful_oids
        return values

    def _interfaces(self, client, run, target):
        max_interfaces = min(settings.snmp_maximum_interfaces, getattr(target.polling_configuration, "max_interfaces", 256))
        previews = client.get_interfaces_preview(max_interfaces=max_interfaces, cancelled=lambda: self._cancelled(run))
        by_index = {}
        requested = successful = 0
        for key, result in previews.items():
            requested += len(result.items)
            root = INTERFACE_OIDS[key]
            for value in result.items:
                try: index = int(value.oid.removeprefix(root + ".").split(".")[0])
                except ValueError: continue
                by_index.setdefault(index, {})[key] = value
                successful += value.quality in {"good", "warning", "truncated"}
        records = []
        for index, fields in list(by_index.items())[:max_interfaces]:
            name_value = fields.get("interface.name") or fields.get("interface.description")
            name = name_value.value_text if name_value else None
            for key, value in fields.items():
                self._persist(run, target, key, value, interface_index=index, interface_name=name)
            speed = getattr(fields.get("interface.high_speed"), "value_numeric", None)
            speed = int(speed * 1_000_000) if speed else getattr(fields.get("interface.speed"), "value_numeric", None)
            records.append({
                "interface_index": index, "name": name,
                "description": getattr(fields.get("interface.description"), "value_text", None),
                "alias": getattr(fields.get("interface.alias"), "value_text", None),
                "interface_type": str(getattr(fields.get("interface.type"), "value_numeric", "") or "") or None,
                "mac_address": getattr(fields.get("interface.mac"), "value_text", None),
                "mtu": getattr(fields.get("interface.mtu"), "value_numeric", None),
                "speed_bps": speed,
                "admin_status": str(getattr(fields.get("interface.admin_status"), "value_numeric", "") or "") or None,
                "operational_status": str(getattr(fields.get("interface.oper_status"), "value_numeric", "") or "") or None,
                "duplex": {2: "half", 3: "full"}.get(getattr(fields.get("interface.duplex"), "value_numeric", None), "unknown" if fields.get("interface.duplex") else None),
                "last_change": getattr(fields.get("interface.last_change"), "value_numeric", None),
            })
        complete = all(not result.truncated for result in previews.values())
        SNMPOperationalService(self.db).sync_interfaces(
            target, run, records, complete=complete,
            grace_polls=settings.snmp_interface_missing_grace_polls,
            max_interfaces=settings.snmp_maximum_interfaces,
        )
        run.requested_oids, run.successful_oids = requested, int(successful)
        run.failed_oids = requested - run.successful_oids
        return by_index

    def _custom(self, client, run, target):
        profile_id = getattr(target.polling_configuration, "profile_id", None)
        definitions = self.db.scalars(select(SNMPOIDDefinition).where(
            SNMPOIDDefinition.enabled.is_(True), SNMPOIDDefinition.profile_id == profile_id,
        ).limit(settings.snmp_maximum_oids_per_request)).all()
        if not definitions:
            raise SNMPClientError("configuration_error", "Target profile has no approved OIDs.")
        scalar = [d for d in definitions if d.collection_type == "scalar"]
        values = client.get_many([definition.oid for definition in scalar]) if scalar else []
        run.requested_oids = len(values)
        for definition, value in zip(scalar, values):
            self._persist(run, target, definition.metric_key, value, unit=definition.unit)
        observations = []
        for definition in (d for d in definitions if d.collection_type != "scalar"):
            result = client.bulk_walk(
                definition.oid, max_rows=min(settings.snmp_maximum_interfaces, 1000),
                max_duration=30, max_repetitions=20, cancelled=lambda: self._cancelled(run),
            )
            run.requested_oids += len(result.items)
            values.extend(result.items)
            observed_at = datetime.now(timezone.utc)
            for value in result.items:
                try:
                    index = int(value.oid.removeprefix(definition.oid + ".").split(".")[0])
                except ValueError:
                    continue
                self._persist(run, target, definition.metric_key, value, unit=definition.unit,
                              interface_index=index, observed_at=observed_at)
                if value.value_numeric is not None:
                    observations.append({"metric_key": definition.metric_key, "interface_index": index,
                                         "value": int(value.value_numeric), "oid": value.oid,
                                         "observed_at": observed_at})
        SNMPOperationalService(self.db).persist_rates(
            target.id, run.id, observations, max_gap_seconds=settings.snmp_rate_max_gap_seconds,
        )
        run.successful_oids = sum(value.quality in {"good", "warning", "truncated"} for value in values)
        run.failed_oids = run.requested_oids - run.successful_oids
        return values

    def execute_poll(self, run_id, actor):
        run = self.db.get(SNMPPollRun, run_id)
        if not run: raise HTTPException(404, "SNMP poll run was not found.")
        target = self.db.get(SNMPTarget, run.target_id)
        credential = self.db.get(SNMPCredential, target.credential_id) if target else None
        if not target or not credential: raise HTTPException(400, "SNMP target or credential is unavailable.")
        started = monotonic()
        client = None
        self.transition(run, "running")
        self.db.commit()
        manager.broadcast_from_thread({"type": "snmp_poll_started", "poll_run_id": str(run.id), "target_id": str(target.id), "poll_type": run.poll_type})
        try:
            with snmp_operation_lock(target.id, credential.id):
                client = self._client(target, credential)
                if run.poll_type == "availability": result = self._availability(client, run, target)
                elif run.poll_type == "system": result = self._system(client, run, target, actor)
                elif run.poll_type == "interfaces_preview": result = self._interfaces(client, run, target)
                elif run.poll_type == "custom_profile": result = self._custom(client, run, target)
                else: raise SNMPClientError("configuration_error", "Unsupported SNMP poll type.")
                if self._cancelled(run):
                    return self._finalize(run, target, actor, "cancelled", started)
            status = "partial" if run.failed_oids else "completed"
            return self._finalize(run, target, actor, status, started)
        except SNMPClientError as error:
            return self._finalize(run, target, actor, "cancelled" if error.category == "cancelled" else "failed", started, error)
        finally:
            if client: client.close()

    def execute_collection(self, run_id, actor, groups):
        """Execute an explicitly approved, bounded collection plan in one run."""
        run = self.db.get(SNMPPollRun, run_id)
        if not run:
            raise HTTPException(404, "SNMP poll run was not found.")
        if len(groups) == 1:
            mapping = {
                "availability": "availability", "system": "system",
                "interface_inventory": "interfaces_preview",
                "interface_performance": "custom_profile",
                "device_performance": "custom_profile",
                "all_profile_metrics": "custom_profile",
            }
            run.poll_type = mapping[groups[0]]
            self.db.commit()
            return self.execute_poll(run.id, actor)
        target = self.db.get(SNMPTarget, run.target_id)
        credential = self.db.get(SNMPCredential, target.credential_id) if target else None
        if not target or not credential:
            raise HTTPException(400, "SNMP target or credential is unavailable.")
        started = monotonic()
        client = None
        self.transition(run, "running")
        self.db.commit()
        manager.broadcast_from_thread({"type": "snmp_collection_started", "poll_run_id": str(run.id), "target_id": str(target.id), "groups": groups})
        try:
            with snmp_operation_lock(target.id, credential.id):
                client = self._client(target, credential)
                requested = successful = failed = 0
                profile_groups = {"interface_performance", "device_performance", "all_profile_metrics"}
                execution_groups = [g for g in groups if g not in profile_groups]
                if profile_groups.intersection(groups):
                    execution_groups.append("all_profile_metrics")
                for group in execution_groups:
                    if group == "availability": self._availability(client, run, target)
                    elif group == "system": self._system(client, run, target, actor)
                    elif group == "interface_inventory": self._interfaces(client, run, target)
                    else: self._custom(client, run, target)
                    requested += run.requested_oids; successful += run.successful_oids; failed += run.failed_oids
                    manager.broadcast_from_thread({"type": "snmp_collection_progress", "poll_run_id": str(run.id), "group": group, "successful": run.successful_oids, "failed": run.failed_oids})
                    if self._cancelled(run):
                        return self._finalize(run, target, actor, "cancelled", started)
                run.requested_oids, run.successful_oids, run.failed_oids = requested, successful, failed
            return self._finalize(run, target, actor, "partial" if failed else "completed", started)
        except SNMPClientError as error:
            return self._finalize(run, target, actor, "cancelled" if error.category == "cancelled" else "failed", started, error)
        finally:
            if client: client.close()

    def _finalize(self, run, target, actor, status, started, error=None):
        if run.status == "running": self.transition(run, status)
        run.completed_at = datetime.now(timezone.utc)
        run.duration_ms = round((monotonic() - started) * 1000)
        if error:
            run.error_category, run.error_summary = error.category, error.safe_message
        if status in {"completed", "partial"}:
            target.last_successful_poll_at = run.completed_at
            target.last_response_time_ms = run.duration_ms
            target.consecutive_failures = 0
        elif status == "failed":
            target.last_failed_poll_at = run.completed_at
            target.consecutive_failures += 1
        action = {"completed": "SNMP_POLL_COMPLETED", "partial": "SNMP_POLL_PARTIAL", "failed": "SNMP_POLL_FAILED", "cancelled": "SNMP_POLL_CANCELLED"}[status]
        create_audit_log(self.db, actor.username, action, "SNMPPollRun", str(run.id), f"SNMP poll ended with status {status}.")
        event = {"completed": "snmp_poll_completed", "partial": "snmp_poll_partial", "failed": "snmp_poll_failed", "cancelled": "snmp_poll_cancelled"}[status]
        manager.broadcast_from_thread({"type": event, "poll_run_id": str(run.id), "target_id": str(target.id), "status": status, "requested": run.requested_oids, "successful": run.successful_oids, "failed": run.failed_oids})
        if status in {"partial", "failed"}:
            notify_snmp(self.db, f"HIOP SNMP poll {status}", f"Poll {run.id} for target {target.id} ended {status}.")
        self.db.commit(); self.db.refresh(run)
        if getattr(target.polling_configuration, "alerting_enabled", False):
            from app.services.snmp_alert_service import SNMPAlertService
            SNMPAlertService(self.db).evaluate_target(target, run, actor.username)
        return run

    def cancel_poll(self, run, actor):
        if run.status not in {"pending", "running"}:
            raise HTTPException(409, "Only pending or running SNMP polls may be cancelled.")
        run.status = "cancelled"
        run.completed_at = datetime.now(timezone.utc)
        create_audit_log(self.db, actor.username, "SNMP_POLL_CANCELLED", "SNMPPollRun", str(run.id), "Cancelled SNMP poll.")
        manager.broadcast_from_thread({"type": "snmp_poll_cancelled", "poll_run_id": str(run.id), "target_id": str(run.target_id)})
        self.db.commit(); self.db.refresh(run)
        return run
