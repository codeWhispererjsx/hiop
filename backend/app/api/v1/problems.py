from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.core.tenant import organization_context, property_context
from app.models.asset_intelligence import ManagedAsset
from app.models.asset_management import Vendor, VendorContact
from app.models.device import Device
from app.models.hierarchy import Building, Department, Floor, Property, Room
from app.models.hospitality_operations import HospitalityTechnologyService
from app.models.incidents import IncidentImpactAssessment, OperationalIncident
from app.models.problem_management import Problem, ProblemRelationship, ProblemTimelineEvent
from app.models.procurement import AssetProcurement
from app.models.user import User
from app.services.audit_service import create_audit_log

router=APIRouter(prefix="/problems",tags=["Problem Management"])
reader=require_roles(["platformadmin","admin","technician","viewer"]); operator=require_roles(["admin"]); note_writer=require_roles(["admin","technician"])
STATUSES={"open","investigating","known_error","resolved","closed"}; PRIORITIES={"low","medium","high","critical"}; CATEGORIES={"network","hardware","software","pos","pms","wifi","printer","security_system","telephony","other"}

class ProblemWrite(BaseModel):
    title:str=Field(min_length=3,max_length=240); description:str=Field("",max_length=10000); problem_statement:str=Field(min_length=3,max_length=10000)
    priority:str="medium"; category:str="other"; assigned_team:str|None=None; assigned_technician_id:str|None=None; owner_id:str|None=None
    property_id:UUID|None=None; department_id:UUID|None=None; location_type:str|None=None; location_id:UUID|None=None; service_id:UUID|None=None
    vendor_id:UUID|None=None; procurement_id:UUID|None=None; incident_id:UUID|None=None; asset_id:UUID|None=None; device_id:UUID|None=None; source:str="manual"
    @field_validator("priority")
    @classmethod
    def priority_valid(cls,v):
        if v not in PRIORITIES: raise ValueError("Unsupported priority")
        return v
    @field_validator("category")
    @classmethod
    def category_valid(cls,v):
        if v not in CATEGORIES: raise ValueError("Unsupported category")
        return v

class ProblemPatch(BaseModel):
    title:str|None=Field(None,min_length=3,max_length=240); description:str|None=Field(None,max_length=10000); problem_statement:str|None=Field(None,max_length=10000)
    priority:str|None=None; assigned_team:str|None=None; assigned_technician_id:str|None=None; owner_id:str|None=None; root_cause:str|None=Field(None,max_length=20000); workaround:str|None=Field(None,max_length=20000); resolution:str|None=Field(None,max_length=20000); follow_up_notes:str|None=Field(None,max_length=20000)

class TransitionWrite(BaseModel):
    target_status:str; reason:str|None=Field(None,max_length=5000); resolution:str|None=Field(None,max_length=20000)

class NoteWrite(BaseModel): note:str=Field(min_length=2,max_length=10000)
class LinkWrite(BaseModel): target_type:Literal["incident","asset","device","service","vendor","procurement"]; target_id:UUID

def require_problem(db,id,org):
    row=db.query(Problem).filter_by(id=id,organization_id=org).first()
    if not row: raise HTTPException(404,"Problem not found")
    return row
def event(db,row,actor,kind,summary): db.add(ProblemTimelineEvent(problem_id=row.id,organization_id=row.organization_id,event_type=kind,summary=summary,actor_id=actor.id,actor_name=actor.username))
def audit(db,row,actor,action,detail): create_audit_log(db,actor.username,action,"Problem",str(row.id),f"Organization {row.organization_id}: {detail}")

TARGETS={"incident":OperationalIncident,"asset":ManagedAsset,"device":Device,"service":HospitalityTechnologyService,"vendor":Vendor,"procurement":AssetProcurement}
def target(db,kind,id,org):
    model=TARGETS[kind]; query=db.query(model).filter(model.id==id)
    if hasattr(model,"organization_id"): query=query.filter(model.organization_id==org)
    elif model is Device: query=query.join(Property,Device.property_id==Property.id).filter(Property.organization_id==org)
    row=query.first()
    if not row: raise HTTPException(422,f"{kind.title()} does not belong to this organization")
    return row

def link(db,row,kind,id,actor):
    target(db,kind,id,row.organization_id)
    exists=db.query(ProblemRelationship).filter_by(problem_id=row.id,target_type=kind,target_id=id,relationship_type="related").first()
    if not exists: db.add(ProblemRelationship(problem_id=row.id,target_type=kind,target_id=id,relationship_type="related",created_by=actor.id)); event(db,row,actor,f"{kind}_linked",f"Linked {kind} {id}"); audit(db,row,actor,f"PROBLEM_{kind.upper()}_LINKED",f"Linked {kind} {id}")

def rels(db,row,kind): return db.query(ProblemRelationship).filter_by(problem_id=row.id,target_type=kind).all()
def present(db,row,detail=False):
    relationships={kind:rels(db,row,kind) for kind in TARGETS}
    incidents=[target(db,"incident",x.target_id,row.organization_id) for x in relationships["incident"]]
    assets=[target(db,"asset",x.target_id,row.organization_id) for x in relationships["asset"]]
    service=db.query(HospitalityTechnologyService).filter_by(id=row.technology_service_id,organization_id=row.organization_id).first() if row.technology_service_id else None
    vendor=db.query(Vendor).filter_by(id=row.vendor_id,organization_id=row.organization_id).first() if row.vendor_id else None
    contact=db.query(VendorContact).filter_by(vendor_id=row.vendor_id,primary=True).first() if vendor else None
    department=db.query(Department).filter_by(id=row.department_id,organization_id=row.organization_id).first() if row.department_id else None
    location=None
    if row.location_type in {"building","floor","room"} and row.location_id: location=db.query({"building":Building,"floor":Floor,"room":Room}[row.location_type]).filter_by(id=row.location_id,organization_id=row.organization_id).first()
    impact_rows=db.query(IncidentImpactAssessment).filter(IncidentImpactAssessment.incident_id.in_([x.id for x in incidents])).all() if incidents else []
    result={"id":row.id,"problem_number":row.problem_number,"title":row.title,"description":row.description,"problem_statement":row.problem_statement,"status":row.status,"priority":row.priority,"category":row.impact,"assigned_team":row.assigned_team,"assigned_technician_id":row.assigned_technician_id,"owner_id":row.owner_id,"root_cause":row.root_cause,"workaround":row.workaround,"resolution":row.resolution,"follow_up_notes":row.follow_up_notes,"service_id":row.technology_service_id,"service_name":service.name if service else None,"department":department.name if department else None,"location":location.name if location else None,"vendor":{"id":vendor.id,"name":vendor.legal_name,"support_contact":contact.name if contact else None} if vendor else None,"procurement_id":row.procurement_id,"related_counts":{k:len(v) for k,v in relationships.items()},"impact":{"confirmed_affected":0,"potentially_affected":sum(x.affected_guest_rooms or 0 for x in impact_rows),"confidence_score":max(x.confidence_score for x in impact_rows),"source":"existing_incident_impact"} if impact_rows else None,"resolved_at":row.resolved_at,"closed_at":row.closed_at,"created_at":row.created_at,"updated_at":row.updated_at}
    if detail:
        result["incidents"]=[{"id":x.id,"incident_number":x.incident_number,"title":x.title,"status":x.status} for x in incidents]
        result["assets"]=[{"id":x.id,"asset_number":x.asset_number,"name":x.name} for x in assets]
        result["timeline"]=[{"id":x.id,"type":x.event_type,"summary":x.summary,"author":x.actor_name,"timestamp":x.created_at} for x in db.query(ProblemTimelineEvent).filter_by(problem_id=row.id,organization_id=row.organization_id).order_by(ProblemTimelineEvent.created_at).all()]
    return result

@router.get("/summary")
def summary(db:Session=Depends(get_db),_=Depends(reader),organization_id=Depends(organization_context),property_id=Depends(property_context)):
    query=db.query(Problem).filter_by(organization_id=organization_id);rows=(query.filter_by(property_id=property_id) if property_id else query).all(); counts={x:sum(r.status==x for r in rows) for x in STATUSES}
    return {"total":len(rows),**counts,"critical":sum(r.priority=="critical" and r.status not in {"resolved","closed"} for r in rows),"recurring":sum(db.query(ProblemRelationship).filter_by(problem_id=r.id,target_type="incident").count()>1 for r in rows)}

@router.get("")
def list_problems(search:str|None=None,status:str|None=None,priority:str|None=None,category:str|None=None,service_id:UUID|None=None,vendor_id:UUID|None=None,db:Session=Depends(get_db),_=Depends(reader),organization_id=Depends(organization_context),property_id=Depends(property_context)):
    q=db.query(Problem).filter_by(organization_id=organization_id)
    if property_id:q=q.filter_by(property_id=property_id)
    if search:
        term=f"%{search}%"
        related_ids=db.query(ProblemRelationship.problem_id).filter(or_(
            ProblemRelationship.target_type=="asset", ProblemRelationship.target_type=="device"
        ), ProblemRelationship.target_id.in_(
            db.query(ManagedAsset.id).filter(or_(ManagedAsset.name.ilike(term),ManagedAsset.asset_number.ilike(term),ManagedAsset.asset_tag.ilike(term)))
        )).union(db.query(ProblemRelationship.problem_id).filter(ProblemRelationship.target_type=="device",ProblemRelationship.target_id.in_(db.query(Device.id).filter(or_(Device.hostname.ilike(term),Device.ip_address.ilike(term))))))
        q=q.outerjoin(HospitalityTechnologyService,Problem.technology_service_id==HospitalityTechnologyService.id).outerjoin(Department,Problem.department_id==Department.id).outerjoin(Vendor,Problem.vendor_id==Vendor.id).filter(or_(Problem.problem_number.ilike(term),Problem.title.ilike(term),Problem.description.ilike(term),Problem.problem_statement.ilike(term),HospitalityTechnologyService.name.ilike(term),Department.name.ilike(term),Vendor.legal_name.ilike(term),Problem.id.in_(related_ids)))
    if status:q=q.filter_by(status=status)
    if priority:q=q.filter_by(priority=priority)
    if category:q=q.filter_by(impact=category)
    if service_id:q=q.filter_by(technology_service_id=service_id)
    if vendor_id:q=q.filter_by(vendor_id=vendor_id)
    return [present(db,x) for x in q.order_by(Problem.created_at.desc()).all()]

@router.post("",status_code=201)
def create_problem(payload:ProblemWrite,db:Session=Depends(get_db),actor=Depends(operator),organization_id=Depends(organization_context)):
    if payload.property_id and not db.query(Property).filter_by(id=payload.property_id,organization_id=organization_id).first(): raise HTTPException(422,"Property does not belong to this organization")
    if payload.department_id and not db.query(Department).filter_by(id=payload.department_id,organization_id=organization_id).first(): raise HTTPException(422,"Department does not belong to this organization")
    if payload.location_id:
        if payload.location_type not in {"building","floor","room"}: raise HTTPException(422,"Unsupported location type")
        if not db.query({"building":Building,"floor":Floor,"room":Room}[payload.location_type]).filter_by(id=payload.location_id,organization_id=organization_id).first(): raise HTTPException(422,"Location does not belong to this organization")
    for user_id in (payload.assigned_technician_id,payload.owner_id):
        if user_id and not db.query(User).filter_by(id=user_id,organization_id=organization_id).first(): raise HTTPException(422,"Assigned user does not belong to this organization")
    number=db.execute(text("SELECT nextval('problem_number_seq')")).scalar_one()
    row=Problem(problem_number=f"PRB-{number:05d}",title=payload.title,description=payload.description,problem_statement=payload.problem_statement,status="open",priority=payload.priority,severity=payload.priority,impact=payload.category,source=payload.source,organization_id=organization_id,property_id=payload.property_id,department_id=payload.department_id,location_type=payload.location_type,location_id=payload.location_id,technology_service_id=payload.service_id,vendor_id=payload.vendor_id,procurement_id=payload.procurement_id,assigned_team=payload.assigned_team,assigned_technician_id=payload.assigned_technician_id,owner_id=payload.owner_id,created_by=actor.id)
    db.add(row);db.flush()
    for kind,id in (("incident",payload.incident_id),("asset",payload.asset_id),("device",payload.device_id),("service",payload.service_id),("vendor",payload.vendor_id),("procurement",payload.procurement_id)):
        if id: link(db,row,kind,id,actor)
    event(db,row,actor,"problem_created","Problem created");audit(db,row,actor,"PROBLEM_CREATED",f"Created {row.problem_number}");db.commit();db.refresh(row);return present(db,row,True)

@router.get("/{problem_id}")
def get_problem(problem_id:UUID,db:Session=Depends(get_db),_=Depends(reader),organization_id=Depends(organization_context)): return present(db,require_problem(db,problem_id,organization_id),True)

@router.patch("/{problem_id}")
def update_problem(problem_id:UUID,payload:ProblemPatch,db:Session=Depends(get_db),actor=Depends(operator),organization_id=Depends(organization_context)):
    row=require_problem(db,problem_id,organization_id); changes=payload.model_dump(exclude_unset=True)
    if changes.get("assigned_technician_id") and not db.query(User).filter_by(id=changes["assigned_technician_id"],organization_id=organization_id).first(): raise HTTPException(422,"Assigned user does not belong to this organization")
    for key,value in changes.items(): setattr(row,key,value)
    event(db,row,actor,"problem_updated","Updated: "+", ".join(changes));audit(db,row,actor,"PROBLEM_UPDATED","Updated problem fields")
    for field,action in (("root_cause","PROBLEM_ROOT_CAUSE_UPDATED"),("workaround","PROBLEM_WORKAROUND_UPDATED"),("priority","PROBLEM_PRIORITY_CHANGED")):
        if field in changes: audit(db,row,actor,action,f"Updated {field.replace('_',' ')}")
    db.commit();db.refresh(row);return present(db,row,True)

@router.post("/{problem_id}/transition")
def transition(problem_id:UUID,payload:TransitionWrite,db:Session=Depends(get_db),actor=Depends(operator),organization_id=Depends(organization_context)):
    row=require_problem(db,problem_id,organization_id); target_status=payload.target_status
    allowed={"open":{"investigating"},"investigating":{"known_error","resolved"},"known_error":{"investigating","resolved"},"resolved":{"closed","investigating"},"closed":{"investigating"}}
    if target_status not in STATUSES or target_status not in allowed.get(row.status,set()): raise HTTPException(422,f"Cannot transition from {row.status} to {target_status}")
    if target_status=="known_error" and not row.workaround: raise HTTPException(422,"Document a workaround before marking a known error")
    if target_status=="resolved":
        row.resolution=payload.resolution or row.resolution
        if not row.resolution: raise HTTPException(422,"Resolution is required")
        row.resolved_at=datetime.now(timezone.utc)
    if target_status=="closed":
        if not row.resolution: raise HTTPException(422,"Resolved documentation is required before closure")
        row.closed_at=datetime.now(timezone.utc)
    if target_status=="investigating" and row.status in {"resolved","closed"}: row.resolved_at=None;row.closed_at=None
    previous=row.status;row.status=target_status;event(db,row,actor,"status_changed",f"{previous} → {target_status}. {payload.reason or ''}".strip());audit(db,row,actor,"PROBLEM_STATUS_CHANGED",f"Changed {previous} to {target_status}");db.commit();db.refresh(row);return present(db,row,True)

@router.post("/{problem_id}/relationships",status_code=201)
def add_relationship(problem_id:UUID,payload:LinkWrite,db:Session=Depends(get_db),actor=Depends(operator),organization_id=Depends(organization_context)):
    row=require_problem(db,problem_id,organization_id);link(db,row,payload.target_type,payload.target_id,actor);db.commit();return present(db,row,True)

@router.delete("/{problem_id}/relationships/{relationship_id}",status_code=204)
def remove_relationship(problem_id:UUID,relationship_id:UUID,db:Session=Depends(get_db),actor=Depends(operator),organization_id=Depends(organization_context)):
    row=require_problem(db,problem_id,organization_id);rel=db.query(ProblemRelationship).filter_by(id=relationship_id,problem_id=row.id).first()
    if not rel: raise HTTPException(404,"Relationship not found")
    event(db,row,actor,f"{rel.target_type}_unlinked",f"Unlinked {rel.target_type} {rel.target_id}");audit(db,row,actor,f"PROBLEM_{rel.target_type.upper()}_UNLINKED","Removed relationship");db.delete(rel);db.commit();return Response(status_code=204)

@router.post("/{problem_id}/notes",status_code=201)
def add_note(problem_id:UUID,payload:NoteWrite,db:Session=Depends(get_db),actor=Depends(note_writer),organization_id=Depends(organization_context)):
    row=require_problem(db,problem_id,organization_id);event(db,row,actor,"note",payload.note);audit(db,row,actor,"PROBLEM_NOTE_ADDED","Added problem note");db.commit();return present(db,row,True)

@router.get("/incident-links/{incident_id}")
def incident_problems(incident_id:UUID,db:Session=Depends(get_db),_=Depends(reader),organization_id=Depends(organization_context)):
    target(db,"incident",incident_id,organization_id); ids=db.query(ProblemRelationship.problem_id).filter_by(target_type="incident",target_id=incident_id)
    return [present(db,x) for x in db.query(Problem).filter(Problem.organization_id==organization_id,Problem.id.in_(ids)).all()]

@router.get("/asset-links/{asset_id}")
def asset_problems(asset_id:UUID,db:Session=Depends(get_db),_=Depends(reader),organization_id=Depends(organization_context)):
    target(db,"asset",asset_id,organization_id); ids=db.query(ProblemRelationship.problem_id).filter_by(target_type="asset",target_id=asset_id)
    return [present(db,x) for x in db.query(Problem).filter(Problem.organization_id==organization_id,Problem.id.in_(ids)).all()]
