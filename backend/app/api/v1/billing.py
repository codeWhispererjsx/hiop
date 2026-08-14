import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.core.tenant import organization_context
from app.models.billing import BillingDocumentReference, BillingEvent, CommercialPlan, OrganizationSubscription
from app.models.hierarchy import Organization
from app.models.user import User
from app.services.audit_service import create_audit_log
from app.services.billing_service import present_plan, present_subscription, provider, start_trial, unpack, usage

router=APIRouter(prefix="/billing",tags=["Billing and subscriptions"])
org_admin=require_roles(["admin"]);platform=require_roles(["platformadmin"])

class TrialWrite(BaseModel):plan_code:str=Field(min_length=2,max_length=40)
class PlanChange(BaseModel):plan_code:str=Field(min_length=2,max_length=40);billing_interval:str=Field(pattern="^(monthly|yearly)$")
class CancelWrite(BaseModel):at_period_end:bool=True
class PlanPatch(BaseModel):name:str|None=None;description:str|None=None;monthly_price:str|None=None;yearly_price:str|None=None;currency:str|None=Field(default=None,min_length=3,max_length=3);trial_days:int|None=Field(default=None,ge=0,le=90);features:list[str]|None=None;entitlements:list[str]|None=None;limits:dict[str,int]|None=None;is_active:bool|None=None

@router.get("/public/plans")
def public_plans(db:Session=Depends(get_db)):
    return [present_plan(x) for x in db.query(CommercialPlan).filter(CommercialPlan.is_active.is_(True)).order_by(CommercialPlan.sort_order)]

@router.get("/current")
def current(db:Session=Depends(get_db),actor:User=Depends(org_admin),org=Depends(organization_context)):
    row=db.query(OrganizationSubscription).filter_by(organization_id=org).first()
    if not row:return {"subscription":None,"usage":usage(db,org)}
    result=present_subscription(db,row);db.commit();return {"subscription":result}

@router.get("/documents")
def documents(db:Session=Depends(get_db),actor:User=Depends(org_admin),org=Depends(organization_context)):
    return [{"id":str(x.id),"type":x.document_type,"hosted_url":x.hosted_url,"amount":str(x.amount) if x.amount is not None else None,"currency":x.currency,"status":x.status,"issued_at":x.issued_at} for x in db.query(BillingDocumentReference).filter_by(organization_id=org).order_by(BillingDocumentReference.issued_at.desc())]

@router.post("/trial",status_code=201)
def trial(payload:TrialWrite,db:Session=Depends(get_db),actor:User=Depends(org_admin),org=Depends(organization_context)):
    row=start_trial(db,org,payload.plan_code,actor);db.commit();db.refresh(row);return present_subscription(db,row)

@router.post("/checkout")
def checkout(payload:PlanChange,db:Session=Depends(get_db),actor:User=Depends(org_admin),org=Depends(organization_context)):
    plan=db.query(CommercialPlan).filter_by(code=payload.plan_code.lower(),is_active=True).first()
    if not plan:raise HTTPException(404,"Plan not found")
    return provider().checkout(organization_id=org,plan=plan,interval=payload.billing_interval,actor=actor)

@router.post("/change-plan")
def change_plan(payload:PlanChange,db:Session=Depends(get_db),actor:User=Depends(org_admin),org=Depends(organization_context)):
    row=db.query(OrganizationSubscription).filter_by(organization_id=org).first()
    if not row:raise HTTPException(404,"Subscription not found")
    plan=db.query(CommercialPlan).filter_by(code=payload.plan_code.lower(),is_active=True).first()
    if not plan:raise HTTPException(404,"Plan not found")
    new_limits=unpack(plan.limits,{});current_usage=usage(db,org);excess={k:{"used":current_usage.get(k,0),"limit":v} for k,v in new_limits.items() if isinstance(v,int) and current_usage.get(k,0)>v}
    if excess:raise HTTPException(409,{"message":"Current usage exceeds the selected plan limits","excess":excess})
    if row.status=="active" and row.provider_subscription_reference:raise HTTPException(409,"Use provider checkout to change a paid subscription")
    previous=db.get(CommercialPlan,row.plan_id);row.plan_id=plan.id;row.billing_interval=payload.billing_interval;db.add(BillingEvent(organization_id=org,subscription_id=row.id,event_type="plan_changed",safe_details=json.dumps({"from":previous.code,"to":plan.code})));create_audit_log(db,actor.username,"BILLING_PLAN_CHANGED","OrganizationSubscription",str(row.id),f"Changed plan from {previous.name} to {plan.name}");db.commit();return present_subscription(db,row)

@router.post("/cancel")
def cancel(payload:CancelWrite,db:Session=Depends(get_db),actor:User=Depends(org_admin),org=Depends(organization_context)):
    row=db.query(OrganizationSubscription).filter_by(organization_id=org).first()
    if not row:raise HTTPException(404,"Subscription not found")
    if row.provider_subscription_reference:return provider().cancel(subscription=row,at_period_end=payload.at_period_end)
    now=datetime.now(timezone.utc);row.cancel_at_period_end=payload.at_period_end
    if payload.at_period_end:row.cancellation_date=row.current_period_end
    else:row.status="cancelled";row.cancellation_date=now;row.current_period_end=now
    db.add(BillingEvent(organization_id=org,subscription_id=row.id,event_type="subscription_cancelled",safe_details=json.dumps({"at_period_end":payload.at_period_end})));create_audit_log(db,actor.username,"BILLING_SUBSCRIPTION_CANCELLED","OrganizationSubscription",str(row.id),"Scheduled cancellation" if payload.at_period_end else "Cancelled subscription");db.commit();return present_subscription(db,row)

@router.get("/platform/overview")
def platform_overview(db:Session=Depends(get_db),_:User=Depends(platform)):
    rows=db.query(OrganizationSubscription).all();items=[]
    for row in rows:
        organization=db.get(Organization,row.organization_id);items.append({"organization":{"id":str(organization.id),"name":organization.name},**present_subscription(db,row)})
    db.commit();return {"plans":db.query(CommercialPlan).count(),"subscriptions":len(items),"active":sum(x["status"]=="active" for x in items),"trials":sum(x["status"]=="trial" for x in items),"past_due":sum(x["status"]=="past_due" for x in items),"cancelled":sum(x["status"]=="cancelled" for x in items),"items":items}

@router.get("/platform/plans")
def platform_plans(db:Session=Depends(get_db),_:User=Depends(platform)):return [present_plan(x) for x in db.query(CommercialPlan).order_by(CommercialPlan.sort_order)]

@router.patch("/platform/plans/{plan_id}")
def update_plan(plan_id:UUID,payload:PlanPatch,db:Session=Depends(get_db),actor:User=Depends(platform)):
    row=db.get(CommercialPlan,plan_id)
    if not row:raise HTTPException(404,"Plan not found")
    data=payload.model_dump(exclude_unset=True)
    for field in ("features","entitlements","limits"):
        if field in data:data[field]=json.dumps(data[field])
    for key,value in data.items():setattr(row,key,value)
    create_audit_log(db,actor.username,"BILLING_PLAN_CONFIGURATION_CHANGED","CommercialPlan",str(row.id),f"Updated commercial plan {row.name}");db.commit();db.refresh(row);return present_plan(row)

@router.post("/webhooks/{provider_name}")
def webhook(provider_name:str):
    raise HTTPException(503,f"{provider_name.title()} webhook processing is unavailable until a verified provider adapter is configured")
