from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.api.v1.inventory_imports import _session
from app.models.hierarchy import Department
from app.services.import_finalization_service import ImportFinalizationService
from app.services.import_matching_service import ImportMatchingService


def test_import_session_is_bound_to_organization_and_property():
    organization_id, property_id = uuid4(), uuid4()
    session = SimpleNamespace(
        mapping_metadata={
            "tenant_organization_id": str(organization_id),
            "tenant_property_id": str(property_id),
        }
    )
    db = SimpleNamespace(info={}, get=lambda model, identifier: session)

    assert _session(db, uuid4(), organization_id, property_id) is session
    assert db.info == {"organization_id": organization_id, "property_id": property_id}

    with pytest.raises(HTTPException) as error:
        _session(db, uuid4(), uuid4(), property_id)
    assert error.value.status_code == 404


def test_import_session_property_scope_cannot_be_widened():
    organization_id, session_property_id = uuid4(), uuid4()
    session = SimpleNamespace(
        mapping_metadata={
            "tenant_organization_id": str(organization_id),
            "tenant_property_id": str(session_property_id),
        }
    )
    db = SimpleNamespace(info={}, get=lambda model, identifier: session)

    with pytest.raises(HTTPException) as error:
        _session(db, uuid4(), organization_id, uuid4())
    assert error.value.status_code == 404


def test_import_hierarchy_lookup_includes_organization_departments_and_active_property():
    organization_id, property_id = uuid4(), uuid4()
    db = SimpleNamespace(info={"organization_id": organization_id, "property_id": property_id})

    for service in (ImportMatchingService(db), ImportFinalizationService(db)):
        statement = service._hierarchy_query(Department)
        sql = str(statement.compile(dialect=postgresql.dialect()))

        assert "departments.organization_id =" in sql
        assert "departments.property_id IS NULL" in sql
        assert "departments.property_id IN" in sql
        assert "properties.organization_id" in sql
        assert "properties.id =" in sql
