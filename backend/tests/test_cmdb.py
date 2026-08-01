from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.v1.cmdb import AttributeWrite, BulkWrite, CIWrite, RelationshipWrite, router
from app.main import app
from app.models import cmdb as models
from app.services.cmdb_service import ATTRIBUTE_TYPES, DEPENDENCY_CODES, LIFECYCLE_TRANSITIONS, attribute_value, normalize_identifier
from app.services.scheduler_service import CMDB_JOB_INTERVALS, cmdb_job_id


def test_cmdb_models_are_registered_and_distinct():
    names={"ConfigurationItem","CIType","CIClass","CIStatus","CILifecycle","CIAttribute","CIAttributeHistory","CIIdentifier","CIAlias","CIRelationship","CIRelationshipType","RelationshipHistory","CILifecycleHistory","DependencyGraph","CIReconciliationCandidate","CIHealthSnapshot"}
    assert all(hasattr(models,name) for name in names)
    assert len({getattr(models,name).__tablename__ for name in names})==16


def test_ci_lifecycle_is_strict_and_terminal():
    assert LIFECYCLE_TRANSITIONS["planned"]=={"ordered","archived"}
    assert "operational" not in LIFECYCLE_TRANSITIONS["planned"]
    assert LIFECYCLE_TRANSITIONS["operational"]=={"maintenance","retired"}
    assert LIFECYCLE_TRANSITIONS["archived"]==set()


@pytest.mark.parametrize("kind,value,expected",[("mac","AA:BB:CC:DD:EE:FF","aabbccddeeff"),("hostname","Core-SWITCH.","core-switch"),("ip","10.0.0.1","10.0.0.1")])
def test_identifier_normalization_is_deterministic(kind,value,expected):assert normalize_identifier(kind,value)==expected


def test_attribute_validation_accepts_typed_values_and_rejects_unsafe_values():
    assert {"ip","mac","json"}.issubset(ATTRIBUTE_TYPES)
    assert attribute_value(AttributeWrite(name="network.ip",data_type="ip",value_text="10.0.0.1",reason="verified"))=='"10.0.0.1"'
    with pytest.raises(HTTPException):attribute_value(AttributeWrite(name="network.ip",data_type="ip",value_text="not-an-ip",reason="verified"))
    with pytest.raises(HTTPException):attribute_value(AttributeWrite(name="bad.json",data_type="json",value_text="{bad",reason="verified"))
    with pytest.raises(HTTPException):attribute_value(AttributeWrite(name="ambiguous",data_type="string",value_text="x",value_number=1,reason="verified"))


def test_ci_and_relationship_schemas_bound_mutations():
    with pytest.raises(ValidationError):RelationshipWrite(target_ci_id="00000000-0000-0000-0000-000000000001",relationship_type_id="00000000-0000-0000-0000-000000000002",evidence="ok",confidence=101)
    with pytest.raises(ValidationError):BulkWrite(ci_ids=[],action="verify",reason="reviewed")
    with pytest.raises(ValidationError):CIWrite(type_id="00000000-0000-0000-0000-000000000001",class_id="00000000-0000-0000-0000-000000000002",name="x",criticality="certain")


def test_dependency_relationship_codes_are_allowlisted():
    assert DEPENDENCY_CODES=={"runs_on","hosts","depends_on","uses","supports","contained_in","located_in","managed_by","monitored_by"}
    assert "connected_to" not in DEPENDENCY_CODES


def test_cmdb_api_surface_covers_framework_graph_impact_reconciliation_health_and_reports():
    paths={route.path for route in router.routes}
    expected={"/cmdb/dashboard","/cmdb/classes","/cmdb/types","/cmdb/items","/cmdb/items/{ci_id}","/cmdb/items/{ci_id}/lifecycle","/cmdb/items/{ci_id}/attributes","/cmdb/items/{ci_id}/identifiers","/cmdb/relationship-types","/cmdb/items/{ci_id}/relationships","/cmdb/dependency-graph","/cmdb/items/{ci_id}/impact","/cmdb/reconciliation/run","/cmdb/reconciliation/candidates","/cmdb/health","/cmdb/reports/summary","/cmdb/reports/export"}
    assert expected.issubset(paths)
    assert not any("infer" in path or "ai" in path or "execute" in path for path in paths)


def test_cmdb_scheduler_jobs_are_stable_and_separate():
    expected={"ci_verification","relationship_validation","health_recalculation","duplicate_detection","orphan_detection","discovery_reconciliation","expired_warranty_notifications"}
    assert set(CMDB_JOB_INTERVALS)==expected
    assert cmdb_job_id("ci_verification")=="cmdb_ci_verification"
    with pytest.raises(ValueError):cmdb_job_id("arbitrary")


def test_cmdb_endpoints_require_authentication():
    client=TestClient(app)
    assert client.get("/api/v1/cmdb/dashboard").status_code==401
    assert client.post("/api/v1/cmdb/items",json={}).status_code==401
    assert client.post("/api/v1/cmdb/reconciliation/run",json={}).status_code==401


def test_reconciliation_is_review_only_and_does_not_auto_create_relationships():
    service=Path("app/services/cmdb_service.py").read_text()
    api=Path("app/api/v1/cmdb.py").read_text()
    assert "CIReconciliationCandidate" in service
    assert "no CI was auto-created" in api
    assert "add_relationship(db" not in service[service.index("def reconciliation_candidates"):]


def test_migration_is_additive_seeded_and_reversible():
    text=Path("alembic/versions/c0d1e2f3a4b5_enterprise_cmdb.py").read_text()
    assert 'down_revision="b9c0d1e2f3a4"' in text
    for value in ("Opera PMS","Door Lock Controller","Azure Resource","Patch Panel","Depends On","Monitored By"):assert value in text
    assert "reversed(TABLES)" in text
