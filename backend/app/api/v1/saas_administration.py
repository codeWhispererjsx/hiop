import secrets
from datetime import datetime, timedelta, timezone

import dns.resolver
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.models.audit_log import AuditLog
from app.models.hierarchy import Organization, Property
from app.models.property_access import UserPropertyAccess
from app.models.saas_security import DataLifecycleRequest, SecurityAccessEvent
from app.models.user import User
from app.services.audit_service import create_audit_log

router=APIRouter(prefix="/saas-admin",tags=["SaaS administration"])
platform=require_roles(["platformadmin"])
security_reader=require_roles(["platformadmin","admin"])


class OffboardingRequest(BaseModel):
    reason:str=Field(min_length=10,max_length=1000)
    retention_days:int=Field(default=30,ge=7,le=3650)
    legal_hold:bool=False


class Confirmation(BaseModel):
    confirmation:str


class DomainRequest(BaseModel):
    domain:str=Field(min_length=4,max_length=255,pattern=r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$")


@router.get("/security/access-events")
def access_events(limit:int=100,denied_only:bool=False,db:Session=Depends(get_db),actor:User=Depends(security_reader)):
    limit=max(1,min(limit,500));query=db.query(SecurityAccessEvent)
    if actor.role!="platformadmin":query=query.filter(SecurityAccessEvent.organization_id==actor.organization_id)
    if denied_only:query=query.filter(SecurityAccessEvent.denied.is_(True))
    rows=query.order_by(SecurityAccessEvent.created_at.desc()).limit(limit).all()
    return {"items":[{"id":str(x.id),"request_id":x.request_id,"actor_user_id":x.actor_user_id,"organization_id":str(x.organization_id) if x.organization_id else None,"property_id":str(x.property_id) if x.property_id else None,"method":x.method,"path":x.path,"status_code":x.status_code,"source_ip":x.source_ip,"denied":x.denied,"duration_ms":x.duration_ms,"created_at":x.created_at} for x in rows],"denied":sum(x.denied for x in rows),"total":len(rows)}


@router.post("/organizations/{organization_id}/offboarding",status_code=201)
def request_offboarding(organization_id:str,payload:OffboardingRequest,db:Session=Depends(get_db),actor:User=Depends(platform)):
    org=db.get(Organization,organization_id)
    if not org:raise HTTPException(404,"Organization not found")
    if db.query(DataLifecycleRequest).filter(DataLifecycleRequest.organization_id==org.id,DataLifecycleRequest.status.in_(["requested","approved","scheduled"])).first():raise HTTPException(409,"An offboarding request is already active")
    now=datetime.now(timezone.utc);execute_after=now+timedelta(days=payload.retention_days)
    row=DataLifecycleRequest(organization_id=org.id,request_type="gdpr_erasure",status="requested",reason=payload.reason,requested_by=actor.id,execute_after=execute_after,legal_hold=payload.legal_hold)
    org.offboarding_status="legal_hold" if payload.legal_hold else "erasure_scheduled";org.legal_hold=payload.legal_hold;org.erasure_requested_at=now;org.erasure_scheduled_for=execute_after;org.retention_until=execute_after
    db.add(row);create_audit_log(db,actor.username,"ORGANIZATION_ERASURE_REQUESTED","Organization",str(org.id),payload.reason,organization_id=org.id,event_category="privacy");db.commit();db.refresh(row);return {"id":str(row.id),"status":row.status,"execute_after":row.execute_after,"legal_hold":row.legal_hold}


@router.post("/offboarding/{request_id}/approve")
def approve_offboarding(request_id:str,db:Session=Depends(get_db),actor:User=Depends(platform)):
    row=db.get(DataLifecycleRequest,request_id)
    if not row or row.status!="requested":raise HTTPException(404,"Pending offboarding request not found")
    if row.requested_by==actor.id:raise HTTPException(409,"A second platform administrator must approve erasure")
    row.status="approved";row.approved_by=actor.id;create_audit_log(db,actor.username,"ORGANIZATION_ERASURE_APPROVED","Organization",str(row.organization_id),"Approved controlled tenant erasure",organization_id=row.organization_id,event_category="privacy");db.commit();return {"status":row.status,"execute_after":row.execute_after}


@router.post("/offboarding/{request_id}/execute")
def execute_offboarding(request_id:str,payload:Confirmation,db:Session=Depends(get_db),actor:User=Depends(platform)):
    row=db.get(DataLifecycleRequest,request_id);now=datetime.now(timezone.utc)
    if not row or row.status!="approved":raise HTTPException(404,"Approved offboarding request not found")
    if row.legal_hold:raise HTTPException(409,"Legal hold prevents erasure")
    if row.execute_after and row.execute_after>now:raise HTTPException(409,"Retention period has not ended")
    if payload.confirmation!=f"ERASE {row.organization_id}":raise HTTPException(400,"Confirmation text does not match")
    org=db.get(Organization,row.organization_id)
    for user in db.query(User).filter(User.organization_id==org.id).all():
        user.email=f"erased-{user.id}@invalid.local";user.username=f"erased-{user.id[:12]}";user.hashed_password="!erased";user.is_active=False;user.department_id=None;user.primary_location_id=None
    db.query(UserPropertyAccess).filter(UserPropertyAccess.user_id.in_([u.id for u in db.query(User).filter(User.organization_id==org.id)])).delete(synchronize_session=False)
    db.query(Property).filter(Property.organization_id==org.id).update({Property.is_active:False,Property.operational_status:"inactive",Property.email:None,Property.phone:None},synchronize_session=False)
    org.name=f"Erased organization {str(org.id)[:8]}";org.contact_email=None;org.contact_phone=None;org.address=None;org.description=None;org.notes=None;org.custom_domain=None;org.custom_domain_status="unconfigured";org.status="inactive";org.offboarding_status="erased";org.administrator_id=None
    row.status="completed";row.completed_at=now;row.verification_summary="Personal/contact data anonymized; operational and audit history retained without active access."
    create_audit_log(db,actor.username,"ORGANIZATION_ERASURE_COMPLETED","Organization",str(org.id),row.verification_summary,organization_id=org.id,event_category="privacy")
    db.commit();return {"status":"completed","organization_id":str(org.id),"verification":row.verification_summary}


@router.post("/offboarding/{request_id}/legal-hold")
def legal_hold(request_id:str,payload:Confirmation,db:Session=Depends(get_db),actor:User=Depends(platform)):
    row=db.get(DataLifecycleRequest,request_id)
    if not row:raise HTTPException(404,"Offboarding request not found")
    enabled=payload.confirmation=="ENABLE LEGAL HOLD";row.legal_hold=enabled;org=db.get(Organization,row.organization_id);org.legal_hold=enabled;org.offboarding_status="legal_hold" if enabled else "erasure_scheduled";create_audit_log(db,actor.username,"LEGAL_HOLD_ENABLED" if enabled else "LEGAL_HOLD_RELEASED","Organization",str(org.id),"Updated legal hold",organization_id=org.id,event_category="privacy");db.commit();return {"legal_hold":enabled}


@router.post("/audit/archive")
def archive_audit(retention_days:int=Query(default=365,ge=30,le=3650),db:Session=Depends(get_db),actor:User=Depends(platform)):
    cutoff=datetime.now(timezone.utc)-timedelta(days=retention_days);now=datetime.now(timezone.utc)
    count=db.query(AuditLog).filter(AuditLog.created_at<cutoff,AuditLog.archived_at.is_(None),AuditLog.legal_hold.is_(False)).update({AuditLog.archived_at:now},synchronize_session=False);create_audit_log(db,actor.username,"AUDIT_ARCHIVED","AuditLog","batch",f"Archived {count} audit records older than {retention_days} days",event_category="security");db.commit();return {"archived":count,"cutoff":cutoff}


@router.delete("/access-events/expired")
def purge_access_events(retention_days:int=Query(default=90,ge=30,le=3650),db:Session=Depends(get_db),actor:User=Depends(platform)):
    cutoff=datetime.now(timezone.utc)-timedelta(days=retention_days);count=db.query(SecurityAccessEvent).filter(SecurityAccessEvent.created_at<cutoff).delete(synchronize_session=False);create_audit_log(db,actor.username,"ACCESS_EVENTS_RETENTION_CLEANUP","SecurityAccessEvent","batch",f"Removed {count} expired access events",event_category="security");db.commit();return {"deleted":count,"cutoff":cutoff}


@router.post("/organizations/{organization_id}/domain")
def configure_domain(organization_id:str,payload:DomainRequest,db:Session=Depends(get_db),actor:User=Depends(platform)):
    org=db.get(Organization,organization_id)
    if not org:raise HTTPException(404,"Organization not found")
    if db.query(Organization).filter(Organization.custom_domain==payload.domain.lower(),Organization.id!=org.id).first():raise HTTPException(409,"Domain is already assigned")
    token=secrets.token_urlsafe(32);org.custom_domain=payload.domain.lower();org.custom_domain_status="pending";org.custom_domain_verification_token=token;org.custom_domain_verified_at=None;create_audit_log(db,actor.username,"DOMAIN_VERIFICATION_STARTED","Organization",str(org.id),f"Started verification for {org.custom_domain}",organization_id=org.id,event_category="security");db.commit();return {"domain":org.custom_domain,"status":"pending","dns_record":{"type":"TXT","name":f"_hiop-verification.{org.custom_domain}","value":f"hiop-verification={token}"},"tls":"Provision TLS only after verification succeeds"}


@router.post("/organizations/{organization_id}/domain/verify")
def verify_domain(organization_id:str,db:Session=Depends(get_db),actor:User=Depends(platform)):
    org=db.get(Organization,organization_id)
    if not org or not org.custom_domain or not org.custom_domain_verification_token:raise HTTPException(404,"Pending domain verification not found")
    expected=f"hiop-verification={org.custom_domain_verification_token}"
    try:values={str(value).strip('"') for answer in dns.resolver.resolve(f"_hiop-verification.{org.custom_domain}","TXT") for value in answer.strings}
    except Exception:values=set()
    if expected not in values:raise HTTPException(409,"DNS verification record was not found")
    org.custom_domain_status="verified";org.custom_domain_verified_at=datetime.now(timezone.utc);create_audit_log(db,actor.username,"DOMAIN_VERIFIED","Organization",str(org.id),f"Verified {org.custom_domain}",organization_id=org.id,event_category="security");db.commit();return {"domain":org.custom_domain,"status":"verified","tls":"Ready for hosting-provider certificate provisioning"}
