"""Epic 6C deterministic forecast tests using synthetic aggregates only."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.analytics import router
from app.models.analytics import AnalyticsForecast
from app.schemas.analytics import ForecastRunRequest
from app.services.analytics_forecast_service import AnalyticsForecastService, linear_regression

UTC = timezone.utc


def test_forecast_model_is_registered_and_auditable():
    assert AnalyticsForecast.__tablename__ == "analytics_forecasts"
    assert {"prediction_points", "confidence_score", "assumptions", "actual_value", "forecast_error", "accuracy_percent"}.issubset(AnalyticsForecast.__table__.columns.keys())


def test_linear_projection_is_deterministic_and_increasing():
    predicted, residual, stability = AnalyticsForecastService.project([10, 12, 14, 16, 18, 20], "linear_regression", 3)
    assert predicted == pytest.approx([22, 24, 26])
    assert residual == pytest.approx(0)
    assert stability == pytest.approx(1)
    assert linear_regression([5, 5, 5, 5, 5, 5])[0] == 0


def test_moving_weighted_and_exponential_smoothing():
    moving, _, _ = AnalyticsForecastService.project([1, 2, 3, 4], "moving_average", 2, moving_window=3)
    weighted, _, _ = AnalyticsForecastService.project([1, 2, 3, 4], "weighted_moving_average", 2, moving_window=3)
    smoothed, _, _ = AnalyticsForecastService.project([10, 20, 10, 20], "exponential_smoothing", 2, alpha=.5)
    assert moving == pytest.approx([3, 3])
    assert weighted == pytest.approx([20 / 6, 20 / 6])
    assert smoothed == pytest.approx([16.25, 16.25])


def test_growth_projection_and_period_rates():
    projected, _, _ = AnalyticsForecastService.project([100, 110, 121, 133.1], "growth_percentage", 2)
    assert projected == pytest.approx([146.41, 161.051])
    rates = AnalyticsForecastService.growth_rates([100, 110, 121], 86400)
    assert rates["daily_percent"] == pytest.approx(10)
    assert rates["weekly_percent"] > rates["daily_percent"]


def test_confidence_is_explainable_and_bounded():
    high, high_variance = AnalyticsForecastService.confidence([10] * 30, ["good"] * 30, 1)
    low, _ = AnalyticsForecastService.confidence([1, 10, 1, 10, 1, 10], ["partial"] * 6, .2)
    assert high == 100
    assert high_variance == 0
    assert 0 <= low < high <= 100


def test_seasonal_comparison_requires_two_complete_seasons():
    assert AnalyticsForecastService.seasonal_comparison([1] * 13, 7) is None
    result = AnalyticsForecastService.seasonal_comparison([10] * 7 + [12] * 7, 7)
    assert result["change_percent"] == pytest.approx(20)


def test_forecast_request_is_bounded():
    now = datetime.now(UTC)
    request = ForecastRunRequest(entity_type="device", entity_id=uuid4(), metric_key="device.cpu_percent", period_start=now - timedelta(days=1), period_end=now)
    assert request.horizon_points == 24
    with pytest.raises(Exception):
        ForecastRunRequest(entity_type="device", entity_id=uuid4(), metric_key="device.cpu_percent", period_start=now, period_end=now, horizon_points=121)


class FakeScalars:
    def __init__(self, rows): self.rows = rows
    def all(self): return self.rows


class FakeDB:
    def __init__(self, rows): self.rows = rows
    def scalars(self, query): return FakeScalars(self.rows)


def aggregate_rows(values, qualities=None):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    qualities = qualities or ["good"] * len(values)
    return [SimpleNamespace(average_value=value, quality=quality, bucket_start=start + timedelta(hours=index), bucket_end=start + timedelta(hours=index + 1)) for index, (value, quality) in enumerate(zip(values, qualities))]


def definition():
    return SimpleNamespace(id=uuid4(), entity_type="device", metric_key="device.cpu_percent", warning_threshold=75, critical_threshold=90, higher_is_better=False)


def test_service_detects_increasing_decreasing_and_stable_trends():
    start = datetime(2026, 1, 1, tzinfo=UTC); end = start + timedelta(hours=12)
    increasing, _ = AnalyticsForecastService(FakeDB(aggregate_rows([10, 20, 30, 40, 50, 60]))).run(definition(), uuid4(), start, end, "1_hour", "linear_regression", 2, persist=False)
    decreasing, _ = AnalyticsForecastService(FakeDB(aggregate_rows([60, 50, 40, 30, 20, 10]))).run(definition(), uuid4(), start, end, "1_hour", "linear_regression", 2, persist=False)
    stable, _ = AnalyticsForecastService(FakeDB(aggregate_rows([50, 50, 50, 50, 50, 50]))).run(definition(), uuid4(), start, end, "1_hour", "linear_regression", 2, persist=False)
    assert increasing.trend_direction == "increasing"
    assert decreasing.trend_direction == "decreasing"
    assert stable.trend_direction == "stable"


def test_service_rejects_empty_and_poor_history():
    start = datetime(2026, 1, 1, tzinfo=UTC); end = start + timedelta(hours=12)
    with pytest.raises(HTTPException, match="requires at least"):
        AnalyticsForecastService(FakeDB([])).run(definition(), uuid4(), start, end, "1_hour", "linear_regression", 2, persist=False)
    poor = aggregate_rows([10, 11, 12, 13, 14, 15], ["partial", "partial", "partial", "partial", "good", "good"])
    with pytest.raises(HTTPException, match="quality"):
        AnalyticsForecastService(FakeDB(poor)).run(definition(), uuid4(), start, end, "1_hour", "linear_regression", 2, persist=False)


def test_forecast_api_routes_are_registered():
    paths = {route.path for route in router.routes}
    assert {
        "/analytics/forecasts", "/analytics/entities/{entity_type}/{entity_id}/forecast",
        "/analytics/forecast/run", "/analytics/forecast/history",
        "/analytics/forecasts/{forecast_id}/evaluate", "/analytics/forecast-summary",
        "/analytics/forecast-report",
    }.issubset(paths)
