import re
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_db, hash_password, require_roles
from app.models.alert import Alert
from app.models.asset_intelligence import ManagedAsset
from app.models.audit_log import AuditLog
from app.models.device import Device
from app.models.hierarchy import Organization, Property
from app.models.incidents import OperationalIncident
from app.models.user import User
from app.schemas.platform import OrganizationAdminCreate, OrganizationCreate, OrganizationUpdate, PlatformAdminCreate
from app.services.audit_service import create_audit_log

router=APIRouter(prefix="/platform",tags=["Platform Control Center"])
platform=require_roles(["platformadmin"])

def counts(db,org):
    properties=db.query(Property.id).filter(Property.organization_id==org.id).subquery()
    device_ids=db.query(Device.id).filter(Device.property_id.in_(properties)).subquery()
    return {"users":db.query(User).filter(User.organization_id==org.id).count(),"assets":db.query(ManagedAsset).filter(ManagedAsset.organization_id==org.id).count(),"devices":db.query(Device).filter(Device.id.in_(device_ids)).count(),"active_alerts":db.query(Alert).filter(Alert.device_id.in_(device_ids),Alert.lifecycle_status.in_(("open","acknowledged"))).count(),"open_incidents":db.query(OperationalIncident).filter(OperationalIncident.organization_id==org.id,OperationalIncident.status.notin_(("resolved","closed"))).count()}
def present(db,row):return {"id":row.id,"name":row.name,"code":row.code,"status":row.status,"contact_email":row.contact_email,"contact_phone":row.contact_phone,"notes":row.notes,"administrator_id":row.administrator_id,"hiop_version":row.hiop_version,"created_at":row.created_at,"updated_at":row.updated_at,"last_activity_at":row.last_activity_at,**counts(db,row)}

@router.get("/organizations")
def organizations(db:Session=Depends(get_db),_:User=Depends(platform)):return [present(db,x) for x in db.query(Organization).order_by(Organization.name)]
@router.get("/organizations/{organization_id}")
def organization(organization_id:UUID,db:Session=Depends(get_db),_:User=Depends(platform)):
    row=db.get(Organization,organization_id)
    if not row:raise HTTPException(404,"Organization not found")
    return present(db,row)
@router.post("/organizations",status_code=201)
def create_organization(payload:OrganizationCreate,db:Session=Depends(get_db),actor:User=Depends(platform)):
    base=re.sub(r"[^a-z0-9]+","-",(payload.code or payload.name).lower()).strip("-")[:32] or "organization";code=base;suffix=2
    while db.query(Organization).filter(func.lower(Organization.code)==code.lower()).first():code=f"{base}-{suffix}";suffix+=1
    row=Organization(name=payload.name.strip(),code=code,status="active",contact_email=str(payload.contact_email) if payload.contact_email else None,contact_phone=payload.contact_phone,notes=payload.notes,created_by=actor.id,hiop_version=settings.app_version,last_activity_at=datetime.now(timezone.utc));db.add(row);db.flush();db.add(Property(name=payload.name.strip(),code=code,organization_id=row.id,timezone="UTC",operational_status="active"));create_audit_log(db,actor.username,"ORGANIZATION_CREATED","Organization",str(row.id),f"Created organization {row.name}");db.commit();db.refresh(row);return present(db,row)
@router.patch("/organizations/{organization_id}")
def update_organization(organization_id:UUID,payload:OrganizationUpdate,db:Session=Depends(get_db),actor:User=Depends(platform)):
    row=db.get(Organization,organization_id)
    if not row:raise HTTPException(404,"Organization not found")
    for key,value in payload.model_dump(exclude_unset=True).items():setattr(row,key,str(value) if key=="contact_email" and value else value)
    row.last_activity_at=datetime.now(timezone.utc);create_audit_log(db,actor.username,"ORGANIZATION_UPDATED","Organization",str(row.id),f"Updated organization {row.name}");db.commit();return present(db,row)
@router.post("/organizations/{organization_id}/suspend")
def suspend(organization_id:UUID,db:Session=Depends(get_db),actor:User=Depends(platform)):return set_status(db,actor,organization_id,"suspended")
@router.post("/organizations/{organization_id}/activate")
def activate(organization_id:UUID,db:Session=Depends(get_db),actor:User=Depends(platform)):return set_status(db,actor,organization_id,"active")
def set_status(db,actor,organization_id,status):
    row=db.get(Organization,organization_id)
    if not row:raise HTTPException(404,"Organization not found")
    row.status=status;row.last_activity_at=datetime.now(timezone.utc);create_audit_log(db,actor.username,f"ORGANIZATION_{status.upper()}","Organization",str(row.id),f"Set {row.name} to {status}");db.commit();return present(db,row)
@router.post("/organizations/{organization_id}/administrator",status_code=201)
def provision_admin(organization_id:UUID,payload:OrganizationAdminCreate,db:Session=Depends(get_db),actor:User=Depends(platform)):
    row=db.get(Organization,organization_id)
    if not row:raise HTTPException(404,"Organization not found")
    if db.query(User).filter((func.lower(User.email)==str(payload.email).lower())|(func.lower(User.username)==payload.username.lower())).first():raise HTTPException(409,"Username or email already exists")
    user=User(username=payload.username,email=str(payload.email).lower(),hashed_password=hash_password(payload.password),role="admin",is_active=True,organization_id=row.id);db.add(user);db.flush();row.administrator_id=user.id;create_audit_log(db,actor.username,"ORGANIZATION_ADMIN_ASSIGNED","Organization",str(row.id),f"Assigned organization administrator {user.username}");db.commit();return {"id":user.id,"username":user.username,"email":user.email,"role":user.role,"organization_id":str(row.id)}
@router.get("/users")
def platform_users(db:Session=Depends(get_db),_:User=Depends(platform)):return [{"id":x.id,"username":x.username,"email":x.email,"role":x.role,"is_active":x.is_active,"created_at":x.created_at,"last_login_at":x.last_login_at} for x in db.query(User).filter(User.role=="platformadmin").order_by(User.created_at)]
@router.post("/users",status_code=201)
def create_platform_user(payload:PlatformAdminCreate,db:Session=Depends(get_db),actor:User=Depends(platform)):
    if db.query(User).filter((func.lower(User.email)==str(payload.email).lower())|(func.lower(User.username)==payload.username.lower())).first():raise HTTPException(409,"Username or email already exists")
    user=User(username=payload.username.strip(),email=str(payload.email).lower(),hashed_password=hash_password(payload.password),role="platformadmin",is_active=True,organization_id=None);db.add(user);db.flush();create_audit_log(db,actor.username,"PLATFORM_ADMIN_CREATED","User",str(user.id),f"Created platform administrator {user.username}");db.commit();db.refresh(user);return {"id":user.id,"username":user.username,"email":user.email,"role":user.role,"is_active":user.is_active,"created_at":user.created_at,"last_login_at":user.last_login_at}
@router.post("/users/{user_id}/status")
def set_platform_user_status(user_id:str,active:bool,db:Session=Depends(get_db),actor:User=Depends(platform)):
    user=db.get(User,user_id)
    if not user or user.role!="platformadmin":raise HTTPException(404,"Platform administrator not found")
    if user.id==actor.id and not active:raise HTTPException(400,"You cannot deactivate your own platform account")
    if not active and user.is_active and db.query(User).filter(User.role=="platformadmin",User.is_active.is_(True)).count()<=1:raise HTTPException(400,"At least one active platform administrator is required")
    user.is_active=active;create_audit_log(db,actor.username,"PLATFORM_ADMIN_ACTIVATED" if active else "PLATFORM_ADMIN_DEACTIVATED","User",str(user.id),f"{'Activated' if active else 'Deactivated'} platform administrator {user.username}");db.commit();return {"id":user.id,"username":user.username,"email":user.email,"role":user.role,"is_active":user.is_active,"created_at":user.created_at,"last_login_at":user.last_login_at}
@router.get("/audit")
def platform_audit(db:Session=Depends(get_db),_:User=Depends(platform)):
    rows=db.query(AuditLog).filter(AuditLog.action.like("%ORGANIZATION%")|AuditLog.action.like("%PLATFORM%") ).order_by(AuditLog.created_at.desc()).limit(200).all()
    return [{"id":x.id,"actor":x.actor,"action":x.action,"entity_type":x.entity_type,"entity_id":x.entity_id,"description":x.description,"created_at":x.created_at} for x in rows]
@router.get("/health")
def platform_health(db:Session=Depends(get_db),_:User=Depends(platform)):
    db.execute(text("SELECT 1"));return {"status":"healthy","api":"healthy","database":"healthy","scheduler":"healthy" if settings.scheduler_enabled else "disabled","discovery_engine":"available","monitoring_engine":"available","alert_engine":"available","version":settings.app_version}
@router.get("/summary")
def summary(db:Session=Depends(get_db),_:User=Depends(platform)):
    rows=db.query(Organization).all();details=[present(db,x) for x in rows];return {"organizations":len(rows),"active":sum(x.status=="active" for x in rows),"suspended":sum(x.status=="suspended" for x in rows),"users":sum(x["users"] for x in details),"assets":sum(x["assets"] for x in details),"devices":sum(x["devices"] for x in details),"active_alerts":sum(x["active_alerts"] for x in details),"open_incidents":sum(x["open_incidents"] for x in details)}
