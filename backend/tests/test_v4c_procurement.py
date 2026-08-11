from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi import HTTPException
from app.models.procurement import AssetProcurement,ProcurementAssetLink,ProcurementLineItem
from app.schemas.procurement import ProcurementCreate,ProcurementItemCreate
from app.services import procurement_service as service

actor=SimpleNamespace(id="admin",username="admin@example.com",role="admin")
class DB:
    def __init__(self):self.added=[];self.commits=0
    def add(self,row):self.added.append(row)
    def commit(self):self.commits+=1
    def refresh(self,row):pass
def record(status="draft"):return AssetProcurement(id=uuid4(),organization_id=uuid4(),procurement_number="PO-000001",title="Test POS Acquisition",status=status,requested_by="admin",currency="NGN")
def test_multiple_items_and_decimal_cost_validate():
    payload=ProcurementCreate(title="POS replacement",currency="NGN",items=[ProcurementItemCreate(description="POS",quantity_requested=2,unit_cost=Decimal("450000.25")),ProcurementItemCreate(description="Printer",quantity_requested=1,unit_cost=Decimal("80000.10"))])
    assert len(payload.items)==2 and payload.items[0].unit_cost*2==Decimal("900000.50")
def test_supported_currencies_and_invalid_currency():
    for currency in ("NGN","USD","EUR","GBP"):assert ProcurementCreate(title="Request",currency=currency,items=[ProcurementItemCreate(description="Item",quantity_requested=1)]).currency==currency
    with pytest.raises(ValueError):ProcurementCreate(title="Request",currency="BTC",items=[ProcurementItemCreate(description="Item",quantity_requested=1)])
@pytest.mark.parametrize("before,target",[("draft","requested"),("requested","approved"),("approved","ordered"),("ordered","partially_received"),("partially_received","received")])
def test_procurement_workflow_is_audited(monkeypatch,before,target):
    db=DB();row=record(before);monkeypatch.setattr(service,"_event",lambda *args,**kwargs:db.added.append((args,kwargs)))
    service.transition(db,row,target,actor)
    assert row.status==target and db.commits==1 and db.added
def test_invalid_transition_is_rejected():
    with pytest.raises(HTTPException):service.transition(DB(),record("draft"),"approved",actor)
def test_received_quantity_constraint_and_unique_asset_link_are_database_enforced():
    checks=" ".join(str(x.sqltext) for x in ProcurementLineItem.__table__.constraints if hasattr(x,"sqltext"))
    assert "quantity_received <= quantity_requested" in checks
    names={x.name for x in ProcurementAssetLink.__table__.constraints};assert "uq_procurement_asset_link_asset" in names
def test_migration_is_additive_and_preserves_v4b():
    source=Path(__file__).parents[1].joinpath("alembic/versions/v4c7d8e9f0a1_procurement.py").read_text().lower()
    for forbidden in ("drop_table(\"managed_assets\"","delete from managed_assets","drop_table(\"asset_lifecycle_events\""):assert forbidden not in source
