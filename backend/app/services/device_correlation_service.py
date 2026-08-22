"""Deterministic V2D correlation for discovery results; no external infrastructure writes."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass,field
from datetime import datetime,timezone

from sqlalchemy import or_,select

from app.models.discovery_intelligence import DiscoveryEvidence,DiscoveryIdentityConflict,DiscoveryIdentityHistory,DiscoveryResult
from app.services.discovery_intelligence_service import WEIGHTS,confidence,review_status


def normalized_mac(value):
    compact=re.sub(r"[^0-9a-f]","",str(value or "").lower());return compact if len(compact)==12 else None
def normalized_hostname(value):
    text=str(value or "").strip().rstrip(".").lower().rstrip("$");return text.split(".",1)[0] if text else None
def normalized_fqdn(value):
    text=str(value or "").strip().rstrip(".").lower();return text if "." in text else None
def _usable_serial(value):
    text=str(value or "").strip().lower();return text if text and not text.startswith("unknown") and text not in {"n/a","not available"} else None
def confidence_level(score):return "very_high" if score>=85 else "high" if score>=60 else "medium" if score>=30 else "low"


@dataclass
class CorrelationDecision:
    matched:bool
    canonical:DiscoveryResult|None=None
    strength:int=0
    identifiers:list[str]=field(default_factory=list)
    supporting:list[str]=field(default_factory=list)
    ambiguous:bool=False


class DeviceCorrelationService:
    DYNAMIC_FIELDS=("ip_address","primary_hostname","fqdn")
    FILL_FIELDS=("mac_address","friendly_name","department","suggested_department","device_number","description","description_source","location","vendor","operating_system","model","serial_number","firmware","sys_description","sys_object_id","uptime_seconds","interface_count","interface_information","ad_computer_name","ad_distinguished_name","ad_domain","ad_organizational_unit","ad_description","ad_operating_system","ad_operating_system_version","ad_enabled","ad_last_logon_at")
    def __init__(self,db):self.db=db
    def root(self,result):return self.db.get(DiscoveryResult,result.canonical_result_id) if result.canonical_result_id else result
    def group_ids(self,result):
        root=self.root(result);return [root.id,*self.db.scalars(select(DiscoveryResult.id).where(DiscoveryResult.canonical_result_id==root.id)).all()]
    def evidence(self,result):return self.db.scalars(select(DiscoveryEvidence).where(DiscoveryEvidence.result_id.in_(self.group_ids(result))).order_by(DiscoveryEvidence.observed_at.desc())).all()
    def history(self,result):return self.db.scalars(select(DiscoveryIdentityHistory).where(DiscoveryIdentityHistory.result_id==self.root(result).id).order_by(DiscoveryIdentityHistory.observed_at.desc())).all()
    def conflicts(self,result,open_only=False):
        query=select(DiscoveryIdentityConflict).where(DiscoveryIdentityConflict.result_id==self.root(result).id)
        if open_only:query=query.where(DiscoveryIdentityConflict.status=="open")
        return self.db.scalars(query.order_by(DiscoveryIdentityConflict.detected_at.desc())).all()
    def _identity(self,row):
        return {"mac":normalized_mac(row.mac_address),"stable_discovery":str(row.discovered_device_id) if row.discovered_device_id else None,"serial":_usable_serial(row.serial_number),"hostname":{x for x in (normalized_hostname(row.primary_hostname),normalized_hostname(row.ad_computer_name)) if x},"fqdn":{x for x in (normalized_fqdn(row.fqdn),normalized_fqdn(getattr(row,"ad_computer_name",None))) if x},"ip":row.ip_address}
    def compare(self,incoming,candidate):
        left,right=self._identity(incoming),self._identity(candidate);identifiers=[];strength=0
        for key,weight in (("mac",100),("stable_discovery",95),("serial",90)):
            if left[key] and left[key]==right[key]:identifiers.append(key);strength=max(strength,weight)
        if left["mac"] and right["mac"] and left["mac"]!=right["mac"] and not identifiers:return CorrelationDecision(False,candidate,supporting=["conflicting_mac"])
        if left["hostname"]&right["hostname"]:identifiers.append("hostname");strength=max(strength,80)
        if left["fqdn"]&right["fqdn"]:identifiers.append("fqdn");strength=max(strength,75)
        supporting=["ip_address"] if left["ip"]==right["ip"] else []
        return CorrelationDecision(bool(identifiers),candidate,strength,identifiers,supporting)
    def find_match(self,result):
        candidates=self.db.scalars(select(DiscoveryResult).where(DiscoveryResult.id!=result.id,DiscoveryResult.canonical_result_id.is_(None))).all();decisions=[self.compare(result,row) for row in candidates];matches=[row for row in decisions if row.matched]
        if not matches:return CorrelationDecision(False,supporting=["ip_address"] if any(result.ip_address==row.ip_address for row in candidates) else [])
        best=max(row.strength for row in matches);strong=[row for row in matches if row.strength==best]
        if len(strong)>1:return CorrelationDecision(False,strength=best,identifiers=sorted({item for row in strong for item in row.identifiers}),ambiguous=True)
        return strong[0]
    def _history(self,root,attribute,previous,current,source):
        if previous!=current:self.db.add(DiscoveryIdentityHistory(result_id=root.id,attribute=attribute,previous_value=None if previous is None else str(previous),current_value=str(current),source=source))
    def _conflict(self,root,attribute,left,left_source,right,right_source):
        if left in (None,"") or right in (None,"") or str(left).strip().casefold()==str(right).strip().casefold():return
        values=sorted((f"{left_source}:{str(left).strip().casefold()}",f"{right_source}:{str(right).strip().casefold()}"));signature=hashlib.sha256(f"{attribute}|{'|'.join(values)}".encode()).hexdigest()
        existing=self.db.scalar(select(DiscoveryIdentityConflict).where(DiscoveryIdentityConflict.result_id==root.id,DiscoveryIdentityConflict.signature==signature))
        if existing:existing.status="open";existing.resolved_at=None;existing.resolved_by=None
        else:self.db.add(DiscoveryIdentityConflict(result_id=root.id,attribute=attribute,left_value=str(left),left_source=left_source,right_value=str(right),right_source=right_source,signature=signature))
    def _merge(self,root,incoming,source):
        for field in self.DYNAMIC_FIELDS:
            value=getattr(incoming,field,None);previous=getattr(root,field,None)
            if value and value!=previous:self._history(root,field,previous,value,source);setattr(root,field,value)
        for field in self.FILL_FIELDS:
            value=getattr(incoming,field,None)
            if getattr(root,field,None) in (None,"") and value not in (None,""):setattr(root,field,value)
        if not root.identity_confirmed:
            for field in ("device_type","classification"):
                incoming_value=getattr(incoming,field,None);root_value=getattr(root,field,None)
                if root_value in (None,"Unknown","Unknown Device") and incoming_value not in (None,"Unknown","Unknown Device"):setattr(root,field,incoming_value)
        root.first_seen_at=min(root.first_seen_at,incoming.first_seen_at);root.last_seen_at=max(root.last_seen_at,incoming.last_seen_at)
    @staticmethod
    def _evidence_value(row,field=None):
        try:value=json.loads(row.value)
        except (TypeError,ValueError):value=row.value
        if field and isinstance(value,dict):value=value.get(field)
        return value
    def detect_conflicts(self,result):
        root=self.root(result);rows=self.evidence(root)
        self._conflict(root,"hostname",root.primary_hostname,"DNS/discovery",root.ad_computer_name,"Active Directory")
        if root.description_source!="Active Directory":self._conflict(root,"description",root.description,root.description_source or "Discovery",root.ad_description,"Active Directory")
        hostname_types=[(self._evidence_value(row,"device_type"),row.source) for row in rows if row.evidence_type=="hostname_rule"]
        snmp_types=[(self._evidence_value(row),row.source) for row in rows if row.evidence_type=="device_type" and "snmp" in row.source.lower()]
        for left,left_source in hostname_types:
            for right,right_source in snmp_types:self._conflict(root,"device_type",left,left_source,right,right_source)
        self.db.flush();open_rows=self.conflicts(root,open_only=True);root.conflict_status="open" if open_rows else "resolved" if self.conflicts(root) else "none";return open_rows
    def apply_hostname_identity(self,result):
        """Apply naming-rule role suggestions without replacing a confirmed identity.

        ``classification`` may describe the technical platform (for example Windows
        Server), while ``device_type`` is the operational role suggested by the
        administrator's hostname rules (for example Point of Sale).
        """
        root=self.root(result)
        if root.identity_confirmed:return root
        for row in self.evidence(root):
            if row.evidence_type!="hostname_rule":continue
            value=self._evidence_value(row)
            if not isinstance(value,dict):continue
            for field in ("friendly_name","department","device_type"):
                suggested=value.get(field)
                if suggested not in (None,""):setattr(root,field,suggested)
            break
        return root
    def calculate_confidence(self,result):
        root=self.root(result);rows=self.evidence(root);types={row.evidence_type for row in rows};base=confidence(types)["score"]
        groups={"mac":{},"hostname":{},"description":{},"device_type":{}}
        for row in rows:
            group=None;value=None
            if row.evidence_type=="mac_address":group="mac";value=normalized_mac(self._evidence_value(row))
            elif row.evidence_type in {"hostname_match","sys_name","ad_match"}:group="hostname";value=normalized_hostname(self._evidence_value(row))
            elif row.evidence_type=="description":group="description";value=str(self._evidence_value(row) or "").strip().casefold()
            elif row.evidence_type in {"device_type","hostname_rule"}:group="device_type";value=str(self._evidence_value(row,"device_type") or self._evidence_value(row) or "").strip().casefold()
            if group and value:groups[group].setdefault(value,set()).add(row.source)
        bonuses={"mac":10,"hostname":10,"description":5,"device_type":5};agreements=[name for name,values in groups.items() if any(len(sources)>=2 for sources in values.values())];bonus=min(20,sum(bonuses[name] for name in agreements));open_conflicts=len(self.conflicts(root,open_only=True));penalty=min(45,open_conflicts*15);raw=max(0,base+bonus-penalty);score=min(100 if root.identity_confirmed and not open_conflicts else 95,raw)
        reasons=[]
        if types:reasons.append(f"{len(types)} distinct evidence types")
        if agreements:reasons.append("agreement across "+", ".join(agreements))
        if open_conflicts:reasons.append(f"{open_conflicts} unresolved conflict{'s' if open_conflicts!=1 else ''} reduced confidence")
        if root.identity_confirmed:reasons.append("administrator-confirmed identity")
        if not reasons:reasons.append("insufficient identifying evidence")
        root.confidence_score=score;root.confidence_level=confidence_level(score);root.confidence_reason="; ".join(reasons).capitalize()+".";root.confidence_explanation=json.dumps({"base":base,"agreement_bonus":bonus,"conflict_penalty":penalty,"manual_confirmation":root.identity_confirmed,"evidence_types":sorted(types),"agreements":agreements});
        if root.review_status!="manually_verified":root.review_status=review_status(score)
        return {"score":score,"level":root.confidence_level,"reason":root.confidence_reason,"base":base,"agreement_bonus":bonus,"conflict_penalty":penalty}
    def refresh(self,result):
        root=self.root(result);self.apply_hostname_identity(root);self.detect_conflicts(root);self.calculate_confidence(root);return root
    def correlate(self,result,source="discovery"):
        if result.canonical_result_id:return self.refresh(result)
        decision=self.find_match(result)
        if decision.ambiguous:self._conflict(result,"identity","Current observation",source,"Multiple equally strong candidates","correlation");return self.refresh(result)
        if not decision.matched:return self.refresh(result)
        root=self.root(decision.canonical);result.canonical_result_id=root.id;self._merge(root,result,source);self.db.flush();return self.refresh(root)
    def confirm(self,result,actor,values):
        root=self.root(result)
        from app.models.hierarchy import Property
        from app.services.device_identity_service import DeviceIdentityService
        prop=self.db.get(Property,root.property_id) if root.property_id else None
        profile=DeviceIdentityService(self.db).profile(root,prop.organization_id,create=True) if prop else None
        for field in ("friendly_name","department","device_type","location"):
            value=values.get(field)
            if value:
                previous=getattr(root,field,None);self._history(root,field,previous,value,"manual_confirmation");setattr(root,field,value)
                if field=="device_type":root.classification=value
                if profile:
                    if field=="friendly_name":profile.friendly_name_source="MANUAL";profile.friendly_name_confidence=100
                    elif field=="device_type":profile.classification_source="MANUAL";profile.classification_confidence=100
                    elif field=="department":profile.department_source="MANUAL"
                    elif field=="location":profile.location_source="MANUAL"
        root.identity_confirmed=True;root.confirmed_by=actor.id;root.confirmed_at=datetime.now(timezone.utc);root.review_status="manually_verified"
        existing=self.db.scalar(select(DiscoveryEvidence).where(DiscoveryEvidence.result_id==root.id,DiscoveryEvidence.evidence_type=="manual_confirmation",DiscoveryEvidence.source=="administrator"))
        payload={field:getattr(root,field) for field in ("friendly_name","department","device_type","location")}
        if existing:existing.value=json.dumps(payload);existing.normalized_value=str(actor.id);existing.verified=True
        else:self.db.add(DiscoveryEvidence(result_id=root.id,evidence_type="manual_confirmation",source="administrator",value=json.dumps(payload),normalized_value=str(actor.id),weight=WEIGHTS["manual_confirmation"],verified=True))
        for conflict in self.conflicts(root,open_only=True):conflict.status="resolved";conflict.resolved_by=actor.id;conflict.resolved_at=datetime.now(timezone.utc)
        root.conflict_status="resolved" if self.conflicts(root) else "none";self.db.flush();self.calculate_confidence(root);return root
