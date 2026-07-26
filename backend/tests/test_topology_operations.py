"""Epic 5E operational contracts. No network operation occurs."""
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.v1.topology_operations import router
from app.models.topology_operations import (
    TopologyAlertEvent,
    TopologyAlertRule,
    TopologyOperationalRun,
    TopologyScheduleConfiguration,
)
from app.schemas.topology_operations import AlertRuleWrite, ScheduleWrite
from app.services.scheduler_service import TOPOLOGY_JOB_TYPES, topology_job_id
from app.services.topology_operational_service import TopologyOperationalService, _safe_csv


def test_operational_models_are_registered():
    assert TopologyScheduleConfiguration.__tablename__ == "topology_schedule_configurations"
    assert TopologyOperationalRun.__tablename__ == "topology_operational_runs"
    assert TopologyAlertRule.__tablename__ == "topology_alert_rules"
    assert TopologyAlertEvent.__tablename__ == "topology_alert_events"


def test_schedule_limits_and_safe_defaults():
    value = ScheduleWrite()
    assert not value.enabled
    assert not value.neighbor_collection_enabled
    assert value.maximum_targets_per_run == 25
    with pytest.raises(ValidationError):
        ScheduleWrite(neighbor_collection_interval_minutes=1)
    with pytest.raises(ValidationError):
        ScheduleWrite(maximum_targets_per_run=1000)


def test_alert_rule_scoping_and_disabled_default():
    value = AlertRuleWrite(name="Stale graph", rule_type="topology_stale")
    assert not value.enabled
    with pytest.raises(ValidationError):
        AlertRuleWrite(
            name="Contradictory scope",
            rule_type="node_missing",
            node_id=uuid4(),
            link_id=uuid4(),
        )


def test_deterministic_topology_job_ids():
    topology_id = str(uuid4())
    values = {topology_job_id(topology_id, kind) for kind in TOPOLOGY_JOB_TYPES}
    assert len(values) == len(TOPOLOGY_JOB_TYPES)
    assert values == {f"topology_{topology_id}_{kind}" for kind in TOPOLOGY_JOB_TYPES}


def test_tarjan_detects_articulation_and_bridges():
    a, b, c = uuid4(), uuid4(), uuid4()
    first, second = uuid4(), uuid4()
    adjacency = {a: {b}, b: {a, c}, c: {b}}
    edge_ids = {frozenset((a, b)): first, frozenset((b, c)): second}
    articulation, bridges = TopologyOperationalService._tarjan([a, b, c], adjacency, edge_ids)
    assert articulation == {b}
    assert bridges == {first, second}


@pytest.mark.parametrize("value", ["=2+2", "+cmd", "-1", "@formula", "\tdata"])
def test_csv_formula_injection_is_neutralized(value):
    assert _safe_csv(value).startswith("'")


def test_operations_api_routes_are_registered():
    paths = {route.path for route in router.routes}
    expected = {
        "/topology/alert-rules",
        "/topology/alerts",
        "/topology/retention/preview",
        "/topology/retention/cleanup",
        "/topology/{topology_id}/schedule",
        "/topology/{topology_id}/scheduler-status",
        "/topology/{topology_id}/health",
        "/topology/{topology_id}/analytics",
        "/topology/{topology_id}/operational-runs",
        "/topology/{topology_id}/reports/summary",
    }
    assert expected.issubset(paths)
