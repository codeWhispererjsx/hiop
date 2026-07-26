"""Reliability calculations with explicit insufficient-evidence behavior."""


class AnalyticsReliabilityService:
    @staticmethod
    def calculate(period_seconds, outage_durations, failure_count=None, acknowledgement_seconds=(), detection_seconds=()):
        outages = [max(0, float(value)) for value in outage_durations]
        failures = len(outages) if failure_count is None else max(0, int(failure_count))
        downtime = sum(outages)
        uptime = max(0, period_seconds - downtime)
        return {
            "failure_count": failures, "outage_count": len(outages), "total_downtime_seconds": int(downtime),
            "mtbf_seconds": uptime / failures if failures else None,
            "mttr_seconds": downtime / len(outages) if outages else None,
            "mean_time_to_acknowledge_seconds": sum(acknowledgement_seconds) / len(acknowledgement_seconds) if acknowledgement_seconds else None,
            "mean_time_to_detect_seconds": sum(detection_seconds) / len(detection_seconds) if detection_seconds else None,
            "data_quality": "good" if failures or period_seconds > 0 else "insufficient",
            "assumptions": ["A failure is a confirmed unavailable interval.", "Unknown periods are excluded from uptime and failure evidence.", "Unresolved incidents do not contribute a completed MTTR duration."],
        }
