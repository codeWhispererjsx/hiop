from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.api.v1.discovery_intelligence import ApproveWrite, approve_result
from app.models.device import Device
from app.models.discovered_device import DiscoveredDevice
from app.models.discovery_intelligence import DiscoveryResult


def _result():
    return SimpleNamespace(
        id=uuid4(), discovered_device_id=uuid4(), mac_address="AA:BB:CC:DD:EE:FF",
        primary_hostname="heloshaposbqt01", ad_computer_name="HELOSHAPOSBQT01",
        friendly_name="POS Terminal 01", classification="Point of Sale",
        device_type="Point of Sale", vendor="HP", model="EliteDesk 800",
        serial_number="SN-123", department="Banquet", location="Ballroom",
        ip_address="10.50.21.45", description="Banquet POS Terminal 01",
        description_source="DHCP", ad_distinguished_name=None, ad_domain="ADLOSHA.LOCAL",
        ad_organizational_unit="POS", ad_description="Banquet POS Terminal 01",
        ad_operating_system="Windows 11 Enterprise", ad_operating_system_version="23H2",
        ad_enabled=True, ad_last_logon_at=None, review_status="automatically_identified",
    )


def test_approval_retains_enriched_identity_and_is_idempotent():
    row=_result(); discovered=SimpleNamespace(approved_device_id=None,review_status="pending",reviewed_by=None,reviewed_at=None)
    db=MagicMock(); managed=[]
    def add(value):
        if isinstance(value,Device):
            value.id=uuid4();managed.append(value)
    db.add.side_effect=add
    def get(model,identifier):
        if model is DiscoveryResult:return row
        if model is DiscoveredDevice:return discovered
        if model is Device and managed and identifier==managed[0].id:return managed[0]
        return None
    db.get.side_effect=get
    db.query.return_value.join.return_value.filter.return_value.first.return_value=None
    db.query.return_value.filter.return_value.first.return_value=None
    correlation=MagicMock();correlation.root.return_value=row;correlation.group_ids.return_value=[row.id]
    actor=SimpleNamespace(id="admin",username="admin")
    with patch("app.api.v1.discovery_intelligence.DeviceCorrelationService",return_value=correlation):
        first=approve_result(row.id,ApproveWrite(),db,actor)
        second=approve_result(row.id,ApproveWrite(),db,actor)
    assert first is second and len(managed)==1
    assert first.hostname=="heloshaposbqt01" and first.model=="EliteDesk 800" and first.serial_number=="SN-123"
    assert first.department=="Banquet" and first.location=="Ballroom"
    assert discovered.approved_device_id==first.id
