"""Deterministic anomaly scoring and lifecycle management."""
from __future__ import annotations

import math
from datetime import datetime, timezone

from sqlalchemy import select

from app.models.analytics import AnalyticsAnomaly, AnalyticsAnomalyRule, AnalyticsBaseline


class AnalyticsAnomalyService:
    METHODS = {"z_score", "modified_z_score", "iqr", "percentile", "change_point", "trend_break", "forecast_deviation", "missing_data", "stale_data"}

    def __init__(self, db):
        self.db = db

    @staticmethod
    def evaluate(value: float, baseline: AnalyticsBaseline, method: str, sensitivity: float = 3.0) -> dict:
        if method not in AnalyticsAnomalyService.METHODS:
            raise ValueError("Unsupported deterministic detection method.")
        expected = baseline.median_value
        if method == "z_score":
            score = abs(value - baseline.mean_value) / max(baseline.standard_deviation, 1e-9)
        elif method == "modified_z_score":
            score = .6745 * abs(value - baseline.median_value) / max(baseline.median_absolute_deviation, 1e-9)
        else:
            span = max(baseline.expected_upper_bound - baseline.expected_lower_bound, 1e-9)
            score = max(0.0, (baseline.expected_lower_bound - value) / span, (value - baseline.expected_upper_bound) / span) * sensitivity
        anomalous = score >= sensitivity or value < baseline.expected_lower_bound or value > baseline.expected_upper_bound
        normalized = min(100.0, score / max(sensitivity, .1) * 60)
        return {
            "anomalous": anomalous, "score": round(normalized, 2),
            "type": "spike" if value > baseline.expected_upper_bound else "drop",
            "expected": expected, "deviation": value - expected,
            "evidence": {"method": method, "threshold": sensitivity, "sample_count": baseline.sample_count,
                "baseline_bounds": [baseline.expected_lower_bound, baseline.expected_upper_bound],
                "limitations": ["Statistical deviation indicates unusual behavior, not a confirmed cause."]},
        }

    def detect(self, rule: AnalyticsAnomalyRule, baseline: AnalyticsBaseline, value: float, source_aggregate_id=None):
        result = self.evaluate(value, baseline, rule.detection_method, rule.sensitivity)
        active = self.db.scalar(select(AnalyticsAnomaly).where(
            AnalyticsAnomaly.entity_type == baseline.entity_type, AnalyticsAnomaly.entity_id == baseline.entity_id,
            AnalyticsAnomaly.metric_key == baseline.metric_key, AnalyticsAnomaly.rule_id == rule.id,
            AnalyticsAnomaly.anomaly_type == result["type"], AnalyticsAnomaly.status.in_(("open", "acknowledged", "suppressed")),
        ))
        now = datetime.now(timezone.utc)
        if not result["anomalous"]:
            if active:
                active.recovery_count += 1
                if active.recovery_count >= rule.recovery_occurrences:
                    active.status = "resolved"; active.resolved_at = now
                    active.resolution_reason = "Metric returned inside the accepted baseline after required recovery observations."
            return active
        confidence = min(baseline.confidence_score, 100)
        if confidence < rule.minimum_confidence:
            return None
        severity = "critical" if result["score"] >= rule.critical_score else "high" if result["score"] >= rule.warning_score else "warning"
        if active:
            active.occurrence_count += 1; active.last_detected_at = now; active.observed_value = value
            active.anomaly_score = result["score"]; active.evidence = result["evidence"]; active.recovery_count = 0
            return active
        anomaly = AnalyticsAnomaly(entity_type=baseline.entity_type, entity_id=baseline.entity_id, metric_key=baseline.metric_key,
            baseline_id=baseline.id, rule_id=rule.id, anomaly_type=result["type"], severity=severity, observed_value=value,
            expected_value=result["expected"], expected_lower_bound=baseline.expected_lower_bound, expected_upper_bound=baseline.expected_upper_bound,
            deviation_value=result["deviation"], deviation_percent=(result["deviation"] / expected * 100 if (expected := result["expected"]) else None),
            anomaly_score=result["score"], confidence_score=confidence, detection_method=rule.detection_method,
            evidence=result["evidence"], first_detected_at=now, last_detected_at=now, source_aggregate_id=source_aggregate_id)
        self.db.add(anomaly); self.db.flush(); return anomaly

    @staticmethod
    def transition(anomaly: AnalyticsAnomaly, status: str, actor_id=None, reason: str | None = None):
        allowed = {"acknowledged", "resolved", "ignored", "suppressed"}
        if status not in allowed or anomaly.status in {"resolved", "ignored"}:
            raise ValueError("Invalid anomaly lifecycle transition.")
        now = datetime.now(timezone.utc); anomaly.status = status
        if status == "acknowledged": anomaly.acknowledged_by=actor_id; anomaly.acknowledged_at=now
        if status == "resolved": anomaly.resolved_at=now; anomaly.resolution_reason=reason or "Resolved after administrator review."
        return anomaly
