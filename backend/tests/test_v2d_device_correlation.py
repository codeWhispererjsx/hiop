import json
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.models.discovery_intelligence import DiscoveryIdentityConflict
from app.services.device_correlation_service import CorrelationDecision,DeviceCorrelationService,confidence_level


def result(**changes):
    now=datetime.now(timezone.utc);values={"id":uuid4(),"canonical_result_id":None,"discovered_device_id":None,"ip_address":"10.50.21.45","mac_address":"AA:BB:CC:DD:EE:FF","primary_hostname":"heloshaposbqt01","fqdn":"heloshaposbqt01.adlosha.local","ad_computer_name":"HELOSHAPOSBQT01","serial_number":None,"identity_confirmed":False,"friendly_name":"POS Terminal 01","department":"Banquet","suggested_department":"Banquet","device_number":"01","description":"Banquet POS Terminal 01","description_source":"DHCP","location":None,"vendor":"HP","device_type":"Point of Sale","classification":"Point of Sale","operating_system":None,"model":None,"firmware":None,"sys_description":None,"sys_object_id":None,"uptime_seconds":None,"interface_count":None,"interface_information":"[]","ad_distinguished_name":None,"ad_domain":"ADLOSHA.LOCAL","ad_organizational_unit":"POS","ad_description":"Banquet POS Terminal 01","ad_operating_system":"Windows 11","ad_operating_system_version":None,"ad_enabled":True,"ad_last_logon_at":None,"first_seen_at":now-timedelta(days=1),"last_seen_at":now,"review_status":"needs_review","confidence_score":0,"confidence_level":"low","confidence_reason":"","confidence_explanation":"[]","conflict_status":"none"};values.update(changes);return SimpleNamespace(**values)


@pytest.mark.parametrize("changes,strength,identifier",[
    ({"ip_address":"10.50.21.60"},100,"mac"),
    ({"mac_address":None,"ip_address":"10.50.21.60","fqdn":None,"ad_computer_name":None},80,"hostname"),
    ({"mac_address":None,"primary_hostname":None,"ad_computer_name":None},75,"fqdn"),
    ({"mac_address":None,"primary_hostname":None,"fqdn":None,"ad_computer_name":None,"discovered_device_id":"stable-1"},95,"stable_discovery"),
])
def test_identity_matching_order(changes,strength,identifier):
    incoming=result(**changes);candidate=result(id=uuid4(),discovered_device_id="stable-1" if identifier=="stable_discovery" else None)
    decision=DeviceCorrelationService(None).compare(incoming,candidate)
    assert decision.matched and decision.strength==strength and identifier in decision.identifiers


def test_ip_alone_is_supporting_not_permanent_identity():
    left=result(mac_address=None,primary_hostname=None,fqdn=None,ad_computer_name=None);right=result(id=uuid4(),mac_address=None,primary_hostname=None,fqdn=None,ad_computer_name=None)
    decision=DeviceCorrelationService(None).compare(left,right)
    assert not decision.matched and decision.supporting==["ip_address"]


def test_conflicting_mac_prevents_hostname_only_merge():
    decision=DeviceCorrelationService(None).compare(result(mac_address="AA:AA:AA:AA:AA:AA"),result(id=uuid4(),mac_address="BB:BB:BB:BB:BB:BB"))
    assert not decision.matched and "conflicting_mac" in decision.supporting


class MergeHarness(DeviceCorrelationService):
    def __init__(self,root):super().__init__(MagicMock());self.candidate=root;self.changes=[]
    def find_match(self,_result):return CorrelationDecision(True,self.candidate,100,["mac"],[])
    def _history(self,root,attribute,previous,current,source):self.changes.append((attribute,previous,current,source))
    def refresh(self,result):return self.root(result)
    def root(self,row):return self.candidate if getattr(row,"canonical_result_id",None) else row


def test_same_mac_different_ip_merges_and_records_identity_history():
    root=result(ip_address="10.50.21.45",last_seen_at=datetime.now(timezone.utc)-timedelta(hours=1));incoming=result(id=uuid4(),ip_address="10.50.21.60")
    service=MergeHarness(root);merged=service.correlate(incoming)
    assert incoming.canonical_result_id==root.id and merged.ip_address=="10.50.21.60"
    assert ("ip_address","10.50.21.45","10.50.21.60","discovery") in service.changes


def test_manual_classification_survives_future_discovery_while_dynamic_ip_updates():
    root=result(identity_confirmed=True,classification="Administrator confirmed POS",device_type="Administrator confirmed POS",ip_address="10.50.21.45");incoming=result(id=uuid4(),classification="Switch",device_type="Switch",ip_address="10.50.21.60")
    merged=MergeHarness(root).correlate(incoming)
    assert merged.classification=="Administrator confirmed POS" and merged.ip_address=="10.50.21.60"


def evidence(kind,source,value,weight=0):return SimpleNamespace(evidence_type=kind,source=source,value=json.dumps(value),weight=weight,verified=False,observed_at=datetime.now(timezone.utc))


class ConfidenceHarness(DeviceCorrelationService):
    def __init__(self,root,rows,open_conflicts=0):super().__init__(None);self._root=root;self._rows=rows;self._open=[object() for _ in range(open_conflicts)]
    def root(self,_result):return self._root
    def evidence(self,_result):return self._rows
    def conflicts(self,_result,open_only=False):return self._open if open_only else self._open


def test_confidence_single_source_stays_low_and_unresolved_stays_genuine():
    root=result(mac_address=None,primary_hostname=None,fqdn=None,ad_computer_name=None,identity_confirmed=False)
    score=ConfidenceHarness(root,[evidence("ping_response","icmp","online")]).calculate_confidence(root)
    assert score["score"]==15 and score["level"]=="low"
    empty=ConfidenceHarness(root,[]).calculate_confidence(root)
    assert empty["score"]==0 and "insufficient" in empty["reason"].lower()


def test_two_agreeing_sources_reach_explainable_medium_confidence():
    root=result();rows=[evidence("hostname_match","dns","heloshaposbqt01"),evidence("ad_match","active_directory","HELOSHAPOSBQT01")]
    score=ConfidenceHarness(root,rows).calculate_confidence(root)
    assert score["score"]==35 and score["level"]=="medium" and score["agreement_bonus"]==10


def test_multiple_sources_raise_confidence_without_fake_precision():
    rows=[evidence("ping_response","icmp","online"),evidence("mac_address","arp","AA:BB:CC:DD:EE:FF"),evidence("mac_address","dhcp","AA-BB-CC-DD-EE-FF"),evidence("hostname_match","dns","host1"),evidence("ad_match","active_directory","HOST1"),evidence("description","dhcp","POS 1"),evidence("description","active_directory","POS 1"),evidence("snmp","snmp_read_only","1.3.6")]
    root=result();score=ConfidenceHarness(root,rows).calculate_confidence(root)
    assert score["level"] in {"high","very_high"} and score["score"]<=95 and score["agreement_bonus"]==20


def test_conflicts_reduce_confidence_deterministically():
    rows=[evidence("ping_response","icmp","online"),evidence("mac_address","arp","AA:BB:CC:DD:EE:FF"),evidence("hostname_match","dns","host1"),evidence("snmp","snmp_read_only","1.3.6")]
    root=result();clean=ConfidenceHarness(root,rows).calculate_confidence(root)["score"];conflicted=ConfidenceHarness(root,rows,2).calculate_confidence(root)
    assert conflicted["score"]==max(0,clean-30) and conflicted["conflict_penalty"]==30


def test_manual_confirmation_is_preserved_and_can_reach_very_high():
    rows=[evidence("ping_response","icmp","online"),evidence("mac_address","arp","AA:BB:CC:DD:EE:FF"),evidence("hostname_match","dns","host1"),evidence("description","dhcp","POS 1"),evidence("snmp","snmp_read_only","oid"),evidence("manual_confirmation","administrator",{"device_type":"POS"})]
    root=result(identity_confirmed=True);score=ConfidenceHarness(root,rows).calculate_confidence(root)
    assert score["level"]=="very_high" and "administrator-confirmed" in score["reason"].lower()


def test_conflict_records_preserve_both_sources_and_are_idempotent():
    db=MagicMock();db.scalar.return_value=None;service=DeviceCorrelationService(db);root=result()
    service._conflict(root,"description","Banquet POS","DHCP","Front Office PC","Active Directory")
    conflict=db.add.call_args.args[0]
    assert isinstance(conflict,DiscoveryIdentityConflict) and conflict.left_source=="DHCP" and conflict.right_source=="Active Directory"
    db.scalar.return_value=conflict;service._conflict(root,"description","Banquet POS","DHCP","Front Office PC","Active Directory")
    assert db.add.call_count==1


def test_dns_ad_hostname_snmp_type_and_dhcp_ad_description_conflicts_are_visible():
    class ConflictHarness(DeviceCorrelationService):
        def __init__(self,root,rows):super().__init__(MagicMock());self._root=root;self._rows=rows;self.detected=[]
        def root(self,_result):return self._root
        def evidence(self,_result):return self._rows
        def conflicts(self,_result,open_only=False):return []
        def _conflict(self,_root,attribute,left,left_source,right,right_source):
            if left and right and str(left).casefold()!=str(right).casefold():self.detected.append((attribute,left_source,right_source))
    root=result(primary_hostname="dns-pos-01",ad_computer_name="AD-SW-01",description="Banquet POS",description_source="DHCP",ad_description="Front Office Switch")
    rows=[evidence("hostname_rule","hostname_rule",{"device_type":"Point of Sale"}),evidence("device_type","snmp","Switch")]
    service=ConflictHarness(root,rows);service.detect_conflicts(root)
    assert ("hostname","DNS/discovery","Active Directory") in service.detected
    assert ("description","DHCP","Active Directory") in service.detected
    assert ("device_type","hostname_rule","snmp") in service.detected


def test_confidence_bands_are_human_readable():
    assert [confidence_level(score) for score in (0,30,60,85)]==["low","medium","high","very_high"]
