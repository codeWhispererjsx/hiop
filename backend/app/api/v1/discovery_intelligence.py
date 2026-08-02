import ipaddress,json,re
from datetime import datetime,timezone
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from sqlalchemy import func,or_
from sqlalchemy.orm import Session
from app.core.security import get_db,require_roles
from app.models.cmdb import CIClass,CIIdentifier,CIType,ConfigurationItem
from app.models.discovery_intelligence import DiscoveryChangeSuggestion,DiscoveryCredential,DiscoveryDHCPLease,DiscoveryEvidence,DiscoveryFingerprint,DiscoveryJob,DiscoveryOUI,DiscoveryPolicy,DiscoveryResult,DiscoveryStage,DiscoveryTask
from app.models.topology import Topology,TopologyLink,TopologyNode
from app.models.snmp import SNMPTarget
from app.models.discovered_device import DiscoveredDevice,DiscoveryStatus
from app.models.device import Device
from app.services.audit_service import create_audit_log
from app.services.discovery_intelligence_service import DEVICE_FAMILIES,PIPELINE,DiscoveryIntelligenceService,confidence,parse_json,review_status
from app.services.discovery_collectors import ActiveDirectoryCorrelationCollector,CollectedObservation,CredentialedHostCollector,DHCPLeaseCorrelationCollector,DNSCorrelationCollector,NetBIOSNameCollector,SNMPDiscoveryCollector,ServiceFingerprintCollector,evidence
from app.services.discovery_service import DiscoveryService
from app.services.secret_encryption_service import SecretEncryptionService
from app.services.topology_neighbor_collection_service import TopologyNeighborCollectionService

router=APIRouter(prefix="/discovery-intelligence",tags=["Enterprise Discovery & Configuration Intelligence"])
reader=require_roles(["admin","superadmin","technician","viewer"]);operator=require_roles(["admin","superadmin","technician"]);admin=require_roles(["admin","superadmin"])
REVIEW=("needs_review","automatically_identified","partially_identified","manually_verified","ignored","false_positive","duplicate","retired")
class PolicyWrite(BaseModel):
    name:str=Field(min_length=2,max_length=180);property_id:UUID|None=None;authorized_ranges:list[str];excluded_ranges:list[str]=[];enabled_stages:list[str]=[];allowed_ports:list[int]=[];max_hosts:int=Field(1024,ge=1,le=65536);concurrency:int=Field(20,ge=1,le=128);timeout_seconds:int=Field(2,ge=1,le=30);rate_limit_per_second:int=Field(20,ge=1,le=500);allow_credentialed:bool=False;enabled:bool=True
class CredentialWrite(BaseModel):
    policy_id:UUID;name:str;credential_type:str=Field(pattern=r"^(snmp|wmi|winrm|ssh|http|https)$");username:str|None=None;secret:str=Field(min_length=1,max_length=4096);scope_cidr:str|None=None;least_privilege_notes:str=Field(min_length=3,max_length=2000);enabled:bool=False
class JobWrite(BaseModel): policy_id:UUID;network_range:str;job_type:str=Field("incremental",pattern=r"^(incremental|full)$")
class QuickScanWrite(BaseModel): network_range:str=Field(min_length=3,max_length=64)
class Observation(BaseModel): ip_address:str;hostname:str|None=None;hostnames:list[str]=[];mac_address:str|None=None;vendor:str|None=None;operating_system:str|None=None;open_ports:list[int]=[];evidence:list[dict]=[];configuration:dict={}
class ReviewWrite(BaseModel): status:str=Field(pattern="^("+"|".join(REVIEW)+")$");classification:str|None=None
class ApproveWrite(BaseModel):
    friendly_name:str|None=Field(default=None,max_length=253)
    category:str|None=Field(default=None,max_length=80)
    department:str=Field(default="Unassigned",max_length=120)
    location:str=Field(default="Unassigned",max_length=160)
class OUIWrite(BaseModel): prefix:str=Field(pattern=r"^[0-9A-Fa-f:-]{6,8}$");vendor:str=Field(min_length=2,max_length=180);version:str="manual"
class DHCPLeaseWrite(BaseModel): ip_address:str;mac_address:str=Field(min_length=12,max_length=17);hostname:str|None=None;source:str=Field(min_length=2,max_length=120);lease_server:str|None=None;starts_at:datetime|None=None;expires_at:datetime|None=None
def page(q,p,s):return {"items":q.offset((p-1)*s).limit(s).all(),"total":q.count(),"page":p,"page_size":s}
def get(db,model,id,label):
    row=db.get(model,id)
    if not row:raise HTTPException(404,f"{label} not found")
    return row
def audit(db,user,action,entity,id,message):create_audit_log(db,user.username,action,entity,str(id),message)
def credential_view(row):return {"id":row.id,"policy_id":row.policy_id,"name":row.name,"credential_type":row.credential_type,"username":row.username,"scope_cidr":row.scope_cidr,"least_privilege_notes":row.least_privilege_notes,"enabled":row.enabled,"last_used_at":row.last_used_at,"created_at":row.created_at,"secret_configured":True}
def consolidated_device_rows(db,limit=1000):
    rows=db.query(DiscoveryResult).order_by(DiscoveryResult.confidence_score.desc(),DiscoveryResult.last_seen_at.desc()).limit(10000).all();devices={};mac_index={};name_index={};ip_index={}
    for row in rows:
        mac=re.sub(r"[^0-9a-f]","",(row.mac_address or "").lower());name=(row.primary_hostname or "").strip().rstrip(".").lower()
        key=mac_index.get(mac) if len(mac)==12 else None
        if not key and name:key=name_index.get(name)
        if not key:key=ip_index.get(row.ip_address)
        if not key:key=f"mac:{mac}" if len(mac)==12 else f"name:{name}" if name else f"ip:{row.ip_address}"
        current=devices.get(key)
        if not current:
            devices[key]={"id":row.id,"result_id":row.id,"job_id":row.job_id,"ip_address":row.ip_address,"primary_hostname":row.primary_hostname,"mac_address":row.mac_address,"vendor":row.vendor,"device_type":row.device_type,"classification":row.classification,"operating_system":row.operating_system,"review_status":row.review_status,"confidence_score":row.confidence_score,"confidence_explanation":row.confidence_explanation,"ci_id":row.ci_id,"first_seen_at":row.first_seen_at,"last_seen_at":row.last_seen_at,"observations":1}
        else:
            current["observations"]+=1;current["first_seen_at"]=min(current["first_seen_at"],row.first_seen_at);current["last_seen_at"]=max(current["last_seen_at"],row.last_seen_at)
            for field in ("primary_hostname","mac_address","vendor","operating_system","ci_id"):
                if not current[field] and getattr(row,field):current[field]=getattr(row,field)
        if len(mac)==12:mac_index[mac]=key
        if name:name_index[name]=key
        ip_index[row.ip_address]=key
    return sorted(devices.values(),key=lambda x:x["last_seen_at"],reverse=True)[:limit]
def execute_safe_job(db,job,user):
    policy=get(db,DiscoveryPolicy,job.policy_id,"Policy");job.status="running";job.started_at=datetime.now(timezone.utc);db.commit()
    config={"enabled":True,"authorized_cidr_ranges":",".join(parse_json(policy.authorized_ranges,[])),"ignore_ranges":",".join(parse_json(policy.excluded_ranges,[])),"max_hosts_per_run":policy.max_hosts,"concurrency_limit":policy.concurrency,"ping_timeout_seconds":policy.timeout_seconds,"automatic_hostname_lookup":True,"automatic_vendor_lookup":True,"admin_notification_threshold":policy.max_hosts+1}
    try:run=DiscoveryService(db,config=config).discover_range(job.network_range,trigger_type=job.trigger_type,triggered_by=user.id,audit_actor=user.username)
    except Exception as exc:
        job=db.get(DiscoveryJob,job.id);job.status="failed";job.tasks_failed+=1;job.completed_at=datetime.now(timezone.utc);db.commit();raise HTTPException(502,f"Safe discovery failed: {exc}") from exc
    network=ipaddress.ip_network(job.network_range,strict=False);legacy=[x for x in db.query(DiscoveredDevice).all() if ipaddress.ip_address(x.ip_address) in network and x.last_seen_at>=run.started_at]
    service=DiscoveryIntelligenceService(db);results=[];stage_errors=[]
    enabled=set(parse_json(policy.enabled_stages,[]));stage_enabled=lambda key:not enabled or key in enabled
    dns_collector=DNSCorrelationCollector();netbios_collector=NetBIOSNameCollector(timeout=min(float(policy.timeout_seconds),1.0));ad_collector=ActiveDirectoryCorrelationCollector(db);dhcp_collector=DHCPLeaseCorrelationCollector(db)
    service_collector=ServiceFingerprintCollector(timeout=min(float(policy.timeout_seconds),3.0))
    snmp_collector=SNMPDiscoveryCollector(db);host_collector=CredentialedHostCollector(db)
    for device in legacy:
        observed=CollectedObservation(device.ip_address,hostnames=[device.hostname] if device.hostname else [],mac_address=device.mac_address,vendor=device.vendor,operating_system=device.operating_system_guess)
        if device.status==DiscoveryStatus.ONLINE:observed.evidence.append(evidence("ping_response","icmp","reachable",verified=True))
        for key,value,source in (("mac_address",device.mac_address,"arp"),("vendor_match",device.vendor,"oui"),("hostname_match",device.hostname,"reverse_dns"),("operating_system",device.operating_system_guess,"fingerprint")):
            if value:observed.evidence.append(evidence(key,source,value,verified=source in ("arp","reverse_dns")))
        if stage_enabled("hostname_resolution"):observed.merge(dns_collector.collect(device.ip_address))
        if stage_enabled("netbios_discovery"):observed.merge(netbios_collector.collect(device.ip_address))
        if stage_enabled("dhcp_lease_correlation"):observed.merge(dhcp_collector.collect(device.ip_address))
        if stage_enabled("service_fingerprinting") and parse_json(policy.allowed_ports,[]):
            observed.merge(service_collector.collect(device.ip_address,parse_json(policy.allowed_ports,[])))
        if stage_enabled("snmp_discovery") and policy.allow_credentialed:
            snmp_observation=snmp_collector.collect(device.ip_address,parse_json(policy.authorized_ranges,[]));observed.merge(snmp_observation);stage_errors.extend(snmp_observation.warnings)
        if policy.allow_credentialed and (stage_enabled("windows_wmi_discovery") or stage_enabled("linux_ssh_fingerprinting")):
            host_observation=host_collector.collect(policy.id,device.ip_address,observed.open_ports,float(policy.timeout_seconds));observed.merge(host_observation);stage_errors.extend(host_observation.warnings)
        if stage_enabled("active_directory_correlation"):
            observed.merge(ad_collector.collect(device.ip_address,observed.hostnames))
        result=service.ingest(job,observed.as_dict());result.discovered_device_id=device.id;results.append(result)
    if policy.allow_credentialed and stage_enabled("lldp_cdp_topology"):
        active_topology=db.query(Topology).filter_by(enabled=True).order_by(Topology.is_default.desc()).first()
        if active_topology:
            topology_collector=TopologyNeighborCollectionService(db,authorized_networks=parse_json(policy.authorized_ranges,[]),ignored_networks=parse_json(policy.excluded_ranges,[]))
            for device in legacy:
                target=db.query(SNMPTarget).filter_by(ip_address=device.ip_address,enabled=True).first()
                if not target:continue
                try:
                    topology_run=topology_collector.collect(active_topology,target,"auto",False,user)
                    if topology_run.status not in ("completed","partial"):stage_errors.append(f"Topology collection for {device.ip_address}: {topology_run.error_summary or topology_run.status}")
                except HTTPException as exc:stage_errors.append(f"Topology collection for {device.ip_address}: {exc.detail}")
    stages=db.query(DiscoveryStage).filter_by(job_id=job.id).order_by(DiscoveryStage.sequence).all();executed={"icmp_reachability","arp_resolution","reverse_dns","hostname_resolution","mac_collection","mac_vendor_identification","netbios_discovery","dhcp_lease_correlation","cmdb_correlation","confidence_calculation","configuration_item_update"}
    if parse_json(policy.allowed_ports,[]):executed.update({"port_discovery","service_fingerprinting","http_https_fingerprinting","tls_certificate_inspection"})
    if policy.allow_credentialed:executed.update({"snmp_discovery","windows_wmi_discovery","linux_ssh_fingerprinting","lldp_cdp_topology","active_directory_correlation"})
    now_at=datetime.now(timezone.utc)
    for stage in stages:
        stage.status="completed" if stage.stage_key in executed else "skipped";stage.attempts+=int(stage.stage_key in executed);stage.started_at=stage.started_at or job.started_at;stage.completed_at=now_at
        for device in legacy:db.add(DiscoveryTask(job_id=job.id,stage_id=stage.id,target=device.ip_address,status=stage.status,attempts=int(stage.stage_key in executed),started_at=job.started_at,completed_at=now_at))
    job.status="completed" if run.status.value in ("completed","partial") else "failed";job.current_stage="configuration_item_update";job.hosts_completed=run.hosts_attempted;job.tasks_failed=run.error_count;job.completed_at=now_at;audit(db,user,"EXECUTE","discovery_job",job.id,"Executed bounded ICMP, ARP, DNS, service, SNMP, AD, confidence, and correlation stages");db.commit();db.refresh(job);return {"job":job,"legacy_run_id":run.id,"results":len(results),"hosts_responded":run.hosts_responded,"errors":run.error_count,"warnings":stage_errors[:100]}

@router.get("/capabilities")
def capabilities(_=Depends(reader)):return {"pipeline":PIPELINE,"device_families":DEVICE_FAMILIES,"review_statuses":REVIEW,"credentialed_stages_are_opt_in":True,"intrusive_scanning":False}
@router.post("/quick-scan")
def quick_scan(body:QuickScanWrite,db:Session=Depends(get_db),user=Depends(operator)):
    try:network=ipaddress.ip_network(body.network_range,strict=False)
    except ValueError as exc:raise HTTPException(422,"Enter a valid private IP address or CIDR range") from exc
    if not network.is_private:raise HTTPException(422,"Quick Scan is limited to private networks")
    if network.num_addresses>1024:raise HTTPException(422,"Quick Scan is limited to 1,024 addresses; scan a smaller subnet")
    scope=str(network);policy=db.query(DiscoveryPolicy).filter_by(name=f"Quick Scan · {scope}",created_by=user.id).first()
    safe_stages=["icmp_reachability","arp_resolution","reverse_dns","hostname_resolution","mac_collection","mac_vendor_identification","port_discovery","service_fingerprinting","netbios_discovery","http_https_fingerprinting","tls_certificate_inspection","dhcp_lease_correlation","active_directory_correlation","cmdb_correlation","confidence_calculation","configuration_item_update"]
    if not policy:
        policy=DiscoveryPolicy(name=f"Quick Scan · {scope}",authorized_ranges=json.dumps([scope]),excluded_ranges="[]",enabled_stages=json.dumps(safe_stages),allowed_ports=json.dumps([22,53,80,135,139,161,443,445,3389,5985,5986]),max_hosts=1024,concurrency=32,timeout_seconds=1,rate_limit_per_second=50,allow_credentialed=False,enabled=True,created_by=user.id);db.add(policy);db.flush()
    job=DiscoveryIntelligenceService(db).create_job(policy,scope,"full","quick_scan",user.id);audit(db,user,"CREATE","discovery_job",job.id,"Started credential-free Quick Network Scan");db.commit();db.refresh(job)
    execution=execute_safe_job(db,job,user);devices=[item for item in consolidated_device_rows(db) if ipaddress.ip_address(item["ip_address"]) in network]
    return {"job":execution["job"],"summary":{"found":len(devices),"identified":sum(x["confidence_score"]>=80 for x in devices),"partial":sum(40<=x["confidence_score"]<80 for x in devices),"needs_review":sum(x["confidence_score"]<40 for x in devices)},"devices":devices,"warnings":execution.get("warnings",[])}
@router.get("/devices")
def consolidated_devices(search:str|None=None,db:Session=Depends(get_db),_=Depends(reader)):
    rows=consolidated_device_rows(db)
    if search:
        term=search.lower();rows=[x for x in rows if term in " ".join(str(x.get(k) or "") for k in ("primary_hostname","ip_address","mac_address","vendor","classification","operating_system")).lower()]
    return {"items":rows,"total":len(rows)}
@router.get("/dashboard")
def dashboard(db:Session=Depends(get_db),_=Depends(reader)):
    total=db.query(DiscoveryResult).count();identified=db.query(DiscoveryResult).filter(DiscoveryResult.review_status.in_(("automatically_identified","manually_verified"))).count();unknown=db.query(DiscoveryResult).filter(DiscoveryResult.review_status=="needs_review").count();jobs=db.query(DiscoveryJob).count();failed=db.query(DiscoveryTask).filter_by(status="failed").count()
    bands={label:db.query(DiscoveryResult).filter(DiscoveryResult.confidence_score.between(lo,hi)).count() for label,lo,hi in (("low",0,39),("partial",40,79),("high",80,100))}
    vendors=[{"label":v or "Unknown","value":c} for v,c in db.query(DiscoveryResult.vendor,func.count()).group_by(DiscoveryResult.vendor).order_by(func.count().desc()).limit(8)]
    types=[{"label":v,"value":c} for v,c in db.query(DiscoveryResult.classification,func.count()).group_by(DiscoveryResult.classification).order_by(func.count().desc()).limit(8)]
    return {"results":total,"success_rate":round(identified*100/total,1) if total else 0,"unknown_devices":unknown,"jobs":jobs,"errors":failed,"confidence":bands,"vendors":vendors,"device_types":types,"recent":db.query(DiscoveryResult).order_by(DiscoveryResult.last_seen_at.desc()).limit(8).all()}
@router.get("/policies")
def policies(db:Session=Depends(get_db),_=Depends(reader)):return {"items":db.query(DiscoveryPolicy).order_by(DiscoveryPolicy.name).all()}
@router.post("/policies",status_code=201)
def create_policy(body:PolicyWrite,db:Session=Depends(get_db),user=Depends(admin)):
    invalid=set(body.enabled_stages)-set(PIPELINE)
    if invalid:raise HTTPException(422,f"Unknown stages: {', '.join(sorted(invalid))}")
    row=DiscoveryPolicy(**body.model_dump(exclude={"authorized_ranges","excluded_ranges","enabled_stages","allowed_ports"}),authorized_ranges=json.dumps(body.authorized_ranges),excluded_ranges=json.dumps(body.excluded_ranges),enabled_stages=json.dumps(body.enabled_stages),allowed_ports=json.dumps(body.allowed_ports),created_by=user.id);db.add(row);db.flush();audit(db,user,"CREATE","discovery_policy",row.id,"Created bounded enterprise discovery policy");db.commit();db.refresh(row);return row
@router.put("/policies/{id}")
def update_policy(id:UUID,body:PolicyWrite,db:Session=Depends(get_db),user=Depends(admin)):
    row=get(db,DiscoveryPolicy,id,"Policy");data=body.model_dump()
    for key in ("authorized_ranges","excluded_ranges","enabled_stages","allowed_ports"):data[key]=json.dumps(data[key])
    for key,value in data.items():setattr(row,key,value)
    audit(db,user,"UPDATE","discovery_policy",id,"Updated enterprise discovery policy");db.commit();db.refresh(row);return row
@router.get("/credentials")
def credentials(db:Session=Depends(get_db),_=Depends(admin)):return {"items":[credential_view(x) for x in db.query(DiscoveryCredential).order_by(DiscoveryCredential.created_at.desc()).all()]}
@router.post("/credentials",status_code=201)
def create_credential(body:CredentialWrite,db:Session=Depends(get_db),user=Depends(admin)):
    policy=get(db,DiscoveryPolicy,body.policy_id,"Policy")
    if not policy.allow_credentialed:raise HTTPException(409,"Credentialed discovery is disabled by this policy")
    data=body.model_dump(exclude={"secret"});row=DiscoveryCredential(**data,secret_ciphertext=SecretEncryptionService.encrypt(body.secret,environment_key="HIOP_DISCOVERY_CREDENTIAL_KEY"),created_by=user.id);db.add(row);db.flush();audit(db,user,"CREATE","discovery_credential",row.id,"Stored encrypted least-privilege discovery credential");db.commit();db.refresh(row);return credential_view(row)
@router.post("/credentials/{id}/disable")
def disable_credential(id:UUID,db:Session=Depends(get_db),user=Depends(admin)):
    row=get(db,DiscoveryCredential,id,"Credential");row.enabled=False;audit(db,user,"DISABLE","discovery_credential",id,"Disabled discovery credential");db.commit();return credential_view(row)
@router.post("/credentials/{id}/enable")
def enable_credential(id:UUID,db:Session=Depends(get_db),user=Depends(admin)):
    row=get(db,DiscoveryCredential,id,"Credential");policy=get(db,DiscoveryPolicy,row.policy_id,"Policy")
    if not policy.enabled or not policy.allow_credentialed:raise HTTPException(409,"Credentialed discovery must be enabled by the policy first")
    row.enabled=True;audit(db,user,"ENABLE","discovery_credential",id,"Enabled scoped least-privilege discovery credential");db.commit();return credential_view(row)
@router.get("/jobs")
def jobs(status:str|None=None,page_number:int=Query(1,alias="page",ge=1),page_size:int=Query(25,ge=1,le=100),db:Session=Depends(get_db),_=Depends(reader)):
    q=db.query(DiscoveryJob).order_by(DiscoveryJob.created_at.desc());q=q.filter_by(status=status) if status else q;return page(q,page_number,page_size)
@router.post("/jobs",status_code=201)
def create_job(body:JobWrite,db:Session=Depends(get_db),user=Depends(admin)):
    policy=get(db,DiscoveryPolicy,body.policy_id,"Policy")
    if not policy.enabled:raise HTTPException(409,"Discovery policy is disabled")
    try:row=DiscoveryIntelligenceService(db).create_job(policy,body.network_range,body.job_type,"manual",user.id)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    audit(db,user,"CREATE","discovery_job",row.id,"Created auditable multi-stage discovery job");db.commit();db.refresh(row);return row
@router.get("/jobs/{id}")
def job(id:UUID,db:Session=Depends(get_db),_=Depends(reader)):
    row=get(db,DiscoveryJob,id,"Job");return {"job":row,"stages":db.query(DiscoveryStage).filter_by(job_id=id).order_by(DiscoveryStage.sequence).all(),"tasks":db.query(DiscoveryTask).filter_by(job_id=id).all()}
@router.post("/jobs/{id}/execute")
def execute_job(id:UUID,db:Session=Depends(get_db),user=Depends(admin)):
    job=get(db,DiscoveryJob,id,"Job")
    if job.status=="running":raise HTTPException(409,"Discovery job is already running")
    if job.status=="completed":raise HTTPException(409,"Discovery job is already complete")
    return execute_safe_job(db,job,user)
@router.post("/jobs/{id}/stages/{stage_key}/run")
def run_stage(id:UUID,stage_key:str,observations:list[Observation]=[],db:Session=Depends(get_db),user=Depends(admin)):
    job=get(db,DiscoveryJob,id,"Job");stage=db.query(DiscoveryStage).filter_by(job_id=id,stage_key=stage_key).first()
    if not stage:raise HTTPException(404,"Stage not found")
    if stage.status=="skipped":raise HTTPException(409,"Stage is disabled by policy")
    stage.status="running";stage.attempts+=1;stage.started_at=datetime.now(timezone.utc);job.status="running";job.current_stage=stage_key
    try:
        results=[]
        for observation in observations:
            task=db.query(DiscoveryTask).filter_by(stage_id=stage.id,target=observation.ip_address).first() or DiscoveryTask(job_id=job.id,stage_id=stage.id,target=observation.ip_address);db.add(task);task.status="running";task.attempts+=1;task.started_at=datetime.now(timezone.utc);db.flush();results.append(DiscoveryIntelligenceService(db).ingest(job,{**observation.model_dump(exclude={"configuration"}),**observation.configuration}));task.status="completed";task.completed_at=datetime.now(timezone.utc)
        stage.status="completed";stage.completed_at=datetime.now(timezone.utc);job.hosts_completed=max(job.hosts_completed,len(results))
    except Exception as exc:stage.status="failed";stage.error=str(exc)[:2000];db.commit();raise
    audit(db,user,"EXECUTE","discovery_stage",stage.id,f"Executed deterministic stage {stage_key}");db.commit();return {"stage":stage,"processed":len(results)}
@router.post("/tasks/{id}/retry")
def retry_task(id:UUID,db:Session=Depends(get_db),user=Depends(admin)):
    row=get(db,DiscoveryTask,id,"Task")
    if row.attempts>=row.max_attempts:raise HTTPException(409,"Retry limit reached")
    row.status="pending";row.next_retry_at=None;row.error=None;row.error_code=None;audit(db,user,"RETRY","discovery_task",id,"Queued discovery task retry");db.commit();return row
@router.get("/results")
def results(search:str|None=None,status:str|None=None,page_number:int=Query(1,alias="page",ge=1),page_size:int=Query(25,ge=1,le=100),db:Session=Depends(get_db),_=Depends(reader)):
    q=db.query(DiscoveryResult).order_by(DiscoveryResult.last_seen_at.desc());q=q.filter_by(review_status=status) if status else q
    if search:q=q.filter(or_(DiscoveryResult.ip_address.ilike(f"%{search}%"),DiscoveryResult.primary_hostname.ilike(f"%{search}%"),DiscoveryResult.vendor.ilike(f"%{search}%"),DiscoveryResult.classification.ilike(f"%{search}%")))
    return page(q,page_number,page_size)
@router.get("/results/{id}")
def result(id:UUID,db:Session=Depends(get_db),_=Depends(reader)):
    row=get(db,DiscoveryResult,id,"Result");return {"result":row,"evidence":db.query(DiscoveryEvidence).filter_by(result_id=id).order_by(DiscoveryEvidence.observed_at.desc()).all(),"fingerprint":db.query(DiscoveryFingerprint).filter_by(result_id=id).first(),"change_suggestions":db.query(DiscoveryChangeSuggestion).filter_by(result_id=id).all()}
@router.post("/results/{id}/review")
def review(id:UUID,body:ReviewWrite,db:Session=Depends(get_db),user=Depends(admin)):
    row=get(db,DiscoveryResult,id,"Result");row.review_status=body.status
    if body.classification:
        row.classification=body.classification;fp=db.query(DiscoveryFingerprint).filter_by(result_id=id).first()
        if fp:fp.editable_override=body.classification
    audit(db,user,"REVIEW","discovery_result",id,"Reviewed discovery identification");db.commit();return row
@router.post("/results/{id}/approve",status_code=201)
def approve_result(id:UUID,body:ApproveWrite,db:Session=Depends(get_db),user=Depends(admin)):
    row=get(db,DiscoveryResult,id,"Result")
    discovered=db.get(DiscoveredDevice,row.discovered_device_id) if row.discovered_device_id else None
    if discovered and discovered.approved_device_id:
        return db.get(Device,discovered.approved_device_id)
    normalized_mac=(row.mac_address or "").strip().upper().replace("-",":")
    duplicate=None
    if normalized_mac: duplicate=db.query(Device).filter(func.lower(Device.mac_address)==normalized_mac.lower()).first()
    if not duplicate: duplicate=db.query(Device).filter(Device.ip_address==row.ip_address).first()
    if duplicate:raise HTTPException(409,"This device is already present in managed inventory")
    suffix=str(row.id).replace("-","")[:12].upper()
    device=Device(
        asset_tag=f"HIOP-{suffix[:8]}",hostname=(body.friendly_name or row.primary_hostname or f"Unknown-{row.ip_address}").strip(),
        device_type=(body.category or row.classification or row.device_type or "Unknown").strip(),brand=(row.vendor or "Unknown").strip(),
        model="Unknown",serial_number=f"UNKNOWN-{suffix}",department=body.department.strip() or "Unassigned",
        location=body.location.strip() or "Unassigned",ip_address=row.ip_address,
        mac_address=normalized_mac or None,
        inventory_status="Active",network_status="Online",status="Active",
    )
    db.add(device);db.flush();row.review_status="manually_verified"
    if discovered:
        discovered.review_status="approved";discovered.approved_device_id=device.id;discovered.reviewed_by=user.id;discovered.reviewed_at=datetime.now(timezone.utc)
    audit(db,user,"APPROVE","discovery_result",id,f"Approved {row.ip_address} into managed inventory");db.commit();db.refresh(device);return device
@router.post("/confidence/recalculate")
def recalculate(db:Session=Depends(get_db),user=Depends(admin)):
    changed=0
    for row in db.query(DiscoveryResult).all():
        score=confidence(x[0] for x in db.query(DiscoveryEvidence.evidence_type).filter_by(result_id=row.id).distinct());row.confidence_score=score["score"];row.confidence_explanation=json.dumps(score["contributions"]);row.review_status=review_status(row.confidence_score) if row.review_status!="manually_verified" else row.review_status;changed+=1
    audit(db,user,"RECALCULATE","discovery_confidence","all","Recalculated explainable discovery confidence");db.commit();return {"updated":changed}
@router.get("/oui")
def oui(q:str|None=None,db:Session=Depends(get_db),_=Depends(reader)):
    query=db.query(DiscoveryOUI);query=query.filter(or_(DiscoveryOUI.prefix.ilike(f"%{q}%"),DiscoveryOUI.vendor.ilike(f"%{q}%"))) if q else query;return {"items":query.order_by(DiscoveryOUI.vendor).limit(200).all()}
@router.post("/oui",status_code=201)
def upsert_oui(body:OUIWrite,db:Session=Depends(get_db),user=Depends(admin)):
    prefix=re.sub(r"[^0-9A-F]","",body.prefix.upper());row=db.query(DiscoveryOUI).filter_by(prefix=prefix).first() or DiscoveryOUI(prefix=prefix);db.add(row);row.vendor=body.vendor;row.source="administrator";row.version=body.version;audit(db,user,"UPDATE","discovery_oui",prefix,"Updated local OUI database entry");db.commit();db.refresh(row);return row
@router.get("/dhcp-leases")
def dhcp_leases(page_number:int=Query(1,alias="page",ge=1),page_size:int=Query(100,ge=1,le=1000),db:Session=Depends(get_db),_=Depends(reader)):
    return page(db.query(DiscoveryDHCPLease).order_by(DiscoveryDHCPLease.last_imported_at.desc()),page_number,page_size)
@router.post("/dhcp-leases/import")
def import_dhcp_leases(body:list[DHCPLeaseWrite],db:Session=Depends(get_db),user=Depends(admin)):
    if len(body)>10000:raise HTTPException(422,"A DHCP lease import is limited to 10,000 rows")
    imported=0
    for item in body:
        try:ipaddress.ip_address(item.ip_address)
        except ValueError as exc:raise HTTPException(422,f"Invalid DHCP lease address: {item.ip_address}") from exc
        mac=":".join(re.findall(r"[0-9a-fA-F]{2}",item.mac_address)).upper()
        if len(mac)!=17:raise HTTPException(422,f"Invalid DHCP lease MAC address for {item.ip_address}")
        row=db.query(DiscoveryDHCPLease).filter_by(source=item.source,ip_address=item.ip_address,mac_address=mac).first() or DiscoveryDHCPLease(source=item.source,ip_address=item.ip_address,mac_address=mac,created_by=user.id);db.add(row)
        for key,value in item.model_dump(exclude={"mac_address","ip_address","source"}).items():setattr(row,key,value)
        row.last_imported_at=datetime.now(timezone.utc);imported+=1
    audit(db,user,"IMPORT","discovery_dhcp_lease","batch",f"Imported {imported} DHCP lease records for correlation");db.commit();return {"imported":imported}
@router.get("/topology")
def topology(topology_id:UUID|None=None,db:Session=Depends(get_db),_=Depends(reader)):
    topology=db.get(Topology,topology_id) if topology_id else db.query(Topology).filter_by(enabled=True).order_by(Topology.is_default.desc()).first()
    if not topology:return {"topology":None,"nodes":[],"links":[],"message":"No reviewed topology exists yet"}
    return {"topology":topology,"nodes":db.query(TopologyNode).filter_by(topology_id=topology.id,is_hidden=False).all(),"links":db.query(TopologyLink).filter_by(topology_id=topology.id).all()}
@router.get("/history")
def history(db:Session=Depends(get_db),_=Depends(reader)):return {"jobs":db.query(DiscoveryJob).order_by(DiscoveryJob.created_at.desc()).limit(100).all(),"changes":db.query(DiscoveryChangeSuggestion).order_by(DiscoveryChangeSuggestion.created_at.desc()).limit(100).all()}
@router.post("/results/{id}/cmdb-sync")
def cmdb_sync(id:UUID,db:Session=Depends(get_db),user=Depends(admin)):
    row=get(db,DiscoveryResult,id,"Result")
    if row.review_status in ("ignored","false_positive","duplicate","retired"):raise HTTPException(409,"This review status cannot be synchronized")
    ci=db.get(ConfigurationItem,row.ci_id) if row.ci_id else None
    mac=re.sub(r"[^0-9a-f]","",(row.mac_address or "").lower())
    if not ci and mac:
        identifier=db.query(CIIdentifier).filter_by(identifier_type="mac",normalized_value=mac).first();ci=db.get(ConfigurationItem,identifier.ci_id) if identifier else None
    cls=db.query(CIClass).filter_by(code="discovered_infrastructure").first()
    if not cls:cls=CIClass(name="Discovered Infrastructure",code="discovered_infrastructure",domain="infrastructure",description="Verified discovery-managed CIs");db.add(cls);db.flush()
    code=re.sub(r"[^a-z0-9]+","_",row.classification.lower()).strip("_")[:75] or "unknown_device";typ=db.query(CIType).filter_by(code=f"discovery_{code}").first()
    if not typ:typ=CIType(class_id=cls.id,name=row.classification,code=f"discovery_{code}",category=row.device_type,attribute_schema="{}");db.add(typ);db.flush()
    created=False
    if not ci:
        ci=ConfigurationItem(ci_number=f"CI-DISC-{str(row.id)[:8].upper()}",name=row.primary_hostname or row.ip_address,display_name=row.primary_hostname or row.ip_address,type_id=typ.id,class_id=cls.id,category=row.classification,property_id=row.property_id,status="active",lifecycle_stage="operational",operational_status="online",manufacturer=row.vendor,discovery_source="network_discovery",source_reference=str(row.id),last_discovery_at=datetime.now(timezone.utc),verification_status="verified" if row.review_status=="manually_verified" else "discovered",created_by=user.id);db.add(ci);db.flush();created=True
    else:ci.last_discovery_at=datetime.now(timezone.utc);ci.operational_status="online";ci.manufacturer=row.vendor or ci.manufacturer;ci.updated_by=user.id
    row.ci_id=ci.id
    if mac and not db.query(CIIdentifier).filter_by(identifier_type="mac",normalized_value=mac).first():db.add(CIIdentifier(ci_id=ci.id,identifier_type="mac",value=row.mac_address,normalized_value=mac,primary=True,verified=row.review_status=="manually_verified",source="network_discovery"))
    audit(db,user,"SYNC","configuration_item",ci.id,"Synchronized verified discovery evidence without duplicate identifiers");db.commit();db.refresh(ci);return {"ci":ci,"created":created,"deduplicated":not created}
