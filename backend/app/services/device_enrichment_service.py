"""Small provider-based, read-only enrichment orchestration for discovered devices."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import or_, select

from app.models.discovery_intelligence import DiscoveryEvidence, DiscoveryResult
from app.models.snmp import SNMPDeviceProfile, SNMPTarget
from app.services.audit_service import create_audit_log
from app.services.discovery_intelligence_service import WEIGHTS, confidence, review_status
from app.services.settings_service import read_discovery
from app.services.snmp_client_service import INTERFACE_OIDS, SNMPClientError, SecureSNMPClient

ENTITY_OIDS={
    "manufacturer":"1.3.6.1.2.1.47.1.1.1.1.12.1",
    "model":"1.3.6.1.2.1.47.1.1.1.1.13.1",
    "serial_number":"1.3.6.1.2.1.47.1.1.1.1.11.1",
    "firmware":"1.3.6.1.2.1.47.1.1.1.1.10.1",
}

@dataclass
class EnrichmentOutcome:
    status:str
    attributes:dict=field(default_factory=dict)
    evidence:list[dict]=field(default_factory=list)
    warnings:list[str]=field(default_factory=list)
    error_category:str|None=None

class EnrichmentProvider(Protocol):
    name:str
    def enrich(self,device:DiscoveryResult)->EnrichmentOutcome:...

def _value(value):
    if not value or getattr(value,"quality","good") == "missing":return None
    return value.value_text if getattr(value,"value_text",None) not in (None,"") else getattr(value,"value_numeric",None)

def _device_type(sys_description:str|None,profile_type:str|None=None)->str|None:
    if profile_type and profile_type not in ("generic_snmp_device","unknown"):return profile_type.replace("_"," ").title()
    text=(sys_description or "").lower()
    rules=(("Switch",("switch","catalyst")),("Router",("router","routing")),("Firewall",("firewall","fortigate","palo alto")),("Access Point",("access point","wireless ap")),("Printer",("printer","laserjet","officejet")),("UPS",("uninterruptible"," ups ")),("Server",("server","windows server","linux")),("Network Appliance",("network appliance",)))
    matches=[label for label,markers in rules if any(marker in f" {text} " for marker in markers)]
    return matches[0] if len(matches)==1 else None

def _vendor(manufacturer,sys_description,profile_vendor=None):
    if profile_vendor:return profile_vendor
    if manufacturer:return str(manufacturer).strip()
    text=(sys_description or "").lower()
    known=(("HP",("hewlett packard","hewlett-packard"," hp ","procurve","laserjet")),("Cisco",("cisco",)),("Aruba",("aruba",)),("Fortinet",("fortinet","fortigate")),("APC",("american power conversion"," apc ")),("Epson",("epson",)),("Brother",("brother",)))
    return next((name for name,markers in known if any(marker in f" {text} " for marker in markers)),None)

def _interfaces(preview):
    rows={}
    for key in ("interface.name","interface.description","interface.admin_status","interface.oper_status"):
        result=preview.get(key)
        for item in getattr(result,"items",[]) if result else []:
            match=re.search(r"\.(\d+)$",item.oid)
            if match:rows.setdefault(match.group(1),{})[key.split(".")[-1]]=_value(item)
    return [{"index":int(index),**values} for index,values in sorted(rows.items(),key=lambda pair:int(pair[0]))]

class SNMPEnrichmentProvider:
    name="SNMP"
    def __init__(self,db,client_factory=SecureSNMPClient,max_interfaces=64):self.db=db;self.client_factory=client_factory;self.max_interfaces=max_interfaces
    def _target(self,device):
        conditions=[SNMPTarget.ip_address==device.ip_address]
        if device.discovered_device_id:conditions.insert(0,SNMPTarget.discovered_device_id==device.discovered_device_id)
        return self.db.scalar(select(SNMPTarget).where(SNMPTarget.enabled.is_(True),or_(*conditions)).order_by(SNMPTarget.discovered_device_id.desc().nullslast()))
    def enrich(self,device):
        target=self._target(device)
        if not target:return EnrichmentOutcome("unavailable",warnings=["No enabled SNMP target is configured for this device."],error_category="target_missing")
        settings=read_discovery(self.db);authorized=settings.get("authorized_cidr_ranges","");ignored=settings.get("ignore_ranges","")
        authorized=[x.strip() for x in authorized.split(",") if x.strip()] if isinstance(authorized,str) else authorized
        ignored=[x.strip() for x in ignored.split(",") if x.strip()] if isinstance(ignored,str) else ignored
        client=None
        try:
            client=self.client_factory(target,target.credential,authorized_networks=authorized,ignored_networks=ignored)
            identity=client.get_system_identity();hardware=dict(zip(ENTITY_OIDS,client.get_many(list(ENTITY_OIDS.values()))))
            attrs={"sys_name":_value(identity.get("system.name")),"sys_description":_value(identity.get("system.description")),"sys_object_id":_value(identity.get("system.object_id")),"uptime_seconds":getattr(identity.get("system.uptime"),"seconds",None),"model":_value(hardware.get("model")),"serial_number":_value(hardware.get("serial_number")),"firmware":_value(hardware.get("firmware"))}
            profile=self.db.get(SNMPDeviceProfile,target.detected_profile_id) if target.detected_profile_id else None
            attrs["vendor"]=_vendor(_value(hardware.get("manufacturer")),attrs["sys_description"],profile.vendor if profile else None)
            attrs["device_type"]=_device_type(attrs["sys_description"],profile.device_type if profile else None)
            warnings=[]
            try:attrs["interfaces"]=_interfaces(client.get_interfaces_preview(max_interfaces=self.max_interfaces));attrs["interface_count"]=len(attrs["interfaces"])
            except SNMPClientError as error:attrs["interfaces"]=[];attrs["interface_count"]=None;warnings.append(error.safe_message)
            found=[key for key,value in attrs.items() if value not in (None,"",[],{})]
            evidence=[{"evidence_type":"snmp","source":"snmp_read_only","value":attrs.get("sys_object_id") or target.id,"verified":True}]
            for key in ("vendor","model","serial_number","firmware","uptime_seconds","interface_count","sys_name","sys_description","sys_object_id","device_type"):
                if attrs.get(key) not in (None,""):evidence.append({"evidence_type":key if key!="vendor" else "vendor_match","source":"snmp", "value":attrs[key],"verified":True})
            if attrs.get("sys_name") and getattr(device,"primary_hostname",None):
                snmp_name=str(attrs["sys_name"]).strip().lower().split(".",1)[0]
                known_name=str(device.primary_hostname).strip().lower().split(".",1)[0]
                if snmp_name==known_name:
                    evidence.append({"evidence_type":"hostname_match","source":"snmp_agreement","value":attrs["sys_name"],"verified":True})
            status="enriched" if all(attrs.get(key) not in (None,"") for key in ("vendor","model","serial_number","uptime_seconds")) else "partially_enriched"
            target.last_test_status="success";target.last_test_message="Read-only SNMP enrichment completed.";target.detected_sys_object_id=attrs.get("sys_object_id");target.last_tested_at=datetime.now(timezone.utc)
            return EnrichmentOutcome(status,attrs,evidence,warnings+[f"{key.replace('_',' ').title()} unavailable." for key in ("vendor","model","serial_number","firmware","uptime_seconds") if not attrs.get(key)])
        except SNMPClientError as error:
            target.last_test_status="failed";target.last_test_message=error.safe_message;target.last_tested_at=datetime.now(timezone.utc)
            return EnrichmentOutcome("unavailable",warnings=[error.safe_message],error_category=error.category)
        finally:
            if client:client.close()

class DeviceEnrichmentService:
    def __init__(self,db,provider=None):self.db=db;self.provider=provider or SNMPEnrichmentProvider(db)
    def enrich(self,result,actor):
        result.snmp_enrichment_status="attempted";self.db.flush();outcome=self.provider.enrich(result);now=datetime.now(timezone.utc)
        result.snmp_enrichment_status=outcome.status;result.snmp_last_error=outcome.error_category;result.last_enriched_at=now
        attrs=outcome.attributes
        for source,target in (("vendor","vendor"),("model","model"),("serial_number","serial_number"),("firmware","firmware"),("sys_description","sys_description"),("sys_object_id","sys_object_id"),("uptime_seconds","uptime_seconds"),("interface_count","interface_count")):
            if attrs.get(source) not in (None,""):setattr(result,target,attrs[source])
        if attrs.get("sys_name") and not result.primary_hostname:result.primary_hostname=str(attrs["sys_name"]).lower()
        if attrs.get("device_type") and result.device_type in (None,"Unknown Device","Unknown"):result.device_type=attrs["device_type"];result.classification=attrs["device_type"]
        if "interfaces" in attrs:result.interface_information=json.dumps(attrs["interfaces"],default=str)
        for raw in outcome.evidence:
            norm=str(raw["value"]).strip().lower()[:500]
            exists=self.db.scalar(select(DiscoveryEvidence).where(DiscoveryEvidence.result_id==result.id,DiscoveryEvidence.evidence_type==raw["evidence_type"],DiscoveryEvidence.source==raw["source"],DiscoveryEvidence.normalized_value==norm))
            if not exists:self.db.add(DiscoveryEvidence(result_id=result.id,evidence_type=raw["evidence_type"],source=raw["source"],value=json.dumps(raw["value"],default=str),normalized_value=norm,weight=WEIGHTS.get(raw["evidence_type"],0),verified=raw.get("verified",False)))
        self.db.flush();types=[row[0] for row in self.db.execute(select(DiscoveryEvidence.evidence_type).where(DiscoveryEvidence.result_id==result.id).distinct()).all()];score=confidence(types);result.confidence_score=score["score"];result.confidence_explanation=json.dumps(score["contributions"])
        if result.review_status!="manually_verified":result.review_status=review_status(result.confidence_score)
        if hasattr(result,"canonical_result_id"):
            from app.services.device_correlation_service import DeviceCorrelationService
            result=DeviceCorrelationService(self.db).correlate(result,"snmp_enrichment")
        from app.models.hierarchy import Property
        from app.services.device_identity_service import DeviceIdentityService
        prop=self.db.get(Property,result.property_id) if getattr(result,"property_id",None) else None
        if prop:DeviceIdentityService(self.db).apply(result,prop.organization_id,actor.username)
        create_audit_log(self.db,actor.username,"ENRICH_DISCOVERY","DiscoveryResult",str(result.id),f"Read-only {self.provider.name} enrichment completed with status {outcome.status}.")
        self.db.commit();self.db.refresh(result)
        return {"status":outcome.status,"provider":self.provider.name,"device":result,"found":sorted(key for key,value in attrs.items() if value not in (None,"",[],{})),"warnings":outcome.warnings,"evidence_added":len(outcome.evidence),"confidence_score":result.confidence_score}
