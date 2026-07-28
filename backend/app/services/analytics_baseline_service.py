"""Explainable, aggregate-only statistical baselines."""
from __future__ import annotations

import math
import statistics
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select

from app.models.analytics import AnalyticsAggregate, AnalyticsBaseline, AnalyticsMetricDefinition


class AnalyticsBaselineService:
    MINIMUM_SAMPLES = 8

    def __init__(self, db):
        self.db = db

    @staticmethod
    def percentile(values: list[float], quantile: float) -> float:
        ordered = sorted(values)
        if not ordered:
            raise ValueError("A percentile requires samples.")
        position = (len(ordered) - 1) * quantile
        lower, upper = math.floor(position), math.ceil(position)
        return ordered[lower] if lower == upper else ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)

    @classmethod
    def calculate(cls, values: list[float], quality_ratio: float = 1.0) -> dict:
        clean = [float(value) for value in values if math.isfinite(float(value))]
        if len(clean) < cls.MINIMUM_SAMPLES:
            raise ValueError(f"At least {cls.MINIMUM_SAMPLES} valid aggregate samples are required.")
        median = statistics.median(clean)
        deviations = [abs(value - median) for value in clean]
        q05, q25, q75, q95 = (cls.percentile(clean, q) for q in (.05, .25, .75, .95))
        iqr = q75 - q25
        confidence = min(100.0, len(clean) / 30 * 100) * max(0, min(1, quality_ratio))
        return {
            "sample_count": len(clean), "mean_value": statistics.fmean(clean), "median_value": median,
            "minimum_value": min(clean), "maximum_value": max(clean),
            "standard_deviation": statistics.pstdev(clean), "median_absolute_deviation": statistics.median(deviations),
            "percentile_05": q05, "percentile_25": q25, "percentile_75": q75, "percentile_95": q95,
            "expected_lower_bound": q25 - 1.5 * iqr, "expected_upper_bound": q75 + 1.5 * iqr,
            "confidence_score": round(confidence, 2), "data_quality": "good" if quality_ratio >= .8 else "partial",
        }

    def recalculate(self, entity_type: str, entity_id: UUID, metric_key: str, bucket_size: str = "1_hour", baseline_type: str = "rolling", window: int = 168):
        definition = self.db.scalar(select(AnalyticsMetricDefinition).where(
            AnalyticsMetricDefinition.metric_key == metric_key,
            AnalyticsMetricDefinition.entity_type == entity_type,
            AnalyticsMetricDefinition.enabled.is_(True),
        ))
        if not definition:
            raise HTTPException(404, "An enabled numeric analytics metric was not found.")
        rows = self.db.scalars(select(AnalyticsAggregate).where(
            AnalyticsAggregate.metric_definition_id == definition.id,
            AnalyticsAggregate.entity_id == entity_id,
            AnalyticsAggregate.bucket_size == bucket_size,
        ).order_by(AnalyticsAggregate.bucket_start.desc()).limit(min(window, 1000))).all()
        values = [row.average_value if row.average_value is not None else row.latest_value for row in rows]
        usable = [value for value in values if value is not None]
        quality_ratio = sum(row.quality == "good" for row in rows) / max(1, len(rows))
        try:
            result = self.calculate(usable, quality_ratio)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        now = datetime.now(timezone.utc)
        baseline = self.db.scalar(select(AnalyticsBaseline).where(
            AnalyticsBaseline.entity_type == entity_type, AnalyticsBaseline.entity_id == entity_id,
            AnalyticsBaseline.metric_key == metric_key, AnalyticsBaseline.baseline_type == baseline_type,
            AnalyticsBaseline.bucket_size == bucket_size, AnalyticsBaseline.seasonality_key == "",
        ))
        if not baseline:
            baseline = AnalyticsBaseline(entity_type=entity_type, entity_id=entity_id, metric_key=metric_key,
                baseline_type=baseline_type, bucket_size=bucket_size, seasonality_key="", period_start=min(row.bucket_start for row in rows),
                period_end=max(row.bucket_end for row in rows), valid_until=now + timedelta(hours=24), **result)
            self.db.add(baseline)
        else:
            for key, value in result.items(): setattr(baseline, key, value)
            baseline.period_start=min(row.bucket_start for row in rows); baseline.period_end=max(row.bucket_end for row in rows)
            baseline.calculated_at=now; baseline.valid_until=now + timedelta(hours=24)
        self.db.flush()
        return baseline

    def coverage(self) -> dict:
        definitions = self.db.query(AnalyticsMetricDefinition).filter_by(enabled=True).count()
        valid = self.db.query(AnalyticsBaseline).filter(AnalyticsBaseline.valid_until > datetime.now(timezone.utc), AnalyticsBaseline.data_quality.in_(("good", "partial"))).count()
        return {"eligible_metrics": definitions, "valid_baselines": valid, "coverage_percent": round(valid / max(1, definitions) * 100, 2)}
