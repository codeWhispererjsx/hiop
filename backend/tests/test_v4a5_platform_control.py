from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.security import require_roles
from app.core.tenant import organization_context


class DB:
    def __init__(self,organization):self.organization=organization
    def get(self,_model,ident):return self.organization if ident==self.organization.id else None


def test_platform_role_is_explicit_and_does_not_inherit_organization_admin():
    platform=SimpleNamespace(role="platformadmin")
    assert require_roles(["platformadmin"])(platform) is platform
    with pytest.raises(HTTPException) as denied:require_roles(["admin"])(platform)
    assert denied.value.status_code==403


def test_organization_context_enforces_membership_and_suspension():
    org=SimpleNamespace(id=uuid4(),status="active")
    member=SimpleNamespace(role="viewer",organization_id=org.id)
    assert organization_context(DB(org),member,None)==org.id
    other=uuid4()
    assert organization_context(DB(org),SimpleNamespace(role="platformadmin",organization_id=None),org.id)==org.id
    assert organization_context(DB(org),member,other)==org.id
    org.status="suspended"
    with pytest.raises(HTTPException) as denied:organization_context(DB(org),member,None)
    assert denied.value.status_code==403


def test_platform_api_and_migration_are_non_destructive_and_tenant_aware():
    root=Path(__file__).parents[1]
    api=root.joinpath("app/api/v1/platform.py").read_text(encoding="utf-8")
    migration=root.joinpath("alembic/versions/v4a5b6c7d8e9_platform_control_center.py").read_text(encoding="utf-8").lower()
    for route in ("/organizations","/summary","/health","/audit","/users","/suspend","/activate","/administrator"):assert route in api
    assert 'require_roles(["platformadmin"])' in api
    assert "update properties set organization_id" in migration and "update managed_assets set organization_id" in migration
    assert "drop table" not in migration and "truncate" not in migration and "hashed_password" not in migration
