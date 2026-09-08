import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.asset_intelligence import ManagedAsset
from app.models.billing import BillingEvent, CommercialPlan, OrganizationSubscription
from app.models.device import Device
from app.models.hierarchy import Property
from app.models.local_agent import LocalAgentRegistration
from app.models.user import User
from app.services.audit_service import create_audit_log


def unpack(value: str, fallback):
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def money(value):
    return str(value) if isinstance(value, Decimal) else value


def present_plan(row: CommercialPlan):
    return {"id":str(row.id),"code":row.code,"name":row.name,"description":row.description,"audience":row.audience,"monthly_price":money(row.monthly_price),"yearly_price":money(row.yearly_price),"currency":row.currency,"trial_days":row.trial_days,"features":unpack(row.features,[]),"entitlements":unpack(row.entitlements,[]),"limits":unpack(row.limits,{}),"is_active":row.is_active,"sort_order":row.sort_order,"checkout_available":bool((row.provider_monthly_price_id or row.provider_yearly_price_id) and os.getenv("HIOP_BILLING_PROVIDER"))}


def usage(db: Session, organization_id):
    property_ids=db.query(Property.id).filter(Property.organization_id==organization_id).subquery()
    return {
        "assets":db.query(ManagedAsset).filter(ManagedAsset.organization_id==organization_id).count(),
        "devices":db.query(Device).filter(Device.property_id.in_(property_ids)).count(),
        "properties":db.query(Property).filter(Property.organization_id==organization_id,Property.is_active.is_(True)).count(),
        "users":db.query(User).filter(User.organization_id==organization_id,User.is_active.is_(True)).count(),
        "agents":db.query(LocalAgentRegistration).filter(
            LocalAgentRegistration.organization_id==organization_id,
            LocalAgentRegistration.revoked_at.is_(None),
            LocalAgentRegistration.retired_at.is_(None),
        ).count(),
    }


def refresh_status(subscription: OrganizationSubscription, now=None):
    now=now or datetime.now(timezone.utc)
    if subscription.status=="trial" and subscription.trial_end and subscription.trial_end<=now:
        subscription.status="expired";subscription.payment_status="not_paid"
    if subscription.cancel_at_period_end and subscription.current_period_end and subscription.current_period_end<=now:
        subscription.status="cancelled";subscription.cancellation_date=subscription.cancellation_date or now


def present_subscription(db: Session, row: OrganizationSubscription):
    refresh_status(row);plan=db.get(CommercialPlan,row.plan_id);current=usage(db,row.organization_id);limits=unpack(plan.limits,{}) if plan else {}
    return {"id":str(row.id),"organization_id":str(row.organization_id),"plan":present_plan(plan) if plan else None,"status":row.status,"billing_interval":row.billing_interval,"start_date":row.start_date,"trial_start":row.trial_start,"trial_end":row.trial_end,"renewal_date":row.renewal_date,"cancellation_date":row.cancellation_date,"cancel_at_period_end":row.cancel_at_period_end,"current_period_start":row.current_period_start,"current_period_end":row.current_period_end,"provider":row.provider,"payment_status":row.payment_status,"usage":current,"limits":limits,"over_limits":{key:{"used":current.get(key,0),"limit":limit} for key,limit in limits.items() if isinstance(limit,int) and current.get(key,0)>limit}}


def start_trial(db:Session,organization_id,plan_code:str,actor):
    if db.query(OrganizationSubscription).filter_by(organization_id=organization_id).first():raise HTTPException(409,"Organization already has a subscription")
    plan=db.query(CommercialPlan).filter(CommercialPlan.code==plan_code.lower(),CommercialPlan.is_active.is_(True)).first()
    if not plan:raise HTTPException(404,"Plan not found")
    now=datetime.now(timezone.utc);end=now+timedelta(days=plan.trial_days)
    row=OrganizationSubscription(organization_id=organization_id,plan_id=plan.id,status="trial",billing_interval="monthly",start_date=now,trial_start=now,trial_end=end,current_period_start=now,current_period_end=end,payment_status="not_required")
    db.add(row);db.flush();db.add(BillingEvent(organization_id=organization_id,subscription_id=row.id,event_type="trial_started",safe_details=json.dumps({"plan":plan.code,"trial_days":plan.trial_days})));create_audit_log(db,actor.username,"BILLING_TRIAL_STARTED","OrganizationSubscription",str(row.id),f"Started {plan.name} trial");return row


def require_entitlement(db:Session,organization_id,entitlement:str):
    subscription=db.query(OrganizationSubscription).filter_by(organization_id=organization_id).first()
    if not subscription:raise HTTPException(402,"An active HIOP plan is required")
    refresh_status(subscription)
    if subscription.status not in {"trial","active","past_due"}:raise HTTPException(402,"Subscription is not active")
    plan=db.get(CommercialPlan,subscription.plan_id)
    if entitlement not in unpack(plan.entitlements,[]):raise HTTPException(403,"Your current plan does not include this capability")
    return subscription


def enforce_limit(db:Session,organization_id,resource:str,increment:int=1):
    subscription=db.query(OrganizationSubscription).filter_by(organization_id=organization_id).first()
    if not subscription:return
    plan=db.get(CommercialPlan,subscription.plan_id);limit=unpack(plan.limits,{}).get(resource)
    if isinstance(limit,int) and usage(db,organization_id).get(resource,0)+increment>limit:raise HTTPException(409,f"{resource.replace('_',' ').title()} limit reached. Upgrade your plan to continue.")


class BillingProvider:
    """Boundary for a hosted PCI-compliant provider. No card data enters HIOP."""
    name="unconfigured"
    def checkout(self,*_args,**_kwargs):
        raise HTTPException(503,"Online checkout is not configured. Contact the HIOP platform operator.")
    def cancel(self,*_args,**_kwargs):
        raise HTTPException(503,"Provider-managed cancellation is not configured.")


def provider():
    return BillingProvider()
