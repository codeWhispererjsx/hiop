from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.models.discovery_intelligence import DiscoveryEvidence
from app.models.device import Device
from app.services.active_directory_enrichment_service import (
    ActiveDirectoryDeviceEnrichmentService, ActiveDirectoryEnrichmentProvider,
    _department, _leaf_ou, safe_connection,
)
from app.services.device_enrichment_service import EnrichmentOutcome
from app.services.ldap_client import LdapError, LdapSearchResult


def connection():
    return SimpleNamespace(id="ad-1",name="Hotel AD",domain_name="adlosha.local",server_host="dc01.adlosha.local",server_port=636,use_ssl=True,use_start_tls=False,base_dn="DC=adlosha,DC=local",computer_search_base="OU=Computers,DC=adlosha,DC=local",bind_username="svc-hiop",authentication_method="ldaps",connection_timeout_seconds=10,page_size=100,enabled=True,verify_tls=True,ca_certificate_reference=None,encrypted_bind_secret="cipher",last_tested_at=None,last_test_status=None,last_test_message=None,created_at="now",updated_at="now")

def device(hostname="heloshaposbqt01"):
    return SimpleNamespace(id="result",primary_hostname=hostname,fqdn=f"{hostname}.adlosha.local" if hostname else None,description="Banquet POS Terminal 01",description_source="Manual",department="Banquet")

def directory_item(**changes):
    item={"sam_account_name":"HELOSHAPOSBQT01$","dns_hostname":"heloshaposbqt01.adlosha.local","distinguished_name":"CN=HELOSHAPOSBQT01,OU=POS,OU=Computers,DC=adlosha,DC=local","description":"Banquet POS Terminal 01","operating_system":"Windows 11 Enterprise","operating_system_version":"10.0 (22631)","enabled":True,"last_logon_at":datetime(2026,8,8,tzinfo=timezone.utc)};item.update(changes);return item

class Client:
    def __init__(self,items=None,error=None):self.items=items if items is not None else [directory_item()];self.error=error;self.closed=False
    def search_computers(self,*_args,**_kwargs):
        if self.error:raise self.error
        return LdapSearchResult(self.items,False,1)
    def close(self):self.closed=True

def provider_db():
    db=MagicMock();db.scalars.return_value.all.return_value=[connection()];return db

def run_provider(client,found_device=None):
    with patch("app.services.active_directory_enrichment_service.ActiveDirectoryConnectionService._bound_client",return_value=client):
        return ActiveDirectoryEnrichmentProvider(provider_db()).enrich(found_device or device())

def test_successful_ad_lookup_extracts_computer_description_ou_os_domain_and_evidence():
    outcome=run_provider(Client())
    assert outcome.status=="enriched" and outcome.attributes["computer_name"]=="HELOSHAPOSBQT01"
    assert outcome.attributes["organizational_unit"]=="POS" and outcome.attributes["operating_system"]=="Windows 11 Enterprise"
    assert outcome.attributes["domain"]=="ADLOSHA.LOCAL" and outcome.attributes["enabled"] is True
    assert {row["evidence_type"] for row in outcome.evidence}>={"ad_match","active_directory","description","organizational_unit","operating_system","domain","ad_description_agreement","ad_domain_match"}

def test_computer_not_found_and_nonmatching_hostname_are_safe_unavailable():
    assert run_provider(Client([])).error_category=="computer_not_found"
    assert run_provider(Client([directory_item(sam_account_name="OTHER$",dns_hostname="other.adlosha.local")])).error_category=="computer_not_found"

@pytest.mark.parametrize("category",["bind_failed","host_unreachable","timeout"])
def test_invalid_credentials_unavailable_and_timeout_do_not_break_discovery(category):
    outcome=run_provider(Client(error=LdapError(category,"Safe directory failure",retryable=category=="timeout")))
    assert outcome.status=="unavailable" and outcome.error_category==category and outcome.warnings==["Safe directory failure"]

def test_incomplete_and_disabled_computer_attributes_are_preserved_without_fabrication():
    outcome=run_provider(Client([directory_item(description=None,operating_system=None,operating_system_version=None,enabled=False)]))
    assert outcome.status=="partially_enriched" and outcome.attributes["description"] is None and outcome.attributes["enabled"] is False
    assert "The Active Directory computer account is disabled." in outcome.warnings

def test_ou_and_department_suggestion_are_deterministic():
    assert _leaf_ou("CN=PC1,OU=POS,OU=Computers,DC=example,DC=local")=="POS"
    assert _department("Banquet","POS Terminal 01") is None
    assert _department("POS",None) is None

def persisted_result():
    values={"id":"result","primary_hostname":"heloshaposbqt01","fqdn":"heloshaposbqt01.adlosha.local","description":"Administrator description","description_source":"Manual","department":"Front Office","operating_system":None,"review_status":"needs_review","confidence_score":20,"confidence_explanation":"[]","ad_enrichment_status":"not_attempted","ad_last_error":None,"ad_last_enriched_at":None}
    for field in ("ad_computer_name","ad_distinguished_name","ad_domain","ad_organizational_unit","ad_description","ad_operating_system","ad_operating_system_version","ad_enabled","ad_last_logon_at","suggested_department"):values[field]=None
    return SimpleNamespace(**values)

def test_persistence_records_evidence_updates_confidence_and_preserves_manual_values_without_duplicates():
    attrs={"computer_name":"HELOSHAPOSBQT01","description":"Banquet POS Terminal 01","suggested_department":"Banquet","operating_system":"Windows 11 Enterprise","enabled":True}
    provider=SimpleNamespace(name="Active Directory",enrich=lambda _result:EnrichmentOutcome("partially_enriched",attrs,[{"evidence_type":"ad_match","source":"active_directory","value":"HELOSHAPOSBQT01","verified":True}]))
    db=MagicMock();db.scalar.return_value=None;db.execute.return_value.all.return_value=[("ping_response",),("ad_match",)]
    result=persisted_result();response=ActiveDirectoryDeviceEnrichmentService(db,provider).enrich(result,SimpleNamespace(username="admin"))
    assert result.description=="Administrator description" and result.description_source=="Manual"
    assert result.department=="Front Office" and result.suggested_department=="Banquet"
    assert result.ad_description=="Banquet POS Terminal 01" and result.operating_system=="Windows 11 Enterprise"
    assert response["confidence_score"]==25
    added=[call.args[0] for call in db.add.call_args_list]
    assert any(isinstance(row,DiscoveryEvidence) for row in added) and not any(isinstance(row,Device) for row in added)

def test_safe_connection_response_never_exposes_bind_secret():
    payload=safe_connection(connection())
    assert payload["secret_configured"] is True
    assert not {"bind_secret","encrypted_bind_secret","password"}&payload.keys()
