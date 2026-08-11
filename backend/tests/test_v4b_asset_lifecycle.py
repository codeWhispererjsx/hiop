from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.asset_intelligence import AssetLifecycleEvent, ManagedAsset
from app.schemas.asset_intelligence import AssetCreate, AssetUpdate, LifecycleTransition
from app.services import asset_intelligence_service as service


class DB:
    def __init__(self): self.added=[]; self.commits=0
    def add(self,row):
        if getattr(row,"id",None) is None: row.id=uuid4()
        self.added.append(row)
    def commit(self): self.commits+=1
    def refresh(self,row): pass


actor=SimpleNamespace(id="admin-id",username="admin@example.com",role="admin",organization_id=uuid4())


def asset(status="active"):
    return ManagedAsset(id=uuid4(),organization_id=actor.organization_id,asset_number="HIOP-900001",name="Lifecycle test asset",device_type="Laptop",status=status,ci_category="device",source="manual",field_sources={},created_by=actor.id)


def test_all_v4b_lifecycle_states_and_conditions_validate():
    for status in ("planned","received","deployed","active","in_maintenance","retired"):
        assert AssetCreate(name="Asset",device_type="Other",status=status).status==status
    for condition in ("new","good","fair","poor","damaged"):
        assert AssetCreate(name="Asset",device_type="Other",condition=condition).condition==condition


@pytest.mark.parametrize("before,after",[("planned","received"),("received","deployed"),("deployed","active"),("active","in_maintenance"),("in_maintenance","active"),("active","retired"),("retired","active")])
def test_allowed_transitions_preserve_history(monkeypatch,before,after):
    db=DB();row=asset(before);monkeypatch.setattr(service,"create_audit_log",lambda *args,**kwargs:None)
    payload=LifecycleTransition(status=after,reason="replaced" if after=="retired" else "Lifecycle test")
    service.transition_asset(db,row,payload,actor)
    event=next(item for item in db.added if isinstance(item,AssetLifecycleEvent))
    assert row.status==after and event.previous_status==before and event.new_status==after and event.changed_by_name==actor.username and db.commits==1


def test_retirement_requires_reason_and_does_not_delete_asset(monkeypatch):
    row=asset();db=DB();monkeypatch.setattr(service,"create_audit_log",lambda *args,**kwargs:None)
    with pytest.raises(HTTPException):service.transition_asset(db,row,LifecycleTransition(status="retired"),actor)
    assert row.status=="active"


def test_invalid_transition_and_invalid_dates_are_rejected():
    with pytest.raises(HTTPException):service.transition_asset(DB(),asset("planned"),LifecycleTransition(status="active"),actor)
    with pytest.raises(HTTPException):service._validate_dates({"acquisition_date":date(2026,4,2),"received_date":date(2026,4,1)})
    with pytest.raises(HTTPException):service._validate_dates({"warranty_start":date(2026,4,2),"warranty_end":date(2026,4,1)})


def test_lifecycle_fields_keep_health_separate():
    payload=AssetUpdate(condition="good",acquisition_date=date(2026,1,1),warranty_start=date(2026,1,1),warranty_end=date(2027,1,1),expected_replacement_date=date(2029,1,1))
    assert payload.condition=="good" and not hasattr(payload,"health")

