"""SLA measurement against availability, response and resolution targets."""


class AnalyticsSLAService:
    @staticmethod
    def evaluate(definition, availability=None, response_time_ms=None, resolution_seconds=None, incident_count=0, resolved_incident_count=0):
        reasons = []
        if availability is None: reasons.append("availability_unknown")
        elif availability < definition.target_availability_percent: reasons.append("availability_target_missed")
        if definition.target_response_time_ms is not None:
            if response_time_ms is None: reasons.append("response_time_unknown")
            elif response_time_ms > definition.target_response_time_ms: reasons.append("response_time_target_missed")
        if definition.maximum_incident_resolution_seconds is not None:
            if resolution_seconds is None and incident_count: reasons.append("resolution_time_unknown")
            elif resolution_seconds is not None and resolution_seconds > definition.maximum_incident_resolution_seconds: reasons.append("resolution_time_target_missed")
        unknown = any(reason.endswith("_unknown") for reason in reasons)
        return {"measured_availability_percent": availability, "measured_response_time_ms": response_time_ms, "incident_count": incident_count, "resolved_incident_count": resolved_incident_count, "average_resolution_seconds": resolution_seconds, "target_met": None if unknown else not reasons, "breach_reasons": reasons, "data_quality": "insufficient" if unknown else "good"}
