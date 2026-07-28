"""Deterministic, explainable forecasting over persisted analytics aggregates only."""
from datetime import timedelta
from math import sqrt
from statistics import fmean, pstdev

from fastapi import HTTPException
from sqlalchemy import select

from app.models.analytics import AnalyticsAggregate, AnalyticsForecast, AnalyticsMetricDefinition
from app.services.analytics_aggregation_service import BUCKET_SECONDS

METHODS = {"linear_regression", "moving_average", "weighted_moving_average", "exponential_smoothing", "growth_percentage"}
MINIMUM_SAMPLES = {
    "linear_regression": 6, "moving_average": 3, "weighted_moving_average": 3,
    "exponential_smoothing": 4, "growth_percentage": 4,
}


def linear_regression(values):
    count = len(values); mean_x = (count - 1) / 2; mean_y = fmean(values)
    denominator = sum((index - mean_x) ** 2 for index in range(count))
    slope = sum((index - mean_x) * (value - mean_y) for index, value in enumerate(values)) / denominator if denominator else 0.0
    intercept = mean_y - slope * mean_x
    fitted = [intercept + slope * index for index in range(count)]
    residual = sqrt(sum((actual - predicted) ** 2 for actual, predicted in zip(values, fitted)) / count)
    variance = sum((value - mean_y) ** 2 for value in values)
    r_squared = 1 - sum((actual - predicted) ** 2 for actual, predicted in zip(values, fitted)) / variance if variance else 1.0
    return slope, intercept, residual, max(0.0, min(1.0, r_squared))


class AnalyticsForecastService:
    def __init__(self, db=None):
        self.db = db

    @staticmethod
    def project(values, method, horizon_points, alpha=.35, moving_window=5):
        if method not in METHODS: raise ValueError("Unsupported forecast method.")
        if len(values) < MINIMUM_SAMPLES[method]: raise ValueError(f"{method} requires at least {MINIMUM_SAMPLES[method]} samples.")
        values = [float(value) for value in values]
        if method == "linear_regression":
            slope, intercept, residual, stability = linear_regression(values)
            predicted = [intercept + slope * (len(values) + offset) for offset in range(horizon_points)]
        elif method == "moving_average":
            window = values[-min(moving_window, len(values)):]
            predicted = [fmean(window)] * horizon_points; residual = pstdev(window); stability = 1 / (1 + residual / max(abs(fmean(window)), 1e-9))
        elif method == "weighted_moving_average":
            window = values[-min(moving_window, len(values)):]; weights = list(range(1, len(window) + 1))
            level = sum(value * weight for value, weight in zip(window, weights)) / sum(weights)
            predicted = [level] * horizon_points; residual = pstdev(window); stability = 1 / (1 + residual / max(abs(level), 1e-9))
        elif method == "exponential_smoothing":
            level = values[0]
            for value in values[1:]: level = alpha * value + (1 - alpha) * level
            predicted = [level] * horizon_points
            residual = sqrt(sum((value - level) ** 2 for value in values) / len(values))
            stability = 1 / (1 + residual / max(abs(level), 1e-9))
        else:
            first, last = values[0], values[-1]
            per_period = (last / first) ** (1 / (len(values) - 1)) - 1 if first != 0 and last / first >= 0 else 0
            predicted = [last * ((1 + per_period) ** (offset + 1)) for offset in range(horizon_points)]
            residual = pstdev(values); stability = 1 / (1 + residual / max(abs(fmean(values)), 1e-9))
        return predicted, residual, max(0.0, min(1.0, stability))

    @staticmethod
    def growth_rates(values, bucket_seconds):
        if len(values) < 2: return {"per_bucket_percent": None, "hourly_percent": None, "daily_percent": None, "weekly_percent": None, "monthly_percent": None}
        first, last = float(values[0]), float(values[-1])
        rate = (last / first) ** (1 / (len(values) - 1)) - 1 if first != 0 and last / first >= 0 else 0.0
        def scale(seconds):
            periods = seconds / bucket_seconds
            return ((1 + rate) ** periods - 1) * 100 if rate > -1 else -100.0
        return {"per_bucket_percent": rate * 100, "hourly_percent": scale(3600), "daily_percent": scale(86400), "weekly_percent": scale(604800), "monthly_percent": scale(2592000)}

    @staticmethod
    def confidence(values, qualities, stability):
        sample_factor = min(1.0, len(values) / 30)
        quality_factor = sum(item == "good" for item in qualities) / len(qualities)
        mean = abs(fmean(values)); coefficient = pstdev(values) / mean if mean > 1e-9 else pstdev(values)
        variance_factor = 1 / (1 + coefficient)
        score = 100 * (.3 * sample_factor + .3 * quality_factor + .25 * stability + .15 * variance_factor)
        return round(max(0.0, min(100.0, score)), 2), coefficient

    @staticmethod
    def seasonal_comparison(values, season_length):
        if not season_length or len(values) < season_length * 2: return None
        current, previous = values[-season_length:], values[-2 * season_length:-season_length]
        previous_mean = fmean(previous); current_mean = fmean(current)
        return {"season_length": season_length, "current_average": current_mean, "previous_average": previous_mean, "change_percent": ((current_mean - previous_mean) / abs(previous_mean) * 100) if previous_mean else None}

    @staticmethod
    def risk(definition, projected, confidence):
        warning, critical = definition.warning_threshold, definition.critical_threshold
        if not definition.higher_is_better and critical is not None and projected >= critical: base = 100
        elif not definition.higher_is_better and warning is not None and projected >= warning: base = 70
        elif definition.higher_is_better and critical is not None and projected <= critical: base = 100
        elif definition.higher_is_better and warning is not None and projected <= warning: base = 70
        else: base = 20
        score = round(base * confidence / 100, 2)
        return score, "critical" if score >= 75 else "high" if score >= 55 else "medium" if score >= 30 else "low"

    def run(self, definition, entity_id, start, end, bucket_size, method, horizon_points, alpha=.35, moving_window=5, persist=True):
        if bucket_size not in BUCKET_SECONDS: raise HTTPException(400, "Unsupported forecast bucket size.")
        rows = self.db.scalars(select(AnalyticsAggregate).where(
            AnalyticsAggregate.metric_definition_id == definition.id,
            AnalyticsAggregate.entity_id == entity_id,
            AnalyticsAggregate.bucket_size == bucket_size,
            AnalyticsAggregate.bucket_start >= start, AnalyticsAggregate.bucket_end <= end,
        ).order_by(AnalyticsAggregate.bucket_start)).all()
        usable = [row for row in rows if row.average_value is not None and row.quality in {"good", "partial"}]
        if len(usable) < MINIMUM_SAMPLES.get(method, 999):
            raise HTTPException(422, f"Forecast rejected: {method} requires at least {MINIMUM_SAMPLES.get(method, 1)} valid aggregate samples.")
        values = [float(row.average_value) for row in usable]; qualities = [row.quality for row in usable]
        good_ratio = sum(value == "good" for value in qualities) / len(qualities)
        if good_ratio < .5: raise HTTPException(422, "Forecast rejected: aggregate data quality is too poor.")
        predicted, residual, stability = self.project(values, method, horizon_points, alpha, moving_window)
        confidence, coefficient = self.confidence(values, qualities, stability)
        if coefficient > 2: raise HTTPException(422, "Forecast rejected: historical variance is excessive.")
        interval = timedelta(seconds=BUCKET_SECONDS[bucket_size]); forecast_start = usable[-1].bucket_end
        bounds = max(residual, abs(predicted[-1]) * (1 - confidence / 100))
        growth = self.growth_rates(values, BUCKET_SECONDS[bucket_size])
        relative_change = (predicted[-1] - values[-1]) / max(abs(values[-1]), 1e-9)
        direction = "stable" if abs(relative_change) < .01 else "increasing" if relative_change > 0 else "decreasing"
        risk_score, risk_level = self.risk(definition, predicted[-1], confidence)
        points = [{"timestamp": forecast_start + interval * index, "value": value, "lower_bound": value - bounds, "upper_bound": value + bounds} for index, value in enumerate(predicted, 1)]
        assumptions = [
            "Projection uses persisted analytics aggregates only.",
            f"Method={method}; minimum_samples={MINIMUM_SAMPLES[method]}.",
            "Confidence combines sample count, aggregate quality, fit stability, and variance.",
            "Bounds are deterministic residual/confidence intervals, not probability guarantees.",
        ]
        seasonal = self.seasonal_comparison(values, 7 if bucket_size in {"1_day", "1_week"} else 24 if bucket_size == "1_hour" else None)
        if seasonal: assumptions.append(f"Seasonal comparison used a {seasonal['season_length']}-bucket lag.")
        row = AnalyticsForecast(
            entity_type=definition.entity_type, entity_id=entity_id, metric_key=definition.metric_key,
            forecast_method=method, period_start=start, period_end=end, forecast_start=forecast_start,
            forecast_end=points[-1]["timestamp"], prediction_points=points, projected_value=predicted[-1],
            lower_bound=predicted[-1] - bounds, upper_bound=predicted[-1] + bounds,
            confidence_score=confidence, growth_rate=growth["per_bucket_percent"] or 0,
            trend_direction=direction, risk_score=risk_score, risk_level=risk_level,
            sample_count=len(values), data_quality="good" if good_ratio >= .9 else "partial",
            assumptions=assumptions,
        )
        if persist:
            self.db.add(row); self.db.commit(); self.db.refresh(row)
        return row, {"growth_rates": growth, "seasonal_comparison": seasonal}

    def evaluate(self, forecast):
        actual = self.db.scalar(select(AnalyticsAggregate.average_value).join(
            AnalyticsMetricDefinition, AnalyticsMetricDefinition.id == AnalyticsAggregate.metric_definition_id
        ).where(
            AnalyticsMetricDefinition.metric_key == forecast.metric_key,
            AnalyticsAggregate.entity_type == forecast.entity_type,
            AnalyticsAggregate.entity_id == forecast.entity_id,
            AnalyticsAggregate.bucket_end >= forecast.forecast_end,
            AnalyticsAggregate.average_value.is_not(None),
        ).order_by(AnalyticsAggregate.bucket_end).limit(1))
        if actual is None: return {"evaluated": False, "reason": "Actual aggregate is not yet available."}
        error = float(actual) - forecast.projected_value
        forecast.actual_value = float(actual); forecast.forecast_error = error
        forecast.accuracy_percent = max(0.0, 100 - abs(error) / max(abs(float(actual)), 1e-9) * 100)
        from datetime import datetime, timezone
        forecast.evaluated_at = datetime.now(timezone.utc); self.db.commit()
        return {"evaluated": True, "actual_value": actual, "forecast_error": error, "accuracy_percent": forecast.accuracy_percent}
