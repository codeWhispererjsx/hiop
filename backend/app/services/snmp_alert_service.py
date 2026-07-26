"""Bounded SNMP rule evaluation with deduplication, recovery, and maintenance suppression."""
from datetime import datetime, timezone

from sqlalchemy import select

from app.models.snmp import (
    SNMPAlertEvent, SNMPAlertRule, SNMPMetric, SNMPPollingConfiguration,
)
from app.services.audit_service import create_audit_log
from app.websocket.connection_manager import manager

OPS = {
    "greater_than": lambda value, threshold: value > threshold,
    "greater_than_or_equal": lambda value, threshold: value >= threshold,
    "less_than": lambda value, threshold: value < threshold,
    "less_than_or_equal": lambda value, threshold: value <= threshold,
    "equal": lambda value, threshold: value == threshold,
    "not_equal": lambda value, threshold: value != threshold,
}


class SNMPAlertService:
    def __init__(self, db):
        self.db = db

    def applicable_rules(self, target):
        return self.db.scalars(select(SNMPAlertRule).where(
            SNMPAlertRule.enabled.is_(True),
            (SNMPAlertRule.target_id.is_(None)) | (SNMPAlertRule.target_id == target.id),
            (SNMPAlertRule.profile_id.is_(None)) | (SNMPAlertRule.profile_id == target.detected_profile_id),
        )).all()

    def _samples(self, target_id, rule):
        if not rule.metric_key:
            return []
        query = select(SNMPMetric).where(
            SNMPMetric.target_id == target_id,
            SNMPMetric.metric_key == rule.metric_key,
        )
        if rule.interface_id:
            from app.models.snmp import SNMPInterface
            interface = self.db.get(SNMPInterface, rule.interface_id)
            if not interface or interface.target_id != target_id:
                return []
            query = query.where(SNMPMetric.interface_index == interface.interface_index)
        return list(self.db.scalars(query.order_by(SNMPMetric.observed_at.desc()).limit(rule.evaluation_window)).all())

    def _breached(self, rule, samples):
        usable = [float(row.value_numeric) for row in samples if row.value_numeric is not None and row.quality not in {"invalid", "missing", "unsupported"}]
        if rule.comparison_operator == "missing":
            return not samples
        if rule.comparison_operator == "stale":
            return not samples or samples[0].quality == "stale"
        if len(usable) < rule.minimum_samples:
            return False
        threshold = rule.critical_threshold if rule.critical_threshold is not None else rule.warning_threshold
        return sum(OPS[rule.comparison_operator](value, threshold) for value in usable[:rule.consecutive_breaches]) >= rule.consecutive_breaches

    def evaluate_target(self, target, poll_run=None, actor="scheduler"):
        config = self.db.scalar(select(SNMPPollingConfiguration).where(SNMPPollingConfiguration.target_id == target.id))
        if not config or not config.alerting_enabled:
            return {"evaluated": 0, "opened": 0, "updated": 0, "resolved": 0, "suppressed": 0}
        now = datetime.now(timezone.utc)
        maintenance = config.maintenance_mode and (not config.maintenance_ends_at or config.maintenance_ends_at > now)
        result = {"evaluated": 0, "opened": 0, "updated": 0, "resolved": 0, "suppressed": 0}
        for rule in self.applicable_rules(target):
            result["evaluated"] += 1
            samples = self._samples(target.id, rule)
            breached = self._breached(rule, samples)
            event = self.db.scalar(select(SNMPAlertEvent).where(
                SNMPAlertEvent.rule_id == rule.id, SNMPAlertEvent.target_id == target.id,
                SNMPAlertEvent.interface_id == rule.interface_id, SNMPAlertEvent.is_open.is_(True),
            ))
            evidence = {
                "metric_key": rule.metric_key, "operator": rule.comparison_operator,
                "threshold": rule.critical_threshold if rule.critical_threshold is not None else rule.warning_threshold,
                "observed_value": float(samples[0].value_numeric) if samples and samples[0].value_numeric is not None else None,
                "sample_time": samples[0].observed_at.isoformat() if samples else None,
                "maintenance": maintenance, "poll_run_id": str(poll_run.id) if poll_run else None,
            }
            if breached and maintenance and rule.suppress_during_maintenance:
                result["suppressed"] += 1
                continue
            if breached:
                if event:
                    event.occurrence_count += 1
                    event.breach_count += 1
                    event.recovery_count = 0
                    event.last_seen_at = now
                    event.evidence = evidence
                    event.flapping = event.occurrence_count >= 6
                    result["updated"] += 1
                else:
                    event = SNMPAlertEvent(
                        rule_id=rule.id, target_id=target.id, interface_id=rule.interface_id,
                        poll_run_id=poll_run.id if poll_run else None, metric_key=rule.metric_key or "",
                        severity=rule.severity, evidence=evidence,
                    )
                    self.db.add(event)
                    result["opened"] += 1
            elif event:
                event.recovery_count += 1
                if event.recovery_count >= rule.recovery_samples:
                    event.is_open = False
                    event.resolved_at = now
                    event.recovery_evidence = evidence
                    result["resolved"] += 1
        create_audit_log(self.db, actor, "SNMP_ALERTS_EVALUATED", "SNMPTarget", str(target.id), f"Evaluated {result['evaluated']} approved rules; opened {result['opened']}, resolved {result['resolved']}.")
        self.db.commit()
        if result["opened"] or result["resolved"]:
            manager.broadcast_from_thread({"type": "snmp_alerts_updated", "target_id": str(target.id), **result})
        return result

    def preview(self, rule):
        targets = []
        from app.models.snmp import SNMPTarget
        query = select(SNMPTarget).where(SNMPTarget.enabled.is_(True))
        if rule.target_id:
            query = query.where(SNMPTarget.id == rule.target_id)
        for target in self.db.scalars(query.limit(500)).all():
            samples = self._samples(target.id, rule)
            targets.append({"target_id": str(target.id), "would_trigger": self._breached(rule, samples), "sample_count": len(samples)})
        return {"items": targets, "targets_affected": len(targets), "estimated_alert_count": sum(item["would_trigger"] for item in targets), "truncated": len(targets) == 500}
