import csv
import io
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.core.tenant import organization_context
from app.models.alert import Alert
from app.models.asset_intelligence import ManagedAsset
from app.models.asset_management import Vendor
from app.models.change_management import ChangeRequest
from app.models.device import Device
from app.models.hierarchy import Department, Property, Room
from app.models.hospitality_operations import HospitalityTechnologyService
from app.models.incidents import OperationalIncident
from app.models.knowledge import KnowledgeArticle, KnowledgeRating
from app.models.network_scan import NetworkScan
from app.models.problem_management import Problem, ProblemRelationship
from app.models.procurement import AssetProcurement, ProcurementLineItem
from app.models.snmp import SNMPInterface, SNMPTarget
from app.models.topology import NetworkSegment, TopologyNode

router=APIRouter(prefix="/reporting",tags=["Organization Reporting"])
reader=require_roles(["platformadmin","admin","technician","viewer"])
REPORTS={"executive","operations","network","assets","lifecycle","incidents","problems","changes","procurement","vendors","knowledge","services","departments","locations"}
PERIODS={"today":0,"7d":7,"30d":30,"90d":90,"month":30,"quarter":90,"year":365}

def bounds(period,start,end):
    now=datetime.now(timezone.utc)
    if period=="custom":
        if not start or not end or end<start:raise HTTPException(422,"A valid custom date range is required")
        return start,end
    if period not in PERIODS:raise HTTPException(422,"Unsupported reporting period")
    days=PERIODS[period]
    return (now.replace(hour=0,minute=0,second=0,microsecond=0) if days==0 else now-timedelta(days=days)),now

def groups(rows,field):
    values=Counter((getattr(x,field,None) or "Unknown") for x in rows)
    return [{"label":str(k),"value":v} for k,v in values.most_common()]
def trend(rows,field,start,end):
    dated=[getattr(x,field,None) for x in rows];dated=[x for x in dated if x and start<=x<=end]
    if len(dated)<2:return {"status":"insufficient_data","message":"Insufficient data","points":[]}
    counts=Counter(x.date().isoformat() for x in dated)
    return {"status":"available","points":[{"date":k,"value":counts[k]} for k in sorted(counts)]}
def metric(value,label,drilldown=None,quality="available"):
    return {"label":label,"value":value if value is not None else "Insufficient data","quality":quality if value is not None else "insufficient_data","drilldown":drilldown}

def context(db,org,start,end):
    property_ids=[x[0] for x in db.query(Property.id).filter_by(organization_id=org).all()]
    devices=db.query(Device).filter(Device.property_id.in_(property_ids)).all() if property_ids else []
    device_ids=[x.id for x in devices]
    assets=db.query(ManagedAsset).filter_by(organization_id=org).all()
    incidents=db.query(OperationalIncident).filter_by(organization_id=org).all()
    problems=db.query(Problem).filter_by(organization_id=org).all()
    changes=db.query(ChangeRequest).filter_by(organization_id=org).all()
    procurement=db.query(AssetProcurement).filter_by(organization_id=org).all()
    vendors=db.query(Vendor).filter_by(organization_id=org).all()
    knowledge=db.query(KnowledgeArticle).filter_by(organization_id=org).all()
    services=db.query(HospitalityTechnologyService).filter_by(organization_id=org).all()
    departments=db.query(Department).filter_by(organization_id=org).all()
    rooms=db.query(Room).filter_by(organization_id=org).all()
    alerts=db.query(Alert).filter(Alert.device_id.in_(device_ids)).all() if device_ids else []
    scans=db.query(NetworkScan).filter(NetworkScan.device_id.in_(device_ids),NetworkScan.scanned_at>=start,NetworkScan.scanned_at<=end).all() if device_ids else []
    return locals()

def build(report,db,org,start,end,filters):
    c=context(db,org,start,end);assets=c["assets"];devices=c["devices"];incidents=c["incidents"];problems=c["problems"];changes=c["changes"];procurements=c["procurement"];vendors=c["vendors"];knowledge=c["knowledge"];services=c["services"];alerts=c["alerts"];scans=c["scans"]
    if filters.get("department_id"):
        dep=UUID(filters["department_id"]);assets=[x for x in assets if x.department_id==dep];incidents=[x for x in incidents if x.department_id==dep];problems=[x for x in problems if x.department_id==dep];procurements=[x for x in procurements if x.department_id==dep];services=[x for x in services if x.department_id==dep]
    if filters.get("service_id"):
        sid=UUID(filters["service_id"]);incidents=[x for x in incidents if x.technology_service_id==sid];problems=[x for x in problems if x.technology_service_id==sid];changes=[x for x in changes if x.technology_service_id==sid];services=[x for x in services if x.id==sid]
    if filters.get("location_id"):
        location=UUID(filters["location_id"]);assets=[x for x in assets if x.room_id==location];incidents=[x for x in incidents if x.room_id==location]
    if filters.get("device_type"):
        kind=filters["device_type"].lower();assets=[x for x in assets if x.device_type.lower()==kind];devices=[x for x in devices if x.device_type.lower()==kind]
    if filters.get("vendor_id"):
        vendor=UUID(filters["vendor_id"]);assets=[x for x in assets if x.vendor_id==vendor];procurements=[x for x in procurements if x.vendor_id==vendor];vendors=[x for x in vendors if x.id==vendor]
    if filters.get("status"):
        value=filters["status"]
        assets=[x for x in assets if x.status==value];incidents=[x for x in incidents if x.status==value];problems=[x for x in problems if x.status==value];changes=[x for x in changes if x.status==value];procurements=[x for x in procurements if x.status==value];vendors=[x for x in vendors if x.status==value];knowledge=[x for x in knowledge if x.status==value];services=[x for x in services if x.status==value]
    today=date.today();metrics=[];breakdowns={};trends={};drilldowns={};insufficient=[]
    if report in {"executive","assets","lifecycle"}:
        metrics += [metric(len(assets),"Managed Assets","/devices"),metric(sum(x.status=="in_maintenance" for x in assets),"Assets in Maintenance","/devices?lifecycle=in_maintenance"),metric(sum(bool(x.warranty_end and today<=x.warranty_end<=today+timedelta(days=90)) for x in assets),"Warranty Expiring in 90 Days","/devices?warranty=expiring")]
        breakdowns.update({"assets_by_type":groups(assets,"device_type"),"assets_by_status":groups(assets,"status"),"assets_by_condition":groups(assets,"condition"),"assets_by_department":groups(assets,"department_name"),"assets_by_location":groups(assets,"location_name")})
        if report=="lifecycle":
            dated=[x for x in assets if x.acquisition_date]
            avg_age=round(sum((today-x.acquisition_date).days for x in dated)/len(dated)/365.25,1) if dated else None
            metrics += [metric(avg_age,"Average Asset Age (years)",quality="available" if dated else "insufficient_data"),metric(sum(bool(x.expected_replacement_date and today<=x.expected_replacement_date<=today+timedelta(days=365)) for x in assets),"Expected Replacement Within 12 Months")]
    if report in {"executive","operations","network"}:
        latest={}
        for scan in sorted(scans,key=lambda x:x.scanned_at):latest[scan.device_id]=scan
        online=sum(x.status.lower()=="online" for x in latest.values());offline=sum(x.status.lower()=="offline" for x in latest.values());known=len(latest)
        availability=round(sum(x.status.lower()=="online" for x in scans)*100/len(scans),2) if scans else None
        metrics += [metric(len(devices),"Devices","/network"),metric(online,"Online Devices","/network?status=online"),metric(offline,"Offline Devices","/network?status=offline"),metric(len(devices)-known,"Unknown Devices","/network?status=unknown"),metric(availability,"Availability %")]
        trends["availability"]={"status":"available","points":[{"date":day,"value":round(sum(x.status.lower()=="online" for x in scans if x.scanned_at.date().isoformat()==day)*100/sum(1 for x in scans if x.scanned_at.date().isoformat()==day),2)} for day in sorted({x.scanned_at.date().isoformat() for x in scans})]} if scans else {"status":"insufficient_data","message":"Insufficient data","points":[]}
        if report=="network":
            network_types={"switch","router","access point","firewall","network appliance"};infra=[x for x in devices if x.device_type.lower() in network_types]
            target_ids=[x[0] for x in db.query(SNMPTarget.id).filter(SNMPTarget.device_id.in_([x.id for x in infra])).all()] if infra else []
            interfaces=db.query(SNMPInterface).filter(SNMPInterface.target_id.in_(target_ids)).all() if target_ids else []
            topology_ids=list({x[0] for x in db.query(TopologyNode.topology_id).filter(TopologyNode.device_id.in_([x.id for x in devices])).all()}) if devices else []
            segments=db.query(NetworkSegment).filter(NetworkSegment.topology_id.in_(topology_ids)).all() if topology_ids else []
            metrics += [metric(len(infra),"Network Devices"),metric(sum(x.operational_status and x.operational_status.lower()!="up" for x in interfaces),"Interfaces Not Up"),metric(len(segments),"Network Segments / VLANs")]
            breakdowns["network_devices_by_type"]=groups(infra,"device_type")
    if report in {"executive","operations","incidents"}:
        current=[x for x in incidents if x.created_at and start<=x.created_at<=end];resolved=[x for x in current if x.resolved_at]
        ack=[(x.acknowledged_at-x.created_at).total_seconds() for x in current if x.acknowledged_at];resolution=[(x.resolved_at-x.created_at).total_seconds() for x in current if x.resolved_at]
        metrics += [metric(len(current),"Incident Volume","/incidents"),metric(sum(x.status not in {"resolved","closed"} for x in incidents),"Open Incidents","/incidents?status=open"),metric(sum(x.severity=="critical" and x.status not in {"resolved","closed"} for x in incidents),"Critical Incidents","/incidents?severity=critical")]
        if report=="incidents":metrics += [metric(round(sum(ack)/len(ack)/60,1) if ack else None,"Average Acknowledge Time (minutes)"),metric(round(sum(resolution)/len(resolution)/3600,1) if resolution else None,"Average Resolution Time (hours)"),metric(sum(bool(x.duplicate_of_id) for x in incidents),"Recurring / Duplicate Incidents")]
        breakdowns.update({"incidents_by_status":groups(incidents,"status"),"incidents_by_category":groups(incidents,"category"),"incidents_by_team":groups(incidents,"assigned_team")});trends["incident_volume"]=trend(incidents,"created_at",start,end)
    if report in {"executive","problems"}:
        metrics += [metric(sum(x.status in {"open","investigating","known_error"} for x in problems),"Open Problems","/problems"),metric(sum(x.status=="known_error" for x in problems),"Known Errors","/problems?status=known_error")]
        if report=="problems":metrics += [metric(sum(db.query(ProblemRelationship).filter_by(problem_id=x.id,target_type="incident").count()>1 for x in problems),"Problems Linked to Recurring Incidents")]
        breakdowns.update({"problems_by_status":groups(problems,"status"),"problems_by_category":groups(problems,"impact"),"problems_by_team":groups(problems,"assigned_team")});trends["problem_volume"]=trend(problems,"created_at",start,end)
    if report in {"executive","changes"}:
        completed=[x for x in changes if x.outcome in {"successful","failed","rolled_back"}];success=sum(x.outcome=="successful" for x in completed)
        metrics += [metric(sum(x.status=="scheduled" for x in changes),"Scheduled Changes","/changes?status=scheduled"),metric(sum(x.risk_level in {"high","critical"} and x.status not in {"closed","cancelled"} for x in changes),"High-Risk Changes","/changes?risk=high")]
        if report=="changes":metrics += [metric(len(changes),"Total Changes"),metric(round(success*100/len(completed),2) if completed else None,"Change Success Rate %")]
        breakdowns.update({"changes_by_status":groups(changes,"status"),"changes_by_type":groups(changes,"change_type"),"changes_by_risk":groups(changes,"risk_level")});trends["change_volume"]=trend(changes,"created_at",start,end)
    if report=="procurement":
        ids=[x.id for x in procurements];items=db.query(ProcurementLineItem).filter(ProcurementLineItem.procurement_id.in_(ids)).all() if ids else [];total=sum(x.quantity_requested*x.unit_cost for x in items)
        metrics += [metric(len(procurements),"Procurement Records","/procurement"),metric(str(total),"Total Acquisition Value"),metric(sum(bool(x.expected_delivery_date and x.expected_delivery_date<today and x.status not in {"received","cancelled"}) for x in procurements),"Overdue Deliveries")]
        breakdowns.update({"procurement_by_status":groups(procurements,"status"),"procurement_by_currency":groups(procurements,"currency")});trends["procurement_volume"]=trend(procurements,"created_at",start,end)
    if report=="vendors":
        metrics += [metric(sum(x.status=="active" for x in vendors),"Active Vendors","/vendors"),metric(sum(bool(x.vendor_id) for x in assets),"Assets With Vendor"),metric(sum(bool(x.vendor_id) for x in procurements),"Procurement With Vendor")];breakdowns["assets_by_vendor"]=groups(assets,"vendor")
    if report=="knowledge":
        ratings=db.query(KnowledgeRating).filter(KnowledgeRating.article_id.in_([x.id for x in knowledge])).all() if knowledge else []
        metrics += [metric(len(knowledge),"Total Articles","/knowledge"),metric(sum(x.status=="published" for x in knowledge),"Published"),metric(sum(x.next_review_at and x.next_review_at<datetime.now(timezone.utc) for x in knowledge),"Review Due"),metric(sum(x.rating==1 for x in ratings),"Helpful Feedback"),metric(sum(x.rating==0 for x in ratings),"Not Helpful Feedback")]
        breakdowns["knowledge_by_status"]=groups(knowledge,"status");breakdowns["most_viewed"]=[{"label":x.title,"value":x.view_count,"id":str(x.id)} for x in sorted(knowledge,key=lambda x:x.view_count,reverse=True)[:10] if x.view_count]
    if report=="services":
        metrics += [metric(len(services),"Technology Services","/incidents/services"),metric(sum(x.status=="operational" for x in services),"Operational"),metric(sum(x.status=="degraded" for x in services),"Degraded"),metric(sum(x.status=="outage" for x in services),"Outage"),metric(sum(x.status=="unknown" for x in services),"Unknown")];breakdowns["services_by_status"]=groups(services,"status")
    if report=="departments":
        rows=[]
        for dep in c["departments"]:rows.append({"label":dep.name,"assets":sum(x.department_id==dep.id for x in assets),"incidents":sum(x.department_id==dep.id for x in incidents),"problems":sum(x.department_id==dep.id for x in problems),"services":sum(x.department_id==dep.id for x in services)})
        metrics.append(metric(len(c["departments"]),"Departments"));breakdowns["departments"]=rows
    if report=="locations":
        rows=[]
        for room in c["rooms"]:rows.append({"label":room.name,"assets":sum(x.room_id==room.id for x in assets),"incidents":sum(x.room_id==room.id for x in incidents)})
        metrics.append(metric(len(c["rooms"]),"Locations"));breakdowns["locations"]=rows
    if report=="executive":metrics += [metric(sum(x.lifecycle_status in {"open","acknowledged"} for x in alerts),"Active Alerts","/alerts"),metric(len(procurements),"Procurement Records","/procurement"),metric(sum(x.status=="active" for x in vendors),"Active Vendors","/vendors"),metric(sum(x.status=="published" for x in knowledge),"Published Knowledge","/knowledge"),metric(len(services),"Technology Services","/incidents/services")]
    if not trends:insufficient.append("No historical trend is required for this report.")
    return {"report":report,"period":{"start":start,"end":end},"generated_at":datetime.now(timezone.utc),"metrics":metrics,"breakdowns":breakdowns,"trends":trends,"drilldowns":drilldowns,"insufficient_data":insufficient,"source":"Live HIOP organization data"}

@router.get("/{report}")
def report(report:str,period:str="30d",start:datetime|None=None,end:datetime|None=None,department_id:str|None=None,location_id:str|None=None,service_id:str|None=None,device_type:str|None=None,status:str|None=None,vendor_id:str|None=None,db:Session=Depends(get_db),_=Depends(reader),org=Depends(organization_context)):
    if report not in REPORTS:raise HTTPException(404,"Unsupported report")
    start_at,end_at=bounds(period,start,end);return build(report,db,org,start_at,end_at,locals())

@router.get("/{report}/export.csv")
def export_csv(report:str,period:str="30d",start:datetime|None=None,end:datetime|None=None,department_id:str|None=None,location_id:str|None=None,service_id:str|None=None,device_type:str|None=None,status:str|None=None,vendor_id:str|None=None,db:Session=Depends(get_db),_=Depends(reader),org=Depends(organization_context)):
    if report not in REPORTS:raise HTTPException(404,"Unsupported report")
    start_at,end_at=bounds(period,start,end);payload=build(report,db,org,start_at,end_at,locals());stream=io.StringIO();writer=csv.writer(stream);writer.writerow(["Report",report]);writer.writerow(["Period",start_at.isoformat(),end_at.isoformat()]);writer.writerow([]);writer.writerow(["Metric","Value","Quality"])
    for row in payload["metrics"]:writer.writerow([row["label"],row["value"],row["quality"]])
    return StreamingResponse(iter([stream.getvalue()]),media_type="text/csv",headers={"Content-Disposition":f'attachment; filename="hiop-{report}-{date.today().isoformat()}.csv"'})
