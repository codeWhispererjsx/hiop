from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.api.v1.discovery_intelligence import safe_snmp_credential
from app.services.device_enrichment_service import (
    DeviceEnrichmentService, EnrichmentOutcome, SNMPEnrichmentProvider,
    _device_type, _vendor,
)
from app.services.snmp_client_service import SNMPClientError

def value(text=None,numeric=None,seconds=None,quality="good",oid="1.2.3.1"):
    return SimpleNamespace(value_text=text,value_numeric=numeric,seconds=seconds,quality=quality,oid=oid)

def target():
    return SimpleNamespace(id="target",credential=object(),detected_profile_id=None,discovered_device_id="legacy",ip_address="10.0.0.8",last_test_status=None,last_test_message=None,last_tested_at=None,detected_sys_object_id=None)

class SuccessfulClient:
    def __init__(self,*args,**kwargs):self.closed=False
    def get_system_identity(self):
        return {"system.name":value("edge-sw-01"),"system.description":value("HP ProCurve network switch"),"system.object_id":value("1.3.6.1.4.1.11"),"system.uptime":value(numeric=987650,seconds=9876.5)}
    def get_many(self,_oids):return [value("HP"),value("J9773A"),value("SERIAL-1"),value("YA.16.11")]
    def get_interfaces_preview(self,**_kwargs):
        return {"interface.name":SimpleNamespace(items=[value("Gi1",oid="1.3.6.1.2.1.31.1.1.1.1.1")]),"interface.description":SimpleNamespace(items=[]),"interface.admin_status":SimpleNamespace(items=[value(numeric=1,oid="1.3.6.1.2.1.2.2.1.7.1")]),"interface.oper_status":SimpleNamespace(items=[value(numeric=1,oid="1.3.6.1.2.1.2.2.1.8.1")])}
    def close(self):self.closed=True

def provider_db(row):
    db=MagicMock();db.scalar.return_value=row;db.get.return_value=None;return db

@patch("app.services.device_enrichment_service.read_discovery",return_value={"authorized_cidr_ranges":"10.0.0.0/24","ignore_ranges":""})
def test_successful_snmp_enrichment_extracts_identity_hardware_health_network_and_evidence(_settings):
    outcome=SNMPEnrichmentProvider(provider_db(target()),client_factory=SuccessfulClient).enrich(SimpleNamespace(ip_address="10.0.0.8",discovered_device_id="legacy",primary_hostname="edge-sw-01.example.test"))
    assert outcome.status=="enriched"
    assert outcome.attributes|{"vendor":"HP","model":"J9773A","serial_number":"SERIAL-1","firmware":"YA.16.11","uptime_seconds":9876.5,"device_type":"Switch"}==outcome.attributes
    assert outcome.attributes["interface_count"]==1 and outcome.attributes["interfaces"][0]["name"]=="Gi1"
    assert {item["evidence_type"] for item in outcome.evidence}>={"snmp","vendor_match","model","serial_number","firmware","uptime_seconds","hostname_match"}

def test_snmp_unavailable_without_target_does_not_fail_discovery():
    outcome=SNMPEnrichmentProvider(provider_db(None)).enrich(SimpleNamespace(ip_address="10.0.0.9",discovered_device_id=None))
    assert outcome.status=="unavailable" and outcome.error_category=="target_missing"

@pytest.mark.parametrize("category",["timeout","authentication_failed"])
@patch("app.services.device_enrichment_service.read_discovery",return_value={"authorized_cidr_ranges":"10.0.0.0/24","ignore_ranges":""})
def test_snmp_timeout_and_invalid_credentials_are_safe_unavailable(_settings,category):
    class FailedClient:
        def __init__(self,*args,**kwargs):pass
        def get_system_identity(self):raise SNMPClientError(category,"Safe SNMP failure")
        def close(self):pass
    outcome=SNMPEnrichmentProvider(provider_db(target()),client_factory=FailedClient).enrich(SimpleNamespace(ip_address="10.0.0.8",discovered_device_id="legacy"))
    assert outcome.status=="unavailable" and outcome.error_category==category and outcome.warnings==["Safe SNMP failure"]

@patch("app.services.device_enrichment_service.read_discovery",return_value={"authorized_cidr_ranges":"10.0.0.0/24","ignore_ranges":""})
def test_partial_snmp_response_is_not_fabricated(_settings):
    class PartialClient(SuccessfulClient):
        def get_many(self,_oids):return [value("HP"),value(quality="missing"),value(quality="missing"),value(quality="missing")]
    outcome=SNMPEnrichmentProvider(provider_db(target()),client_factory=PartialClient).enrich(SimpleNamespace(ip_address="10.0.0.8",discovered_device_id="legacy"))
    assert outcome.status=="partially_enriched" and outcome.attributes["model"] is None
    assert "Model unavailable." in outcome.warnings

def test_vendor_and_conservative_device_type_extraction():
    assert _vendor(None,"Hewlett-Packard LaserJet") == "HP"
    assert _device_type("Cisco managed switch") == "Switch"
    assert _device_type("multi-purpose switch router appliance") is None

def test_enrichment_service_persists_evidence_and_updates_confidence_without_duplicate_device():
    db=MagicMock();db.scalar.return_value=None;db.execute.return_value.all.return_value=[("ping_response",),("snmp",),("vendor_match",)]
    provider=SimpleNamespace(name="SNMP",enrich=lambda _device:EnrichmentOutcome("partially_enriched",{"vendor":"HP","model":"X1","interfaces":[]},[{"evidence_type":"snmp","source":"snmp_read_only","value":"1.2.3","verified":True},{"evidence_type":"vendor_match","source":"snmp","value":"HP","verified":True}]))
    result=SimpleNamespace(id="result",ip_address="10.0.0.8",primary_hostname="host",device_type="Unknown Device",classification="Unknown Device",review_status="needs_review",snmp_enrichment_status="not_attempted",snmp_last_error=None,last_enriched_at=None,vendor=None,model=None,serial_number=None,firmware=None,sys_description=None,sys_object_id=None,uptime_seconds=None,interface_count=None,interface_information="[]",confidence_score=15,confidence_explanation="[]")
    response=DeviceEnrichmentService(db,provider).enrich(result,SimpleNamespace(username="admin"))
    assert result.model=="X1" and result.vendor=="HP" and result.confidence_score==45
    assert response["evidence_added"]==2 and db.add.call_count>=2

def test_credential_response_never_exposes_encrypted_or_plaintext_secrets():
    row=SimpleNamespace(id="id",name="hotel-readonly",version="v2c",username=None,authentication_protocol="none",privacy_protocol="none",security_level="noAuthNoPriv",context_name=None,enabled=True,description=None,community_encrypted="cipher",authentication_secret_encrypted=None,privacy_secret_encrypted=None,created_at="now",updated_at="now")
    payload=safe_snmp_credential(row)
    assert payload["has_community"] is True
    assert not {"community","community_encrypted","authentication_secret","privacy_secret"}&payload.keys()
