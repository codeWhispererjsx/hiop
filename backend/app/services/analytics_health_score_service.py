"""Explainable weighted health scores; missing components reduce coverage."""
from datetime import datetime, timedelta, timezone

from app.core.config import settings

COMPONENTS = ("availability", "performance", "reliability", "alert", "capacity", "topology", "data_quality")


class AnalyticsHealthScoreService:
    @staticmethod
    def calculate(configuration, components):
        weights = {name: float(getattr(configuration, f"{name}_weight")) for name in COMPONENTS}
        present = {name: max(0.0, min(100.0, float(value))) for name, value in components.items() if name in weights and value is not None}
        total_weight = sum(weights[name] for name in present)
        if not present or total_weight <= 0:
            return {"score": 0, "status": "unknown", "coverage_percent": 0, "contributing_factors": [{"factor": "missing_data", "effect": "Health is unknown; no supported components were available."}]}
        score = sum(present[name] * weights[name] for name in present) / total_weight
        coverage = total_weight / sum(weights.values()) * 100
        if coverage < configuration.minimum_data_coverage:
            status = "unknown"
        elif score >= configuration.excellent_threshold: status = "excellent"
        elif score >= configuration.healthy_threshold: status = "healthy"
        elif score >= configuration.warning_threshold: status = "warning"
        elif score >= configuration.degraded_threshold: status = "degraded"
        else: status = "critical"
        factors = [{"factor": name, "score": value, "normalized_weight": weights[name] / total_weight * 100} for name, value in present.items()]
        missing = [name for name in COMPONENTS if name not in present]
        if missing: factors.append({"factor": "missing_components", "components": missing, "effect": "Reduced data coverage; missing data was not treated as failure."})
        return {"score": round(score, 2), "status": status, "coverage_percent": round(coverage, 2), "contributing_factors": factors}

    @staticmethod
    def valid_until(calculated_at=None):
        return (calculated_at or datetime.now(timezone.utc)) + timedelta(minutes=settings.analytics_health_score_valid_minutes)
