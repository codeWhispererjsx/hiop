"""Epic 6A analytics contracts. Tests use synthetic values and no production data."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.v1.analytics import router
from app.models.analytics import (
    AnalyticsAggregate, AnalyticsAvailability, AnalyticsDataQualityRecord,
    AnalyticsMetricDefinition, AnalyticsRun, CapacityAssessment, CapacityPolicy,
    EntityHealthScore, HealthScoreConfiguration, ReliabilityMeasurement,
    SLADefinition, SLAMeasurement,
)
from app.schemas.analytics import (
    AnalyticsRunRequest, CapacityPolicyWrite, HealthConfigurationWrite,
    MetricDefinitionWrite, SLADefinitionWrite, TimeRange,
)
from app.services.analytics_aggregation_service import AnalyticsAggregationService, percentile
from app.services.analytics_availability_service import AnalyticsAvailabilityService
from app.services.analytics_capacity_service import AnalyticsCapacityService
from app.services.analytics_health_score_service import AnalyticsHealthScoreService
from app.services.analytics_reliability_service import AnalyticsReliabilityService
from app.services.analytics_sla_service import AnalyticsSLAService

UTC = timezone.utc


def test_all_analytics_models_are_registered():
    assert {
        AnalyticsMetricDefinition.__tablename__, AnalyticsAggregate.__tablename__,
        AnalyticsAvailability.__tablename__, EntityHealthScore.__tablename__,
        HealthScoreConfiguration.__tablename__, CapacityPolicy.__tablename__,
        CapacityAssessment.__tablename__, SLADefinition.__tablename__,
        SLAMeasurement.__tablename__, ReliabilityMeasurement.__tablename__,
        AnalyticsRun.__tablename__, AnalyticsDataQualityRecord.__tablename__,
    } == {
        "analytics_metric_definitions", "analytics_aggregates", "analytics_availability",
        "analytics_health_scores", "analytics_health_configurations",
        "analytics_capacity_policies", "analytics_capacity_assessments",
        "analytics_sla_definitions", "analytics_sla_measurements",
        "analytics_reliability_measurements", "analytics_runs", "analytics_data_quality",
    }


def test_metric_definition_rejects_expressions_and_unknown_sources():
    valid = MetricDefinitionWrite(metric_key="device.cpu_percent", name="CPU", source_module="SNMP", source_metric_key="device.cpu_percent", entity_type="device", aggregation_method="average")
    assert valid.metric_key == "device.cpu_percent"
    with pytest.raises(ValidationError):
        MetricDefinitionWrite(metric_key="select * from metrics", name="Bad", source_module="SNMP", source_metric_key="x", entity_type="device", aggregation_method="average")


def test_time_range_requires_timezone_and_order():
    now = datetime.now(UTC)
    assert TimeRange(start=now - timedelta(hours=1), end=now)
    with pytest.raises(ValidationError): TimeRange(start=now, end=now)
    with pytest.raises(ValidationError): TimeRange(start=now.replace(tzinfo=None), end=now)


def test_health_configuration_normalizes_weights_and_orders_thresholds():
    value = HealthConfigurationWrite(name="Device default", entity_type="device", availability_weight=60, performance_weight=60)
    assert value.availability_weight + value.performance_weight > 100
    with pytest.raises(ValidationError):
        HealthConfigurationWrite(name="Bad", entity_type="device", availability_weight=0, performance_weight=0, reliability_weight=0, alert_weight=0, capacity_weight=0, topology_weight=0, data_quality_weight=0)
    with pytest.raises(ValidationError):
        HealthConfigurationWrite(name="Bad", entity_type="device", excellent_threshold=70, healthy_threshold=80)


def test_capacity_and_sla_schema_thresholds():
    policy = CapacityPolicyWrite(name="Interface utilization", entity_type="interface", metric_key="interface.in_utilization_percent", warning_threshold=70, critical_threshold=90)
    assert not policy.enabled
    with pytest.raises(ValidationError):
        CapacityPolicyWrite(name="Bad", entity_type="device", metric_key="device.cpu_percent", warning_threshold=95, critical_threshold=90)
    sla = SLADefinitionWrite(name="Network", entity_type="device", scope_type="global", target_availability_percent=99.9)
    assert not sla.enabled
    with pytest.raises(ValidationError):
        SLADefinitionWrite(name="Bad", entity_type="device", scope_type="global", target_availability_percent=101)


def test_manual_run_is_bounded_and_defaults_to_dry_run():
    now = datetime.now(UTC)
    request = AnalyticsRunRequest(run_type="full", period_start=now - timedelta(days=1), period_end=now)
    assert request.dry_run
    with pytest.raises(ValidationError):
        AnalyticsRunRequest(run_type="full", period_start=now - timedelta(days=1), period_end=now, entity_ids=[uuid4(), uuid4()], maximum_entities=1)


def test_aggregate_statistics_and_percentiles():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    summary = AnalyticsAggregationService.summarize([(start, 10, "good"), (start + timedelta(minutes=1), 20, "good"), (start + timedelta(minutes=2), 30, "good")])
    assert summary["minimum_value"] == 10
    assert summary["maximum_value"] == 30
    assert summary["average_value"] == 20
    assert summary["sum_value"] == 60
    assert summary["latest_value"] == 30
    assert summary["percentile_50"] == 20
    assert percentile([1, 2, 3, 4], .95) == pytest.approx(3.85)
    assert AnalyticsAggregationService.summarize([])["quality"] == "insufficient"


def test_bucket_boundaries_are_utc_and_stable():
    value = datetime(2026, 1, 1, 10, 7, 42, tzinfo=UTC)
    assert AnalyticsAggregationService.bucket_start(value, "5_minutes") == datetime(2026, 1, 1, 10, 5, tzinfo=UTC)
    assert AnalyticsAggregationService.bucket_start(value, "1_hour") == datetime(2026, 1, 1, 10, tzinfo=UTC)


def test_availability_fully_available_and_unavailable():
    start = datetime(2026, 1, 1, tzinfo=UTC); end = start + timedelta(hours=1)
    available = AnalyticsAvailabilityService.calculate_timeline(start, end, [(start, "online")])
    assert available["availability_percent"] == 100
    assert available["unknown_duration_seconds"] == 0
    unavailable = AnalyticsAvailabilityService.calculate_timeline(start, end, [(start, "offline")])
    assert unavailable["availability_percent"] == 0
    assert unavailable["outage_count"] == 1
    assert unavailable["longest_outage_seconds"] == 3600


def test_availability_unknown_and_maintenance_are_not_available():
    start = datetime(2026, 1, 1, tzinfo=UTC); end = start + timedelta(hours=2)
    result = AnalyticsAvailabilityService.calculate_timeline(start, end, [(start + timedelta(hours=1), "online")])
    assert result["unknown_duration_seconds"] == 3600
    assert result["available_duration_seconds"] == 3600
    maintained = AnalyticsAvailabilityService.calculate_timeline(start, end, [(start, "offline")], [(start, start + timedelta(hours=1))], True)
    assert maintained["maintenance_duration_seconds"] == 3600
    assert maintained["unavailable_duration_seconds"] == 3600


def config(**overrides):
    base = dict(availability_weight=30, performance_weight=20, reliability_weight=15, alert_weight=10, capacity_weight=10, topology_weight=5, data_quality_weight=10, minimum_data_coverage=50, excellent_threshold=90, healthy_threshold=75, warning_threshold=60, degraded_threshold=40)
    return SimpleNamespace(**(base | overrides))


@pytest.mark.parametrize(("components", "status"), [
    ({"availability": 99, "performance": 95, "reliability": 95, "alert": 100, "capacity": 95, "topology": 90, "data_quality": 100}, "excellent"),
    ({"availability": 75, "performance": 60, "reliability": 65, "alert": 60, "capacity": 55, "topology": 60, "data_quality": 80}, "warning"),
    ({"availability": 10, "performance": 20, "reliability": 10, "alert": 0, "capacity": 10, "topology": 20, "data_quality": 80}, "critical"),
])
def test_explainable_health_statuses(components, status):
    result = AnalyticsHealthScoreService.calculate(config(), components)
    assert result["status"] == status
    assert result["contributing_factors"]


def test_missing_health_data_reduces_coverage_not_score():
    result = AnalyticsHealthScoreService.calculate(config(), {"availability": 100})
    assert result["score"] == 100
    assert result["status"] == "unknown"
    assert result["coverage_percent"] == 30
    assert any(item["factor"] == "missing_components" for item in result["contributing_factors"])


def test_capacity_normal_warning_critical_and_insufficient():
    policy = SimpleNamespace(minimum_samples=3, warning_threshold=70, critical_threshold=90, minimum_duration_seconds=0)
    assert AnalyticsCapacityService.assess(policy, [10, 20, 30], 300)["threshold_status"] == "normal"
    assert AnalyticsCapacityService.assess(policy, [70, 75, 80], 300)["threshold_status"] == "warning"
    assert AnalyticsCapacityService.assess(policy, [91, 95, 99], 300)["threshold_status"] == "critical"
    assert AnalyticsCapacityService.assess(policy, [95], 300)["threshold_status"] == "unknown"


def test_sla_met_breached_and_insufficient():
    sla = SimpleNamespace(target_availability_percent=99, target_response_time_ms=100, maximum_incident_resolution_seconds=3600)
    assert AnalyticsSLAService.evaluate(sla, 99.9, 50, 300, 1, 1)["target_met"] is True
    breached = AnalyticsSLAService.evaluate(sla, 98, 150, 4000, 1, 1)
    assert breached["target_met"] is False and len(breached["breach_reasons"]) == 3
    assert AnalyticsSLAService.evaluate(sla, None, None, None)["target_met"] is None


def test_reliability_mtbf_mttr_and_no_failures():
    result = AnalyticsReliabilityService.calculate(1000, [100, 200])
    assert result["mttr_seconds"] == 150
    assert result["mtbf_seconds"] == 350
    no_failures = AnalyticsReliabilityService.calculate(1000, [])
    assert no_failures["mtbf_seconds"] is None and no_failures["mttr_seconds"] is None


def test_analytics_api_foundations_are_registered():
    paths = {route.path for route in router.routes}
    expected = {
        "/analytics/metric-definitions", "/analytics/aggregates", "/analytics/time-series",
        "/analytics/availability", "/analytics/health", "/analytics/health-configurations",
        "/analytics/capacity", "/analytics/capacity-policies", "/analytics/SLA-definitions",
        "/analytics/SLA-measurements", "/analytics/reliability", "/analytics/run",
        "/analytics/runs", "/analytics/runs/{run_id}", "/analytics/runs/{run_id}/cancel",
        "/analytics/summary", "/analytics/entities/{entity_type}/{entity_id}/summary",
    }
    assert expected.issubset(paths)
