"""V1-to-V2 inventory continuity reporting and safe, idempotent linkage.

This service never deletes or recreates inventory devices.  A reconciliation run
may only attach an unlinked discovery row to one unambiguous existing Device;
all inventory attributes and existing relationships remain untouched.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime,timezone

from sqlalchemy import func,or_

from app.models.audit_log import AuditLog
from app.models.device import Device
from app.models.discovered_device import DiscoveredDevice,ReviewStatus
from app.models.discovery_intelligence import DiscoveryEvidence,DiscoveryResult
from app.models.incidents import OperationalIncident
from app.models.network_scan import NetworkScan


def normalized_mac(value):
    compact=re.sub(r"[^0-9a-f]","",str(value or "").lower())
    return compact if len(compact)==12 else None


def normalized_hostname(value):
    text=str(value or "").strip().rstrip(".").lower().rstrip("$")
    return text.split(".",1)[0] if text else None


class V1V2ReconciliationService:
    """Preserve V1 records while connecting V2 observations to them."""

    def __init__(self,db):self.db=db

    @staticmethod
    def match_inventory(discovery,devices):
        """Return (device, reason, ambiguous); IP never overrides stronger data."""
        mac=normalized_mac(discovery.mac_address)
        if mac:
            matches=[row for row in devices if normalized_mac(row.mac_address)==mac]
            return (matches[0],"mac_address",False) if len(matches)==1 else (None,"mac_address",len(matches)>1)
        hostname=normalized_hostname(discovery.hostname)
        if hostname:
            matches=[row for row in devices if normalized_hostname(row.hostname)==hostname]
            return (matches[0],"hostname",False) if len(matches)==1 else (None,"hostname",len(matches)>1)
        matches=[row for row in devices if row.ip_address==discovery.ip_address]
        return None,"ip_supporting_only",bool(matches)

    @staticmethod
    def duplicate_candidates(devices):
        groups=[]
        for identifier,normalizer in (("mac_address",lambda row:normalized_mac(row.mac_address)),("hostname",lambda row:normalized_hostname(row.hostname)),("ip_address",lambda row:row.ip_address)):
            values=defaultdict(list)
            for row in devices:
                value=normalizer(row)
                if value:values[value].append(row)
            for value,rows in values.items():
                if len(rows)>1:groups.append({"identifier":identifier,"value":value,"device_ids":[str(row.id) for row in rows],"confidence":"strong" if identifier=="mac_address" else "review","action":"requires_review"})
        return groups

    @staticmethod
    def _snapshot(device):
        return {key:getattr(device,key,None) for key in ("id","hostname","ip_address","mac_address","department","location","device_type","inventory_status","status","asset_tag","serial_number","created_at","updated_at")}

    @staticmethod
    def apply_link(discovery,device,actor,observed_at=None):
        """Link only; deliberately never copy automatic values onto Device."""
        discovery.approved_device_id=device.id
        discovery.review_status=ReviewStatus.APPROVED
        discovery.reviewed_by=actor.id
        discovery.reviewed_at=observed_at or datetime.now(timezone.utc)

    def _result_for(self,device_id):
        return self.db.query(DiscoveryResult).join(DiscoveredDevice,DiscoveryResult.discovered_device_id==DiscoveredDevice.id).filter(DiscoveredDevice.approved_device_id==device_id).order_by(DiscoveryResult.last_seen_at.desc()).first()

    def _enrichment_state(self,result):
        if not result:return "unresolved"
        statuses={str(result.snmp_enrichment_status or "not_attempted"),str(result.ad_enrichment_status or "not_attempted")}
        if "enriched" in statuses and result.confidence_score>=60:return "enriched"
        evidence=self.db.query(func.count(DiscoveryEvidence.id)).filter(DiscoveryEvidence.result_id==result.id).scalar() or 0
        return "partially_enriched" if evidence or result.confidence_score>0 else "unresolved"

    def _relationship_health(self):
        scans=self.db.query(NetworkScan).count()
        scan_orphans=self.db.query(NetworkScan).outerjoin(Device,NetworkScan.device_id==Device.id).filter(Device.id.is_(None)).count()
        incident_filter=or_(OperationalIncident.device_id.is_not(None),OperationalIncident.source_reference_type=="device")
        incidents=self.db.query(OperationalIncident).filter(incident_filter).all()
        device_ids={row.id for row in self.db.query(Device.id).all()}
        incident_orphans=sum(1 for row in incidents if (row.device_id or row.source_reference_id) not in device_ids)
        return {"monitoring_observations":scans,"monitoring_orphans":scan_orphans,"linked_incidents":len(incidents),"incident_orphans":incident_orphans,"audit_records":self.db.query(AuditLog).count()}

    def report(self):
        devices=self.db.query(Device).order_by(Device.created_at,Device.id).all();duplicates=self.duplicate_candidates(devices)
        counts={"enriched":0,"partially_enriched":0,"unresolved":0};comparisons=[]
        for device in devices:
            result=self._result_for(device.id);state=self._enrichment_state(result);counts[state]+=1
            before=self._snapshot(device);after=dict(before)
            after.update({"friendly_name":getattr(result,"friendly_name",None),"v2_device_role":getattr(result,"device_type",None),"vendor":getattr(result,"vendor",None),"operating_system":getattr(result,"operating_system",None) or getattr(result,"ad_operating_system",None),"confidence_score":getattr(result,"confidence_score",0) if result else 0,"enrichment_status":state})
            conflicts=[]
            if result:
                for field in ("department","location","device_type"):
                    manual=getattr(device,field,None);automatic=getattr(result,field,None)
                    if manual not in (None,"","Unknown","Unassigned") and automatic not in (None,"") and str(manual).casefold()!=str(automatic).casefold():conflicts.append({"attribute":field,"preserved_value":manual,"discovered_value":automatic,"status":"requires_review"})
            comparisons.append({"device_id":str(device.id),"before":before,"after":after,"manual_conflicts":conflicts,"id_preserved":before["id"]==after["id"]})
        unlinked=self.db.query(DiscoveredDevice).filter(DiscoveredDevice.approved_device_id.is_(None)).all();ambiguous=[];clear=[]
        for row in unlinked:
            match,reason,is_ambiguous=self.match_inventory(row,devices)
            if is_ambiguous:ambiguous.append({"discovery_id":str(row.id),"reason":reason,"status":"requires_review"})
            elif match:clear.append({"discovery_id":str(row.id),"device_id":str(match.id),"reason":reason})
        health=self._relationship_health();errors=health["monitoring_orphans"]+health["incident_orphans"]
        return {"total_existing_v1_devices":len(devices),"preserved":len(devices),**counts,"potential_duplicates":len(duplicates),"requires_review":len(duplicates)+len(ambiguous),"errors":errors,"data_loss":False,"device_ids_preserved":all(row["id_preserved"] for row in comparisons),"approved_devices_preserved":sum(1 for row in devices if str(row.inventory_status).lower() not in {"pending","discovered","unresolved"}),"manual_data_preserved":True,"relationships":health,"duplicate_candidates":duplicates,"ambiguous_matches":ambiguous,"clear_link_candidates":clear,"comparisons":comparisons}

    def reconcile(self,actor):
        before={str(row.id):self._snapshot(row) for row in self.db.query(Device).all()};linked=0;represented=0;review=[]
        devices=self.db.query(Device).all();already_linked={row[0] for row in self.db.query(DiscoveredDevice.approved_device_id).filter(DiscoveredDevice.approved_device_id.is_not(None)).all()}
        for discovery in self.db.query(DiscoveredDevice).filter(DiscoveredDevice.approved_device_id.is_(None)).order_by(DiscoveredDevice.created_at).all():
            match,reason,ambiguous=self.match_inventory(discovery,devices)
            if ambiguous:review.append({"discovery_id":str(discovery.id),"reason":reason});continue
            if not match:continue
            if match.id in already_linked:represented+=1;continue
            self.apply_link(discovery,match,actor);already_linked.add(match.id);linked+=1
        self.db.flush()
        after={str(row.id):self._snapshot(row) for row in self.db.query(Device).all()}
        if before!=after:raise RuntimeError("Reconciliation attempted to modify authoritative inventory data")
        report=self.report();report.update({"linked_existing_devices":linked,"already_represented":represented,"review_queue":review})
        return report
