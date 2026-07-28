"""Epic 6B scheduled analytics contracts; all data is synthetic."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1.analytics import router
from app.models.analytics import (
    AnalyticsCheckpoint, AnalyticsRetentionPolicy, AnalyticsRun,
    AnalyticsScheduleConfiguration,
)
from app.schemas.analytics import AnalyticsBackfillRequest, AnalyticsScheduleWrite, RetentionCleanupRequest
from app.services.analytics_operational_service import AnalyticsOperationalService, RUN_TRANSITIONS
from app.services.scheduler_service import ANALYTICS_JOB_TYPES, analytics_job_id

UTC = timezone.utc


def test_epic_6b_models_are_registered():
    assert AnalyticsScheduleConfiguration.__tablename__ == "analytics_schedule_configurations"
    assert AnalyticsCheckpoint.__tablename__ == "analytics_checkpoints"
    assert AnalyticsRetentionPolicy.__tablename__ == "analytics_retention_policies"
    assert {"job_id", "batches_total", "records_updated", "stale_recovery_status"}.issubset(AnalyticsRun.__table__.columns.keys())


def test_schedule_defaults_are_safe_and_bounded():
    value = AnalyticsScheduleWrite()
    assert value.enabled is False
    assert value.aggregate_interval_minutes >= 5
    assert value.batch_size <= value.maximum_entities_per_run
    with pytest.raises(ValidationError):
        AnalyticsScheduleWrite(aggregate_interval_minutes=1)


def test_backfill_requires_bounded_timezone_aware_range():
    end = datetime.now(UTC)
    value = AnalyticsBackfillRequest(
        analytics_types=["aggregate"], entity_type="device",
        period_start=end - timedelta(days=1), period_end=end,
    )
    assert value.dry_run is True
    with pytest.raises(ValidationError):
        AnalyticsBackfillRequest(
            analytics_types=["aggregate"], entity_type="device",
            period_start=(end - timedelta(days=1)).replace(tzinfo=None),
            period_end=end.replace(tzinfo=None),
        )
    with pytest.raises(ValidationError):
        AnalyticsBackfillRequest(
            analytics_types=["aggregate"], entity_type="device",
            period_start=end - timedelta(days=1), period_end=end,
            entity_ids=[uuid4(), uuid4()], maximum_entities=1,
        )


def test_retention_cleanup_requires_exact_confirmation():
    assert RetentionCleanupRequest(confirmation="DELETE_EXPIRED_ANALYTICS")
    with pytest.raises(ValidationError):
        RetentionCleanupRequest(confirmation="yes")


def test_run_lifecycle_rejects_invalid_transitions():
    run = SimpleNamespace(status="pending")
    AnalyticsOperationalService.transition(run, "running")
    assert run.status == "running"
    AnalyticsOperationalService.transition(run, "partial")
    with pytest.raises(HTTPException) as error:
        AnalyticsOperationalService.transition(run, "running")
    assert error.value.status_code == 409
    assert "completed" not in RUN_TRANSITIONS["failed"]


def test_weighted_rollup_preserves_counts_min_and_max():
    service = AnalyticsOperationalService(SimpleNamespace())
    definition = SimpleNamespace(id=uuid4())
    rows = [
        SimpleNamespace(bucket_start=datetime(2026, 1, 1, tzinfo=UTC), sample_count=2, average_value=10, minimum_value=5, maximum_value=15, sum_value=20, latest_value=15, quality="good"),
        SimpleNamespace(bucket_start=datetime(2026, 1, 1, 0, 5, tzinfo=UTC), sample_count=8, average_value=20, minimum_value=16, maximum_value=25, sum_value=160, latest_value=25, quality="partial"),
    ]

    class Scalars:
        def all(self): return rows
    class DB:
        def scalars(self, query): return Scalars()

    service.db = DB()
    output = service.rollup(definition, None, datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 1, 1, tzinfo=UTC), "5_minutes", "1_hour")
    assert output[0]["sample_count"] == 10
    assert output[0]["average_value"] == 18
    assert output[0]["minimum_value"] == 5
    assert output[0]["maximum_value"] == 25
    assert output[0]["quality"] == "partial"


def test_analytics_job_ids_are_stable_and_separate():
    ids = [analytics_job_id(kind) for kind in ANALYTICS_JOB_TYPES]
    assert len(ids) == len(set(ids))
    assert all(value.startswith("analytics_") for value in ids)
    with pytest.raises(ValueError):
        analytics_job_id("forecast")


def test_epic_6b_api_routes_are_registered():
    paths = {route.path for route in router.routes}
    expected = {
        "/analytics/schedule", "/analytics/schedule/pause", "/analytics/schedule/resume",
        "/analytics/scheduler-status", "/analytics/backfill", "/analytics/backfill/preview",
        "/analytics/runs/{run_id}/progress", "/analytics/runs/{run_id}/errors",
        "/analytics/runs/{run_id}/retry", "/analytics/trends", "/analytics/data-quality",
        "/analytics/capacity-summary", "/analytics/SLA-summary",
        "/analytics/reliability-summary", "/analytics/retention/preview",
        "/analytics/retention/cleanup",
    }
    assert expected.issubset(paths)
