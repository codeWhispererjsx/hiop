"""V3-ADMIN role, escalation, account-status, and audit contracts."""
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core import security
from app.core.access_control import ROLE_DEFINITIONS, SUPPORTED_ROLES
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.user import UserCreate, UserRoleUpdate, UserStatusUpdate, UserUpdate
from app.services import user_service


def actor(role, ident="actor"):
    return SimpleNamespace(id=ident, username=ident, role=role, is_active=True, organization_id=uuid4())


class Query:
    def filter(self,*args,**kwargs): return self
    def first(self): return None
    def count(self): return 2


class DB:
    def __init__(self): self.added=[]; self.commits=0
    def query(self,*args): return Query()
    def add(self,row):
        if getattr(row,"id",None) is None: row.id=str(uuid4())
        self.added.append(row)
    def flush(self): pass
    def commit(self): self.commits+=1
    def rollback(self): pass
    def refresh(self,row): pass


def test_four_minimal_roles_have_clear_permissions():
    assert SUPPORTED_ROLES == ("platformadmin","admin","technician","viewer")
    assert "platform.organizations.manage" in ROLE_DEFINITIONS["platformadmin"]["permissions"]
    assert "users.manage_operational" in ROLE_DEFINITIONS["admin"]["permissions"]
    assert "incidents.operate_assigned" in ROLE_DEFINITIONS["technician"]["permissions"]
    assert all(permission.endswith(".view") or permission == "data.view_all" for permission in ROLE_DEFINITIONS["viewer"]["permissions"])


def test_active_user_authenticates_and_inactive_user_is_rejected(monkeypatch):
    monkeypatch.setattr(security,"verify_password",lambda plain,hashed: plain=="ValidPassword1")
    active=SimpleNamespace(is_active=True,hashed_password="hash")
    inactive=SimpleNamespace(is_active=False,hashed_password="hash")
    assert security.authenticate_user(active,"ValidPassword1") is active
    assert security.authenticate_user(inactive,"ValidPassword1") is False


def test_platform_admin_does_not_inherit_organization_admin_operations():
    check=security.require_roles(["admin"])
    inner=check
    assert inner(actor("admin")).role == "admin"
    for role in ("platformadmin","technician","viewer"):
        with pytest.raises(HTTPException) as error: inner(actor(role))
        assert error.value.status_code == 403


def test_it_admin_can_create_operational_user_but_not_higher_account(monkeypatch):
    db=DB(); monkeypatch.setattr(user_service,"hash_password",lambda _:"secure-hash")
    created=user_service.create_user(db,UserCreate(username="tech01",email="tech01@example.com",password="ValidPassword1",role="technician"),actor("admin"))
    assert created.role=="technician" and created.hashed_password=="secure-hash"
    assert any(isinstance(row,AuditLog) and row.action=="USER_CREATED" for row in db.added)
    with pytest.raises(Exception): UserCreate(username="higher",email="higher@example.com",password="ValidPassword1",role="platformadmin")


def test_self_role_escalation_and_cross_role_escalation_are_blocked(monkeypatch):
    self_user=SimpleNamespace(id="same",username="same",role="technician",is_active=True,organization_id=uuid4())
    monkeypatch.setattr(user_service,"_get",lambda db,user_id:self_user)
    with pytest.raises(HTTPException) as error: user_service.set_role(DB(),"same",UserRoleUpdate(role="admin"),actor("technician","same"))
    assert error.value.status_code==403
    other=SimpleNamespace(id="other",username="other",role="viewer",is_active=True,organization_id=uuid4())
    monkeypatch.setattr(user_service,"_get",lambda db,user_id:other)
    with pytest.raises(HTTPException) as error: user_service.set_role(DB(),"other",UserRoleUpdate(role="technician"),actor("viewer"))
    assert error.value.status_code==403


def test_organization_admin_role_status_and_user_updates_are_audited(monkeypatch):
    org=uuid4();target=SimpleNamespace(id="target",username="target",email="target@example.com",role="viewer",is_active=True,organization_id=org)
    monkeypatch.setattr(user_service,"_get",lambda db,user_id:target)
    monkeypatch.setattr(user_service,"_ensure_unique",lambda *args:None)
    db=DB(); root=actor("admin","root");root.organization_id=org
    user_service.set_role(db,"target",UserRoleUpdate(role="technician"),root)
    user_service.set_status(db,"target",UserStatusUpdate(is_active=False),root)
    user_service.update_user(db,"target",UserUpdate(username="target2"),root)
    actions=[row.action for row in db.added if isinstance(row,AuditLog)]
    assert actions==["USER_ROLE_CHANGED","USER_DEACTIVATED","USER_UPDATED"]


def test_migration_preserves_accounts_and_maps_legacy_privilege_without_resetting_credentials():
    source=Path(__file__).parents[1].joinpath("alembic/versions/v3admin9e1f3a5b7_add_operational_roles.py").read_text(encoding="utf-8").lower()
    assert "update users set role = 'superadmin' where role = 'admin'" in source
    assert "delete from users" not in source and "hashed_password" not in source and "drop_table" not in source


def test_sensitive_user_api_has_no_permission_mutation_or_hard_delete_implementation():
    source=Path(__file__).parents[1].joinpath("app/users/routes.py").read_text(encoding="utf-8")
    assert 'admin = require_roles(["admin"])' in source
    assert "Compatibility route: retain the account and safely deactivate it" in source
    assert "db.delete" not in source
