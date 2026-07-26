"""Controlled source mapping and idempotent numeric time-bucket aggregation."""
from datetime import datetime, timedelta, timezone
from math import ceil

from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import settings
from app.models.analytics import AnalyticsDataQualityRecord, AnalyticsMetricDefinition
from app.models.network_scan import NetworkScan
from app.models.snmp import SNMPMetric
from app.repositories.analytics_repository import AnalyticsAggregateRepository

BUCKET_SECONDS = {"5_minutes": 300, "15_minutes": 900, "1_hour": 3600, "1_day": 86400, "1_week": 604800, "1_month": 2592000}
SOURCE_MAP = {
    ("SNMP", "device.response_time_ms"): ("snmp", "device.response_time_ms"),
    ("SNMP", "device.uptime_seconds"): ("snmp", "device.uptime_seconds"),
    ("SNMP", "device.cpu_percent"): ("snmp", "device.cpu_percent"),
    ("SNMP", "device.memory_percent"): ("snmp", "device.memory_percent"),
    ("SNMP", "interface.in_utilization_percent"): ("snmp", "interface.in_utilization_percent"),
    ("SNMP", "interface.out_utilization_percent"): ("snmp", "interface.out_utilization_percent"),
    ("network_scan", "device.response_time_ms"): ("scan", "response_time"),
}


def percentile(values, percentage):
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * percentage
    lower = int(position); upper = ceil(position)
    return ordered[lower] if lower == upper else ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


class AnalyticsAggregationService:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def validate_range(start, end):
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise HTTPException(400, "A valid timezone-aware analytics range is required.")
        if end - start > timedelta(days=settings.analytics_maximum_time_range_days):
            raise HTTPException(400, "Analytics range exceeds the configured maximum.")

    @staticmethod
    def bucket_start(value, bucket_size):
        seconds = BUCKET_SECONDS[bucket_size]
        epoch = int(value.astimezone(timezone.utc).timestamp())
        return datetime.fromtimestamp(epoch - epoch % seconds, timezone.utc)

    @staticmethod
    def summarize(samples):
        ordered = sorted(samples, key=lambda item: item[0])
        values = [float(value) for _, value, _ in ordered if value is not None]
        qualities = [quality for _, value, quality in ordered if value is not None]
        if not values:
            return {"sample_count": 0, "quality": "insufficient"}
        quality = "good" if all(item == "good" for item in qualities) else "partial"
        return {
            "sample_count": len(values), "minimum_value": min(values), "maximum_value": max(values),
            "average_value": sum(values) / len(values), "sum_value": sum(values),
            "latest_value": values[-1], "percentile_50": percentile(values, .5),
            "percentile_95": percentile(values, .95), "percentile_99": percentile(values, .99),
            "quality": quality, "source_first_seen_at": ordered[0][0], "source_last_seen_at": ordered[-1][0],
        }

    def load_samples(self, definition, entity_id, start, end):
        mapping = SOURCE_MAP.get((definition.source_module, definition.source_metric_key))
        if not mapping:
            raise HTTPException(400, "Metric definition has no approved source mapping.")
        if mapping[0] == "snmp":
            query = select(SNMPMetric.observed_at, SNMPMetric.value_numeric, SNMPMetric.quality).where(
                SNMPMetric.metric_key == mapping[1], SNMPMetric.observed_at >= start, SNMPMetric.observed_at < end,
                SNMPMetric.value_numeric.is_not(None),
            )
            if entity_id:
                query = query.where(SNMPMetric.target_id == entity_id)
            return list(self.db.execute(query).all())
        query = select(NetworkScan.scanned_at, NetworkScan.response_time).where(
            NetworkScan.scanned_at >= start, NetworkScan.scanned_at < end, NetworkScan.response_time.is_not(None)
        )
        if entity_id:
            query = query.where(NetworkScan.device_id == entity_id)
        return [(when, value, "good") for when, value in self.db.execute(query).all()]

    def aggregate(self, definition, entity_id, start, end, bucket_size, persist=True):
        self.validate_range(start, end)
        if bucket_size not in BUCKET_SECONDS:
            raise HTTPException(400, "Unsupported bucket size.")
        samples = self.load_samples(definition, entity_id, start, end)
        grouped = {}
        for sample in samples:
            grouped.setdefault(self.bucket_start(sample[0], bucket_size), []).append(sample)
        if len(grouped) > settings.analytics_maximum_time_series_points:
            raise HTTPException(413, "Analytics result exceeds maximum time-series points.")
        results = []
        for bucket, values in sorted(grouped.items()):
            summary = self.summarize(values)
            result = {
                "metric_definition_id": definition.id, "entity_type": definition.entity_type,
                "entity_id": entity_id, "bucket_start": bucket,
                "bucket_end": bucket + timedelta(seconds=BUCKET_SECONDS[bucket_size]),
                "bucket_size": bucket_size, **summary, "calculated_at": datetime.now(timezone.utc),
            }
            results.append(AnalyticsAggregateRepository(self.db).upsert(result) if persist else result)
        if persist:
            self.db.commit()
        return results
