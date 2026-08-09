from app.models.discovery_intelligence import DiscoveryCredential,DiscoveryEvidence,DiscoveryFingerprint,DiscoveryJob,DiscoveryPolicy,DiscoveryResult,DiscoveryStage
from app.services.discovery_intelligence_service import DEVICE_FAMILIES,PIPELINE,configuration_checksum,confidence,discovered_description,identify,interpret_hostname,merge_hostnames,review_status,services_from_ports

def test_pipeline_has_all_ordered_retryable_stages():
    assert len(PIPELINE)==20 and PIPELINE[0]=="icmp_reachability" and PIPELINE[-1]=="configuration_item_update"
    assert {"snmp_discovery","lldp_cdp_topology","active_directory_correlation","confidence_calculation"}<=set(PIPELINE)
def test_confidence_is_explainable_and_capped():
    result=confidence(["ping_response","mac_address","vendor_match","hostname_match","snmp","ad_match","cmdb_match","lldp","service_fingerprint","operating_system"]);assert result["score"]==100 and sum(x["weight"] for x in result["contributions"])==115;assert confidence(["ping_response","ping_response"])["score"]==15
def test_hostname_rules_are_suggestions_and_unknown_names_stay_unknown():
    assert interpret_hostname("heloshaposbqt01") == {"original_hostname":"heloshaposbqt01","device_type":"Point of Sale","department":"Banquet","device_number":"01","friendly_name":"POS Terminal 01"}
    assert interpret_hostname("ordinary-host") is None
def test_discovered_description_preserves_manual_or_inventory_text():
    assert discovered_description("Front desk terminal", "Manual", "DHCP text", "DHCP") == ("Front desk terminal", "Manual")
    assert discovered_description(None, None, "DHCP text", "DHCP") == ("DHCP text", "DHCP")
def test_hostname_merge_is_normalized_and_deterministic():assert merge_hostnames(["HOST01.","host01.example.com","bad host"])=={"primary":"host01.example.com","aliases":["host01"]}
def test_service_and_device_fingerprints_are_deterministic():
    assert services_from_ports([443,22,443])==[{"port":22,"service":"SSH/SFTP"},{"port":443,"service":"HTTPS"}];assert identify({"vendor":"Hikvision","open_ports":[80]})["classification"]=="CCTV Camera";assert "Unknown Device" in DEVICE_FAMILIES
def test_review_thresholds_and_checksum():assert [review_status(x) for x in (0,40,80)]==["needs_review","partially_identified","automatically_identified"] and configuration_checksum({"b":2,"a":1})==configuration_checksum({"a":1,"b":2})
def test_enterprise_discovery_schema_is_auditable_and_secret_safe():
    assert [x.__tablename__ for x in (DiscoveryPolicy,DiscoveryCredential,DiscoveryJob,DiscoveryStage,DiscoveryResult,DiscoveryEvidence,DiscoveryFingerprint)]==["enterprise_discovery_policies","enterprise_discovery_credentials","enterprise_discovery_jobs","enterprise_discovery_stages","enterprise_discovery_results","enterprise_discovery_evidence","enterprise_discovery_fingerprints"]
    columns=set(DiscoveryCredential.__table__.columns.keys());assert "secret_ciphertext" in columns and "secret" not in columns;assert {"confidence_score","confidence_explanation","configuration_checksum","ci_id"}<=set(DiscoveryResult.__table__.columns.keys())
