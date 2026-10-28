from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.discovery_intelligence import ApproveWrite, approve_result
from app.models.device import Device
from app.models.asset_intelligence import ManagedAsset
from app.models.discovered_device import DiscoveredDevice
from app.models.discovery_intelligence import DiscoveryApprovalLink, DiscoveryResult
from app.schemas.device import DeviceCreate, DeviceUpdate


def _result(discovered_device_id=None, serial_number="SN-123"):
    return SimpleNamespace(
        id=uuid4(), discovered_device_id=discovered_device_id, mac_address="AA:BB:CC:DD:EE:FF",
        primary_hostname="heloshaposbqt01", ad_computer_name="HELOSHAPOSBQT01",
        friendly_name="POS Terminal 01", classification="Point of Sale",
        device_type="Point of Sale", vendor="HP", model="EliteDesk 800",
        serial_number=serial_number, department="Banquet", location="Ballroom",
        suggested_department=None,
        ip_address="10.50.21.45", description="Banquet POS Terminal 01",
        description_source="DHCP", ad_distinguished_name=None, ad_domain="ADLOSHA.LOCAL",
        ad_organizational_unit="POS", ad_description="Banquet POS Terminal 01",
        ad_operating_system="Windows 11 Enterprise", ad_operating_system_version="23H2",
        ad_enabled=True, ad_last_logon_at=None, review_status="automatically_identified",
        identity_confirmed=True, confidence_score=50, property_id=None,
    )


def test_serial_number_can_be_omitted_or_cleared():
    payload=DeviceCreate(
        asset_tag="HIOP-001",hostname="host-1",device_type="Desktop",brand="Dell",
        model="OptiPlex",department="IT",location="Office",ip_address="10.0.0.2",
        serial_number=None,
    )
    assert payload.serial_number is None
    assert DeviceUpdate(serial_number=None).model_dump(exclude_unset=True)=={"serial_number":None}


@pytest.mark.parametrize("serial_number", ["SN-123", None])
@pytest.mark.parametrize("has_legacy_discovery", [True, False])
def test_approval_retains_enriched_identity_and_is_idempotent(serial_number, has_legacy_discovery):
    row=_result(discovered_device_id=uuid4() if has_legacy_discovery else None, serial_number=serial_number)
    row.property_id=uuid4()
    discovered=SimpleNamespace(approved_device_id=None,review_status="pending",reviewed_by=None,reviewed_at=None) if has_legacy_discovery else None
    approval_links={}
    db=MagicMock(); managed=[]
    def add(value):
        if isinstance(value,Device):
            value.id=uuid4();managed.append(value)
        elif isinstance(value,DiscoveryApprovalLink):
            approval_links[value.result_id]=value
    db.add.side_effect=add
    def get(model,identifier):
        if model is DiscoveryResult:return row
        if model is DiscoveryApprovalLink:return approval_links.get(identifier)
        if model is DiscoveredDevice:return discovered
        if model is Device and managed and identifier==managed[0].id:return managed[0]
        return None
    db.get.side_effect=get
    db.query.return_value.join.return_value.filter.return_value.first.return_value=None
    db.query.return_value.join.return_value.filter.return_value.filter.return_value.first.return_value=None
    db.query.return_value.filter.return_value.first.return_value=None
    db.query.return_value.filter.return_value.populate_existing.return_value.with_for_update.return_value.first.return_value=row
    correlation=MagicMock();correlation.root.return_value=row;correlation.group_ids.return_value=[row.id]
    correlation.conflicts.return_value=[]
    actor=SimpleNamespace(id="admin",username="admin")
    organization_id=uuid4()
    with patch("app.api.v1.discovery_intelligence.DeviceCorrelationService",return_value=correlation), \
         patch("app.api.v1.discovery_intelligence.scoped_result",return_value=row), \
         patch("app.api.v1.discovery_intelligence.create_audit_log") as audit, \
         patch("app.api.v1.discovery_intelligence.ensure_asset_for_device",return_value=SimpleNamespace(name="")):
        first=approve_result(row.id,ApproveWrite(),db,actor,organization_id,None)
        second=approve_result(row.id,ApproveWrite(),db,actor,organization_id,None)
    assert first is second and len(managed)==1
    assert first.hostname=="heloshaposbqt01" and first.model=="EliteDesk 800" and first.serial_number==serial_number
    assert first.department=="Banquet" and first.location=="Ballroom"
    assert approval_links[row.id].device_id==first.id
    if discovered:assert discovered.approved_device_id==first.id
    audit.assert_called_once()
    assert audit.call_args.kwargs["organization_id"]==organization_id
    assert audit.call_args.kwargs["property_id"]==row.property_id


@pytest.mark.parametrize(
    ("identity_confirmed", "confidence_score", "conflicts", "reason"),
    [
        (False, 59, [], "60%"),
        (True, 99, [SimpleNamespace(status="open")], "conflicts"),
    ],
)
def test_approval_rejects_ineligible_identity(identity_confirmed, confidence_score, conflicts, reason):
    row=_result();row.identity_confirmed=identity_confirmed;row.confidence_score=confidence_score
    db=MagicMock()
    db.get.return_value=None
    db.query.return_value.filter.return_value.populate_existing.return_value.with_for_update.return_value.first.return_value=row
    correlation=MagicMock();correlation.root.return_value=row;correlation.conflicts.return_value=conflicts
    actor=SimpleNamespace(id="admin",username="admin")
    with patch("app.api.v1.discovery_intelligence.DeviceCorrelationService",return_value=correlation), \
         patch("app.api.v1.discovery_intelligence.scoped_result",return_value=row):
        with pytest.raises(HTTPException) as error:
            approve_result(row.id,ApproveWrite(),db,actor,None,None)
    assert error.value.status_code==409
    assert reason in error.value.detail


def test_approval_links_the_selected_uploaded_asset_instead_of_creating_another():
    row=_result(serial_number="SN-123")
    row.property_id=uuid4()
    row.department=None
    row.location=None
    organization_id=uuid4()
    asset=SimpleNamespace(
        id=uuid4(),organization_id=organization_id,property_id=row.property_id,
        source="inventory_import",device_id=None,status="active",
        asset_number="HIOP-000042",asset_tag="TAG-42",name="heloshaposbqt01",
        device_type="Desktop",vendor="Dell",model="OptiPlex",serial_number="SN-123",
        department_name="Banquet",location_name="Ballroom",description=None,updated_by=None,
    )
    approval_links={}
    db=MagicMock()
    managed=[]
    def add(value):
        if isinstance(value,Device):
            value.id=uuid4()
            managed.append(value)
        elif isinstance(value,DiscoveryApprovalLink):
            approval_links[value.result_id]=value
    db.add.side_effect=add
    def get(model,identifier):
        if model is DiscoveryResult:return row
        if model is DiscoveryApprovalLink:return approval_links.get(identifier)
        if model is Device and managed and identifier==managed[0].id:return managed[0]
        return None
    db.get.side_effect=get
    db.query.return_value.join.return_value.filter.return_value.first.return_value=None
    db.query.return_value.join.return_value.filter.return_value.filter.return_value.first.return_value=None
    db.query.return_value.filter.return_value.first.return_value=None
    db.query.return_value.filter.return_value.populate_existing.return_value.with_for_update.return_value.first.return_value=row
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value=asset
    correlation=MagicMock()
    correlation.root.return_value=row
    correlation.group_ids.return_value=[row.id]
    correlation.conflicts.return_value=[]
    actor=SimpleNamespace(id="admin",username="admin")
    candidate={"asset_id":str(asset.id),"asset_number":asset.asset_number,"name":asset.name,"department":asset.department_name,"location":asset.location_name,"matched_fields":["hostname","serial_number"]}
    with patch("app.api.v1.discovery_intelligence.DeviceCorrelationService",return_value=correlation), \
         patch("app.api.v1.discovery_intelligence.scoped_result",return_value=row), \
         patch("app.api.v1.discovery_intelligence.imported_asset_candidates_for_result",return_value=[candidate]), \
         patch("app.api.v1.discovery_intelligence.DeviceIdentityService"), \
         patch("app.api.v1.discovery_intelligence.create_audit_log"), \
         patch("app.api.v1.discovery_intelligence.ensure_asset_for_device") as ensure_asset:
        device=approve_result(row.id,ApproveWrite(managed_asset_id=asset.id),db,actor,organization_id,None)
    assert device.hostname=="heloshaposbqt01"
    assert device.department=="Banquet"
    assert device.location=="Ballroom"
    assert asset.device_id==device.id
    assert approval_links[row.id].device_id==device.id
    ensure_asset.assert_not_called()


def test_approval_requires_explicit_review_when_an_uploaded_asset_matches():
    row=_result(serial_number="SN-123")
    row.property_id=uuid4()
    row.identity_confirmed=True
    row.confidence_score=99
    candidate={"asset_id":str(uuid4()),"asset_number":"HIOP-000042","name":row.primary_hostname,"department":"Banquet","location":"Ballroom","matched_fields":["hostname"]}
    db=MagicMock()
    db.get.return_value=None
    db.query.return_value.filter.return_value.populate_existing.return_value.with_for_update.return_value.first.return_value=row
    correlation=MagicMock()
    correlation.root.return_value=row
    correlation.group_ids.return_value=[row.id]
    correlation.conflicts.return_value=[]
    actor=SimpleNamespace(id="admin",username="admin")
    with patch("app.api.v1.discovery_intelligence.DeviceCorrelationService",return_value=correlation), \
         patch("app.api.v1.discovery_intelligence.scoped_result",return_value=row), \
         patch("app.api.v1.discovery_intelligence.imported_asset_candidates_for_result",return_value=[candidate]):
        with pytest.raises(HTTPException,match="choose Link to uploaded asset") as error:
            approve_result(row.id,ApproveWrite(),db,actor,uuid4(),None)
    assert error.value.status_code==409
