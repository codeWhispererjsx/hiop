"""Threshold-based capacity assessments without forecasting."""
from app.services.analytics_aggregation_service import percentile


class AnalyticsCapacityService:
    @staticmethod
    def assess(policy, samples, period_seconds):
        values = [float(value) for value in samples if value is not None]
        if len(values) < policy.minimum_samples:
            return {"threshold_status": "unknown", "sample_count": len(values), "data_quality": "insufficient", "current_value": values[-1] if values else None, "average_value": None, "peak_value": max(values) if values else None, "percentile_95": percentile(values, .95), "threshold_breach_duration_seconds": 0, "explanation": {"reason": "minimum_samples_not_met"}}
        critical = [value for value in values if value >= policy.critical_threshold]
        warning = [value for value in values if value >= policy.warning_threshold]
        approximate_interval = period_seconds / max(1, len(values))
        breach = len(critical or warning) * approximate_interval
        status = "critical" if critical and breach >= policy.minimum_duration_seconds else "warning" if warning and breach >= policy.minimum_duration_seconds else "normal"
        return {"threshold_status": status, "sample_count": len(values), "data_quality": "good", "current_value": values[-1], "average_value": sum(values) / len(values), "peak_value": max(values), "percentile_95": percentile(values, .95), "threshold_breach_duration_seconds": int(breach), "explanation": {"warning_threshold": policy.warning_threshold, "critical_threshold": policy.critical_threshold, "approximate_sample_interval_seconds": approximate_interval}}
