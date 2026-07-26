"""Availability timeline calculation where unknown time is never counted available."""
from datetime import datetime, timezone
from sqlalchemy import select

from app.models.analytics import AnalyticsAvailability


class AnalyticsAvailabilityService:
    AVAILABLE = {"online", "reachable", "up", "healthy", "available"}
    UNAVAILABLE = {"offline", "unreachable", "down", "critical", "unavailable"}

    @classmethod
    def calculate_timeline(cls, start, end, events, maintenance=(), exclude_maintenance=True):
        boundaries = {start, end}
        for when, _ in events:
            if start <= when <= end: boundaries.add(when)
        for window_start, window_end in maintenance:
            boundaries.update((max(start, window_start), min(end, window_end)))
        ordered = sorted(boundaries)
        available = unavailable = unknown = maintained = outages = longest = 0
        current = "unknown"; event_index = 0; active_outage = 0
        sorted_events = sorted(events)
        for left, right in zip(ordered, ordered[1:]):
            while event_index < len(sorted_events) and sorted_events[event_index][0] <= left:
                current = str(sorted_events[event_index][1]).lower(); event_index += 1
            seconds = max(0, int((right - left).total_seconds()))
            in_maintenance = any(window_start < right and window_end > left for window_start, window_end in maintenance)
            if in_maintenance and exclude_maintenance:
                maintained += seconds; active_outage = 0
            elif current in cls.AVAILABLE:
                available += seconds; active_outage = 0
            elif current in cls.UNAVAILABLE:
                if active_outage == 0: outages += 1
                active_outage += seconds; unavailable += seconds; longest = max(longest, active_outage)
            else:
                unknown += seconds; active_outage = 0
        measurable = available + unavailable
        return {
            "expected_duration_seconds": int((end - start).total_seconds()),
            "available_duration_seconds": available, "unavailable_duration_seconds": unavailable,
            "maintenance_duration_seconds": maintained, "unknown_duration_seconds": unknown,
            "availability_percent": available / measurable * 100 if measurable else None,
            "outage_count": outages, "longest_outage_seconds": longest,
        }

    def store(self, entity_type, entity_id, start, end, events, maintenance=(), exclude_maintenance=True, source_type="normalized_status"):
        values = self.calculate_timeline(start, end, events, maintenance, exclude_maintenance)
        row = self.db.scalar(select(AnalyticsAvailability).filter_by(entity_type=entity_type, entity_id=entity_id, period_start=start, period_end=end, source_type=source_type))
        if not row:
            row = AnalyticsAvailability(entity_type=entity_type, entity_id=entity_id, period_start=start, period_end=end, source_type=source_type, **values)
            self.db.add(row)
        else:
            for key, value in values.items(): setattr(row, key, value)
            row.calculated_at = datetime.now(timezone.utc)
        self.db.commit()
        return row

    def __init__(self, db):
        self.db = db
