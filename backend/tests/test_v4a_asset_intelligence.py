from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.security import require_roles
from app.models.asset_intelligence import ManagedAsset
from app.schemas.asset_intelligence import AssetCreate, AssetUpdate
from app.services import asset_intelligence_service as service


class Rows:
    def __init__(self,rows):self.rows=rows
    def all(self):return self.rows


class DB:
    def __init__(self,rows=None):self.rows=rows or [];self.added=[];self.commits=0
    def add(self,row):
        if getattr(row,"id",None) is None:row.id=uuid4()
        self.added.append(row);self.rows.append(row)
    def flush(self):pass
    def commit(self):self.commits+=1
    def rollback(self):pass
    def refresh(self,row):pass
    def scalars(self,query):return Rows(self.rows)


actor=SimpleNamespace(id="admin-id",username="admin",role="admin",organization_id=uuid4())


def test_manual_asset_requires_only_name_type_and_status():
    row=AssetCreate(name="Offline laptop",device_type="Laptop",status="planned")
    assert row.asset_tag is None and row.vendor is None and row.status=="planned"


def test_all_four_v4a_statuses_are_supported():
    for status in ("planned","active","in_maintenance","retired"):
        assert AssetCreate(name="Asset",device_type="Other",status=status).status==status
    with pytest.raises(ValueError):AssetCreate(name="Asset",device_type="Other",status="disposed")


def test_manual_asset_creation_is_stable_and_audited(monkeypatch):
    db=DB();monkeypatch.setattr(service,"_next_number",lambda _db:"HIOP-000123");audits=[];monkeypatch.setattr(service,"create_audit_log",lambda *args,**kwargs:audits.append((args,kwargs)))
    row=service.create_asset(db,AssetCreate(name="Test laptop",device_type="Laptop"),actor)
    assert row.asset_number=="HIOP-000123" and row.device_id is None and db.commits==1 and audits


def test_asset_updates_preserve_technical_identity_and_audit(monkeypatch):
    row=ManagedAsset(id=uuid4(),asset_number="HIOP-000001",name="POS",device_type="POS Terminal",status="active",ci_category="device",source="discovery",field_sources={},created_by="admin-id")
    db=DB([row]);monkeypatch.setattr(service,"create_audit_log",lambda *args,**kwargs:None)
    service.update_asset(db,row,AssetUpdate(business_owner="Restaurant Operations",technical_owner="IT Infrastructure",status="in_maintenance"),actor)
    assert row.business_owner=="Restaurant Operations" and row.technical_owner=="IT Infrastructure" and row.status=="in_maintenance" and row.field_sources["business_owner"]=="Manual"


def test_search_and_filters_cover_required_asset_identity(monkeypatch):
    rows=[SimpleNamespace(key="a"),SimpleNamespace(key="b")];db=DB(rows)
    payloads={"a":{"asset_number":"HIOP-000001","asset_tag":"LC-POS-001","name":"Restaurant POS","hostname":"pos01","ip_address":"10.0.0.10","mac_address":"AA:BB:CC:DD:EE:FF","serial_number":"SER1","status":"active","device_type":"POS Terminal","department":"Food & Beverage","location":"Restaurant","health":"Healthy","vendor":"Dell"},"b":{"asset_number":"HIOP-000002","asset_tag":None,"name":"Spare","hostname":None,"ip_address":None,"mac_address":None,"serial_number":None,"status":"planned","device_type":"Laptop","department":None,"location":None,"health":"Unknown","vendor":None}}
    monkeypatch.setattr(service,"present",lambda _db,row:payloads[row.key])
    for query in ("HIOP-000001","LC-POS-001","pos01","10.0.0.10","AA:BB","SER1"):
        assert len(service.list_assets(db,search=query))==1
    assert len(service.list_assets(db,status="active",device_type="POS Terminal",department="Food & Beverage",location="Restaurant",health="Healthy",vendor="Dell"))==1


def test_asset_write_authorization_excludes_technician_and_viewer():
    check=require_roles(["admin","superadmin"])
    assert check(actor).role=="admin"
    for role in ("technician","viewer"):
        with pytest.raises(HTTPException) as error:check(SimpleNamespace(role=role))
        assert error.value.status_code==403


def test_migration_is_non_destructive_and_backfills_existing_device_ids():
    source=Path(__file__).parents[1].joinpath("alembic/versions/v4a1b2c3d4e5_add_managed_assets.py").read_text(encoding="utf-8").lower()
    assert "from devices" in source and "device_id" in source and "managed_asset_number_seq" in source
    assert "drop_table(\"devices\")" not in source and "delete from devices" not in source


def test_asset_model_prevents_duplicate_device_asset_tag_and_number():
    names={constraint.name for constraint in ManagedAsset.__table__.constraints}
    assert {"uq_managed_asset_device","uq_managed_asset_tag","uq_managed_asset_number"}<=names
