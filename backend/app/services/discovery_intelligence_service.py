import hashlib,json,re
from dataclasses import dataclass
from datetime import datetime, timezone
from ipaddress import ip_network

from app.discovery.network import ensure_authorized
from app.models.discovery_intelligence import DiscoveryChangeSuggestion,DiscoveryEvidence,DiscoveryFingerprint,DiscoveryJob,DiscoveryOUI,DiscoveryResult,DiscoveryStage

PIPELINE=("icmp_reachability","arp_resolution","reverse_dns","hostname_resolution","mac_collection","mac_vendor_identification","port_discovery","service_fingerprinting","snmp_discovery","netbios_discovery","windows_wmi_discovery","linux_ssh_fingerprinting","http_https_fingerprinting","tls_certificate_inspection","lldp_cdp_topology","dhcp_lease_correlation","active_directory_correlation","cmdb_correlation","confidence_calculation","configuration_item_update")
WEIGHTS={"ping_response":15,"mac_address":15,"vendor_match":10,"hostname_match":15,"dns_resolution":5,"description":10,"snmp":20,"ad_match":10,"ad_description_agreement":10,"ad_department_agreement":5,"ad_domain_match":5,"cmdb_match":10,"lldp":5,"service_fingerprint":5,"operating_system":10,"hostname_rule":5,"manual_confirmation":15}
# Compatibility symbol only. Hotel department conventions are configured as
# scoped IdentityRule records and are never global application defaults.
DEPARTMENT_RULES={}
SERVICE_PORTS={21:"FTP",22:"SSH/SFTP",53:"DNS",67:"DHCP",80:"HTTP",123:"NTP",135:"WMI",139:"NetBIOS",161:"SNMP",389:"LDAP",443:"HTTPS",445:"SMB",636:"LDAPS",1433:"SQL Server",1521:"Oracle",2375:"Docker",2376:"Docker TLS",3306:"MySQL",3389:"RDP",5432:"PostgreSQL",5985:"WinRM",5986:"WinRM TLS",6379:"Redis",6443:"Kubernetes API",9200:"Elasticsearch",27017:"MongoDB"}
DEVICE_FAMILIES=("Server","Windows","Linux","VMware ESXi","Hyper-V","Docker Host","Kubernetes Node","Switch","Router","Firewall","Wireless Controller","Access Point","Printer","Scanner","UPS","IP Phone","VoIP Gateway","POS Terminal","PMS Server","IPTV System","Door Lock Controller","CCTV Camera","Biometric Device","IoT Device","Storage Array","Virtual Machine","Unknown Device")

def normalize_hostname(value):
    if not value:return None
    text=str(value).strip().rstrip(".").lower();return text[:255] if re.fullmatch(r"[a-z0-9][a-z0-9._-]*",text) else None
def merge_hostnames(values):
    normalized=sorted({x for x in (normalize_hostname(v) for v in values) if x},key=lambda x:(x.count("."),len(x),x),reverse=True);return {"primary":normalized[0] if normalized else None,"aliases":normalized[1:]}
def confidence(evidence_types):
    seen=set(evidence_types);parts=[{"evidence":key,"weight":weight} for key,weight in WEIGHTS.items() if key in seen];return {"score":min(100,sum(x["weight"] for x in parts)),"contributions":parts,"maximum":100}
def interpret_hostname(hostname, type_rules=None, department_rules=None):
    original=normalize_hostname(hostname)
    if not original:return None
    compact=re.sub(r"[^a-z0-9]","",original.split(".")[0]).upper();types=type_rules or {};departments=department_rules or {}
    type_match=next(((code,label) for code,label in sorted(types.items(),key=lambda item:-len(item[0])) if code in compact),None)
    dept_match=next(((code,label) for code,label in sorted(departments.items(),key=lambda item:-len(item[0])) if code in compact),None)
    number=re.search(r"(\d+)$",compact)
    if not type_match and not dept_match:return None
    device_number=number.group(1) if number else None;friendly=None
    if type_match:friendly=f"{'POS Terminal' if type_match[0]=='POS' else type_match[1]}{f' {device_number}' if device_number else ''}"
    return {"original_hostname":original,"device_type":type_match[1] if type_match else None,"department":dept_match[1] if dept_match else None,"device_number":device_number,"friendly_name":friendly}
def discovered_description(current, current_source, discovered, discovered_source="Discovery"):
    if current_source in ("Manual","Inventory") or not discovered:return current,current_source
    return discovered,discovered_source
def services_from_ports(ports):return [{"port":int(port),"service":SERVICE_PORTS.get(int(port),"Unknown")} for port in sorted({int(x) for x in ports})]
def identify(observation):
    text=" ".join(str(observation.get(x,"")) for x in ("hostname","vendor","snmp_description","http_server","ssh_banner","operating_system")).lower();ports={int(x) for x in observation.get("open_ports",[])}
    rules=(("VMware ESXi",("esxi","vmware")),("Hyper-V",("hyper-v","hyperv")),("Kubernetes Node",("kubernetes","kubelet")),("Docker Host",("docker",)),("Domain Controller",("domain controller","active directory")),("Firewall",("fortigate","firewall","palo alto")),("Wireless AP",("access point","unifi","aruba ap")),("Core Switch",("core-sw","core switch")),("Distribution Switch",("distribution switch","dist-sw")),("Access Switch",("catalyst","access switch","switch")),("CCTV Camera",("hikvision","axis","camera")),("Door Controller",("door lock","door controller")),("POS Terminal",("pos terminal","pos-")),("Restaurant Printer",("epson","brother","printer")),("PMS Server",("property management system","pms server")),("Database Server",("postgres","mysql","sql server","oracle")),("Application Server",("application server","server","srv-")))
    classification=next((label for label,markers in rules if any(marker in text for marker in markers)),"Unknown Device")
    if classification=="Unknown Device" and 3389 in ports:classification="Windows Server"
    if classification=="Unknown Device" and 22 in ports:classification="Linux Server"
    family="Unknown Device"
    for name in DEVICE_FAMILIES:
        if name.lower() in classification.lower() or name.lower() in text:family=name;break
    if family=="Unknown Device" and "server" in classification.lower():family="Server"
    return {"device_family":family,"classification":classification,"services":services_from_ports(ports)}
def configuration_checksum(snapshot):return hashlib.sha256(json.dumps(snapshot,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
def review_status(score,manual=False):return "manually_verified" if manual else "automatically_identified" if score>=80 else "partially_identified" if score>=40 else "needs_review"

def parse_json(value, fallback):
    try:return json.loads(value) if isinstance(value,str) else value
    except (TypeError,ValueError):return fallback

class DiscoveryIntelligenceService:
    """Deterministic orchestration. Network activity is limited by an explicit policy."""
    def __init__(self,db):self.db=db
    def create_job(self,policy,network_range,job_type,trigger_type,user_id=None):
        authorized=parse_json(policy.authorized_ranges,[]);excluded=parse_json(policy.excluded_ranges,[])
        network,_ignored=ensure_authorized(network_range,authorized,excluded,max_hosts=policy.max_hosts)
        job=DiscoveryJob(policy_id=policy.id,property_id=policy.property_id,job_type=job_type,trigger_type=trigger_type,network_range=str(network),hosts_total=network.num_addresses,requested_by=user_id)
        self.db.add(job);self.db.flush()
        enabled=set(parse_json(policy.enabled_stages,[]))
        for sequence,key in enumerate(PIPELINE,1):self.db.add(DiscoveryStage(job_id=job.id,stage_key=key,sequence=sequence,status="pending" if not enabled or key in enabled else "skipped"))
        self.db.flush();return job
    def ingest(self,job,observation):
        ip=str(observation["ip_address"]);item=self.db.query(DiscoveryResult).filter_by(job_id=job.id,ip_address=ip).first()
        if not item:item=DiscoveryResult(job_id=job.id,property_id=job.property_id,ip_address=ip);self.db.add(item);self.db.flush()
        names=merge_hostnames(observation.get("hostnames",[])+[observation.get("hostname")]);identified=identify(observation)
        item.primary_hostname=names["primary"] or item.primary_hostname;item.fqdn=observation.get("fqdn") or item.fqdn;item.dns_status=observation.get("dns_status") or item.dns_status;item.mac_address=observation.get("mac_address") or item.mac_address;item.vendor=observation.get("vendor") or item.vendor;item.device_type=identified["device_family"] if identified["device_family"]!="Unknown Device" else item.device_type;item.classification=identified["classification"] if identified["classification"]!="Unknown Device" else item.classification;item.operating_system=observation.get("operating_system") or item.operating_system
        # Hotel naming conventions are tenant configuration, never global code.
        # Scoped rules are evaluated after evidence is persisted below.
        item.description,item.description_source=discovered_description(item.description,item.description_source,observation.get("description"),observation.get("description_source") or "Discovery")
        snapshot={key:observation.get(key) for key in ("operating_system","version","kernel","firmware","bios","cpu","memory","disk","nics","installed_services","installed_roles","virtualization","certificates","dns_servers","gateway","open_ports","running_processes","uptime","boot_time","last_user","manufacturer","model","serial_number","asset_tag") if observation.get(key) is not None}
        checksum=configuration_checksum(snapshot);previous_checksum=item.configuration_checksum;previous_snapshot=item.configuration_snapshot
        if previous_checksum and previous_checksum!=checksum:
            item.last_changed_at=datetime.now(timezone.utc)
            if item.ci_id and not self.db.query(DiscoveryChangeSuggestion).filter_by(result_id=item.id,ci_id=item.ci_id,change_type="configuration",current_value=checksum).first():self.db.add(DiscoveryChangeSuggestion(result_id=item.id,ci_id=item.ci_id,change_type="configuration",previous_value=previous_snapshot,current_value=checksum))
        item.configuration_snapshot=json.dumps(snapshot,sort_keys=True,default=str);item.configuration_checksum=checksum;item.last_seen_at=datetime.now(timezone.utc)
        evidence=[]
        for raw in observation.get("evidence",[]):
            key=raw.get("evidence_type");norm=str(raw.get("normalized_value") or raw.get("value") or "")[:500]
            existing=self.db.query(DiscoveryEvidence).filter_by(result_id=item.id,evidence_type=key,source=raw.get("source","manual"),normalized_value=norm).first()
            if not existing:
                existing=DiscoveryEvidence(result_id=item.id,evidence_type=key,source=raw.get("source","manual"),value=json.dumps(raw.get("value"),default=str),normalized_value=norm,weight=WEIGHTS.get(key,0),verified=bool(raw.get("verified")));self.db.add(existing)
            evidence.append(key)
        self.db.flush();all_evidence=[x[0] for x in self.db.query(DiscoveryEvidence.evidence_type).filter_by(result_id=item.id).distinct().all()];score=confidence(all_evidence);item.confidence_score=score["score"];item.confidence_explanation=json.dumps(score["contributions"]);item.review_status=review_status(item.confidence_score)
        fingerprint=self.db.query(DiscoveryFingerprint).filter_by(result_id=item.id).first() or DiscoveryFingerprint(result_id=item.id)
        self.db.add(fingerprint);fingerprint.device_family=item.device_type;fingerprint.classification=item.classification;fingerprint.operating_system=item.operating_system;fingerprint.service_fingerprints=json.dumps(identified["services"]);fingerprint.hostname_candidates=json.dumps([names["primary"]]+names["aliases"] if names["primary"] else names["aliases"]);fingerprint.hardware=json.dumps({k:snapshot[k] for k in ("cpu","memory","disk","manufacturer","model","serial_number","asset_tag") if k in snapshot});fingerprint.software=json.dumps({k:snapshot[k] for k in ("operating_system","version","kernel","installed_services","installed_roles","running_processes") if k in snapshot});fingerprint.network=json.dumps({k:snapshot[k] for k in ("nics","dns_servers","gateway","open_ports") if k in snapshot});fingerprint.certificate_summary=json.dumps(snapshot.get("certificates",[]));fingerprint.confidence_score=item.confidence_score;fingerprint.rules_matched=json.dumps([item.classification] if item.classification!="Unknown Device" else [])
        self.db.flush()
        from app.models.hierarchy import Property
        from app.services.device_correlation_service import DeviceCorrelationService
        from app.services.device_identity_service import DeviceIdentityService
        root=DeviceCorrelationService(self.db).correlate(item,"discovery_ingest")
        prop=self.db.get(Property,root.property_id) if root.property_id else None
        if prop:
            DeviceIdentityService(self.db).apply(root,prop.organization_id)
        return root
    def oui_lookup(self,mac):
        prefix=re.sub(r"[^0-9A-F]","",(mac or "").upper())[:6]
        row=self.db.query(DiscoveryOUI).filter_by(prefix=prefix).first();return row.vendor if row else "Unknown"
