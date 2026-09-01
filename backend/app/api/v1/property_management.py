from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.core.tenant import allowed_property_ids, organization_context, property_context
from app.models.alert import Alert
from app.models.asset_intelligence import ManagedAsset
from app.models.change_management import ChangeRequest
from app.models.device import Device
from app.models.hierarchy import Organization, Property
from app.models.hospitality_operations import HospitalityTechnologyService
from app.models.incidents import OperationalIncident
from app.models.network_scan import NetworkScan
from app.models.problem_management import Problem
from app.models.property_access import UserPropertyAccess
from app.models.user import User
from app.services.audit_service import create_audit_log
from app.services.billing_service import enforce_limit

router=APIRouter(prefix="/property-management",tags=["V4J Multi-Property"])
reader=require_roles(["platformadmin","admin","technician","viewer"]);manager=require_roles(["platformadmin","admin"])

class PropertyWrite(BaseModel):
    name:str=Field(min_length=2,max_length=120);code:str|None=Field(default=None,max_length=40);address:str|None=None;city:str|None=None;state:str|None=None;country:str|None=None;timezone:str="UTC";contact_email:EmailStr|None=None;contact_phone:str|None=None;description:str|None=None
class PropertyPatch(BaseModel):
    name:str|None=Field(default=None,min_length=2,max_length=120);code:str|None=None;address:str|None=None;city:str|None=None;state:str|None=None;country:str|None=None;timezone:str|None=None;contact_email:EmailStr|None=None;contact_phone:str|None=None;description:str|None=None
class AccessWrite(BaseModel):user_id:str;access_level:str="property_viewer";is_default:bool=False

def counts(db,prop):
    device_ids=db.query(Device.id).filter(Device.property_id==prop.id).subquery()
    scans=db.query(NetworkScan).filter(NetworkScan.device_id.in_(device_ids)).order_by(NetworkScan.scanned_at.desc()).all();latest={}
    for scan in scans:latest.setdefault(scan.device_id,scan)
    total=len(latest);online=sum(x.status.lower()=="online" for x in latest.values());availability=round(online*100/total,2) if total else None
    critical=db.query(Alert).filter(Alert.device_id.in_(device_ids),Alert.severity=="critical",Alert.lifecycle_status.in_(("open","acknowledged"))).count()
    open_incidents=db.query(OperationalIncident).filter(OperationalIncident.property_id==prop.id,OperationalIncident.status.notin_(("resolved","closed"))).count()
    return {"assets":db.query(ManagedAsset).filter(ManagedAsset.property_id==prop.id).count(),"devices":db.query(Device).filter(Device.property_id==prop.id).count(),"services":db.query(HospitalityTechnologyService).filter(HospitalityTechnologyService.property_id==prop.id).count(),"open_incidents":open_incidents,"open_problems":db.query(Problem).filter(Problem.property_id==prop.id,Problem.status.notin_(("resolved","closed"))).count(),"upcoming_changes":db.query(ChangeRequest).filter(ChangeRequest.property_id==prop.id,ChangeRequest.status.in_(("approved","scheduled","in_progress"))).count(),"critical_alerts":critical,"availability":availability,"health":"attention_required" if critical or open_incidents else ("healthy" if total else "unknown")}
def present(db,row,include_counts=False):
    result={"id":row.id,"organization_id":row.organization_id,"name":row.name,"code":row.code,"status":"active" if row.is_active else "inactive","address":row.address,"city":row.city,"state":row.state,"country":row.country,"timezone":row.timezone,"contact_email":row.email,"contact_phone":row.phone,"description":row.description,"created_at":row.created_at,"updated_at":row.updated_at}
    if include_counts:result.update(counts(db,row))
    return result
def require_prop(db,pid,org):
    row=db.query(Property).filter(Property.id==pid,Property.organization_id==org).first()
    if not row:raise HTTPException(404,"Property not found")
    return row

@router.get("")
def list_properties(db:Session=Depends(get_db),user:User=Depends(reader),org=Depends(organization_context)):
    allowed=allowed_property_ids(db,user,org);return [present(db,x,True) for x in db.query(Property).filter(Property.organization_id==org,Property.id.in_(allowed)).order_by(Property.name)]
@router.post("",status_code=201)
def create_property(payload:PropertyWrite,db:Session=Depends(get_db),actor:User=Depends(manager),org=Depends(organization_context)):
    enforce_limit(db,org,"properties")
    if db.query(Property).filter(Property.organization_id==org,Property.code==payload.code).first():raise HTTPException(409,"Property code already exists")
    row=Property(name=payload.name.strip(),code=payload.code,address=payload.address,city=payload.city,state=payload.state,country=payload.country,timezone=payload.timezone,email=str(payload.contact_email) if payload.contact_email else None,phone=payload.contact_phone,description=payload.description,organization_id=org,is_active=True,operational_status="active");db.add(row);db.flush();create_audit_log(db,actor.username,"PROPERTY_CREATED","Property",str(row.id),f"Created property {row.name}");db.commit();db.refresh(row);return present(db,row,True)
@router.get("/context")
def current_context(db:Session=Depends(get_db),user:User=Depends(reader),org=Depends(organization_context),active=Depends(property_context)):
    organization=db.get(Organization,org);allowed=allowed_property_ids(db,user,org);properties=db.query(Property).filter(Property.id.in_(allowed)).order_by(Property.name).all()
    if active is None and user.role not in {"admin","platformadmin"}:
        default=db.query(UserPropertyAccess.property_id).filter(UserPropertyAccess.user_id==user.id,UserPropertyAccess.enabled.is_(True),UserPropertyAccess.is_default.is_(True)).scalar();active=default or (properties[0].id if properties else None)
    return {"organization":{"id":org,"name":organization.name},"active_property_id":active,"organization_wide":active is None,"properties":[present(db,x) for x in properties]}
@router.get("/comparison")
def comparison(db:Session=Depends(get_db),user:User=Depends(reader),org=Depends(organization_context)):
    allowed=allowed_property_ids(db,user,org);return {"organization_id":org,"properties":[present(db,x,True) for x in db.query(Property).filter(Property.organization_id==org,Property.id.in_(allowed)).order_by(Property.name)]}
@router.get("/{property_id}")
def get_property(property_id:UUID,db:Session=Depends(get_db),user:User=Depends(reader),org=Depends(organization_context)):
    if property_id not in allowed_property_ids(db,user,org):raise HTTPException(403,"Property is outside your permitted scope")
    return present(db,require_prop(db,property_id,org),True)
@router.patch("/{property_id}")
def update_property(property_id:UUID,payload:PropertyPatch,db:Session=Depends(get_db),actor:User=Depends(manager),org=Depends(organization_context)):
    row=require_prop(db,property_id,org)
    mapping={"contact_email":"email","contact_phone":"phone"}
    for key,value in payload.model_dump(exclude_unset=True).items():setattr(row,mapping.get(key,key),str(value) if key=="contact_email" and value else value)
    create_audit_log(db,actor.username,"PROPERTY_UPDATED","Property",str(row.id),f"Updated property {row.name}");db.commit();db.refresh(row);return present(db,row,True)
@router.post("/{property_id}/access")
def assign_access(property_id:UUID,payload:AccessWrite,db:Session=Depends(get_db),actor:User=Depends(manager),org=Depends(organization_context)):
    require_prop(db,property_id,org);user=db.query(User).filter(User.id==payload.user_id,User.organization_id==org).first()
    if not user:raise HTTPException(422,"User does not belong to this organization")
    row=db.query(UserPropertyAccess).filter_by(user_id=user.id,property_id=property_id).first() or UserPropertyAccess(user_id=user.id,property_id=property_id,granted_by=actor.id);row.enabled=True;row.access_level=payload.access_level;row.is_default=payload.is_default
    if payload.is_default:db.query(UserPropertyAccess).filter(UserPropertyAccess.user_id==user.id,UserPropertyAccess.property_id!=property_id).update({"is_default":False})
    db.add(row);create_audit_log(db,actor.username,"PROPERTY_ACCESS_ASSIGNED","Property",str(property_id),f"Granted {user.username} property access");db.commit();return {"user_id":user.id,"property_id":property_id,"access_level":row.access_level,"is_default":row.is_default}
@router.post("/{property_id}/{action}")
def status(property_id:UUID,action:str,db:Session=Depends(get_db),actor:User=Depends(manager),org=Depends(organization_context)):
    if action not in {"activate","deactivate"}:raise HTTPException(404,"Unsupported property action")
    row=require_prop(db,property_id,org);row.is_active=action=="activate";row.operational_status="active" if row.is_active else "inactive";create_audit_log(db,actor.username,f"PROPERTY_{action.upper()}","Property",str(row.id),f"{action.title()}d property {row.name}");db.commit();return present(db,row,True)
@router.delete("/{property_id}/access/{user_id}",status_code=204)
def remove_access(property_id:UUID,user_id:str,db:Session=Depends(get_db),actor:User=Depends(manager),org=Depends(organization_context)):
    require_prop(db,property_id,org);row=db.query(UserPropertyAccess).filter_by(user_id=user_id,property_id=property_id).first()
    if not row:raise HTTPException(404,"Property access not found")
    row.enabled=False;create_audit_log(db,actor.username,"PROPERTY_ACCESS_REMOVED","Property",str(property_id),f"Removed property access for {user_id}");db.commit()
