from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from app.core.security import get_db,require_roles
from app.core.tenant import organization_context
from app.models.hierarchy import Property
from app.models.alert import Alert,AlertHistory,AlertRule,InAppNotification,MonitoringEvent
from app.models.device import Device
from app.models.user import User
from app.services.audit_service import create_audit_log

router=APIRouter(prefix="/alert-center",tags=["V3E Alerts and Events"]);reader=require_roles(["platformadmin","admin","technician","viewer"]);operator=require_roles(["admin","technician"]);admin=require_roles(["admin"])
class Resolution(BaseModel):reason:str=Field(min_length=3,max_length=500)
class RuleUpdate(BaseModel):enabled:bool;severity:str=Field(pattern="^(info|warning|critical)$");threshold_value:float|None=None;duration_minutes:int=Field(ge=0,le=1440);consecutive_observations:int=Field(ge=1,le=100);notify_in_app:bool=True;notify_email:bool=False
def view(db,row,device=None):
    device=device or db.get(Device,row.device_id);return {"id":str(row.id),"device_id":str(row.device_id),"device_name":device.hostname if device else "Unavailable device","device_type":device.device_type if device else "Unknown","ip_address":device.ip_address if device else None,"title":row.title,"severity":row.severity,"status":row.lifecycle_status,"alert_type":row.alert_type,"source":row.source,"reason":row.reason,"evidence":row.evidence,"current_value":row.current_value,"threshold_value":row.threshold_value,"triggered_at":row.created_at,"last_updated":row.last_updated_at,"acknowledged_by":row.acknowledged_by,"acknowledged_at":row.acknowledged_at,"resolved_at":row.resolved_at,"resolution_reason":row.resolution_reason,"manually_resolved":row.manually_resolved}
def scoped_alert(db,alert_id,organization_id):
    row=db.query(Alert).join(Device,Alert.device_id==Device.id).join(Property,Device.property_id==Property.id).filter(Alert.id==alert_id,Property.organization_id==organization_id).first()
    if not row:raise HTTPException(404,"Alert not found")
    return row
@router.get("/alerts")
def alerts(status:str|None=None,severity:str|None=None,alert_type:str|None=None,search:str|None=None,db:Session=Depends(get_db),_=Depends(reader),organization_id=Depends(organization_context)):
    allowed_devices=db.query(Device.id).join(Property,Device.property_id==Property.id).filter(Property.organization_id==organization_id).subquery();rows=db.query(Alert).filter(Alert.device_id.in_(allowed_devices)).order_by(Alert.created_at.desc()).limit(1000).all();device_ids={row.device_id for row in rows};devices={row.id:row for row in db.query(Device).filter(Device.id.in_(device_ids)).all()} if device_ids else {};items=[view(db,row,devices.get(row.device_id)) for row in rows];items=[row for row in items if (not status or row["status"]==status) and (not severity or row["severity"]==severity) and (not alert_type or row["alert_type"]==alert_type) and (not search or search.lower() in f'{row["title"]} {row["device_name"]} {row["ip_address"]}'.lower())];return {"items":items,"summary":{key:sum(row["severity"]==key for row in items) for key in ("critical","warning","info")}}
@router.get("/alerts/{alert_id}")
def alert_detail(alert_id:UUID,db:Session=Depends(get_db),_=Depends(reader),organization_id=Depends(organization_context)):
    row=scoped_alert(db,alert_id,organization_id)
    result=view(db,row);result["history"]=[{"action":x.action,"actor":x.actor,"previous_status":x.previous_status,"current_status":x.current_status,"reason":x.reason,"created_at":x.created_at} for x in db.query(AlertHistory).filter_by(alert_id=row.id).order_by(AlertHistory.created_at).all()];return result
@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge(alert_id:UUID,db:Session=Depends(get_db),user:User=Depends(operator),organization_id=Depends(organization_context)):
    row=scoped_alert(db,alert_id,organization_id)
    if row.lifecycle_status=="resolved":raise HTTPException(409,"Resolved alerts cannot be acknowledged")
    previous=row.lifecycle_status;row.lifecycle_status="acknowledged";row.acknowledged=True;row.acknowledged_by=str(user.id);row.acknowledged_at=datetime.now(timezone.utc);row.last_updated_at=row.acknowledged_at;db.add(AlertHistory(alert_id=row.id,action="acknowledged",actor=user.username,previous_status=previous,current_status="acknowledged",reason="Acknowledged by authorized user"));create_audit_log(db,user.username,"ALERT_ACKNOWLEDGED","Alert",str(row.id),row.title);db.commit();return view(db,row)
@router.post("/alerts/{alert_id}/resolve")
def resolve(alert_id:UUID,payload:Resolution,db:Session=Depends(get_db),user:User=Depends(operator),organization_id=Depends(organization_context)):
    row=scoped_alert(db,alert_id,organization_id)
    previous=row.lifecycle_status;row.lifecycle_status="resolved";row.resolved_by=str(user.id);row.resolved_at=datetime.now(timezone.utc);row.resolution_reason=payload.reason;row.manually_resolved=True;row.last_updated_at=row.resolved_at;db.add(AlertHistory(alert_id=row.id,action="manually_resolved",actor=user.username,previous_status=previous,current_status="resolved",reason=payload.reason));create_audit_log(db,user.username,"ALERT_MANUALLY_RESOLVED","Alert",str(row.id),payload.reason);db.commit();return view(db,row)
@router.get("/events")
def events(limit:int=Query(200,ge=1,le=1000),db:Session=Depends(get_db),_=Depends(reader)):return [{"id":str(x.id),"device_id":str(x.device_id),"event_type":x.event_type,"source":x.source,"value":x.value_numeric,"evidence":x.evidence,"occurred_at":x.occurred_at} for x in db.query(MonitoringEvent).order_by(MonitoringEvent.occurred_at.desc()).limit(limit)]
@router.get("/rules")
def rules(db:Session=Depends(get_db),_=Depends(reader)):return db.query(AlertRule).order_by(AlertRule.name).all()
@router.put("/rules/{rule_id}")
def update_rule(rule_id:UUID,payload:RuleUpdate,db:Session=Depends(get_db),user:User=Depends(admin)):
    row=db.get(AlertRule,rule_id)
    if not row:raise HTTPException(404,"Alert rule not found")
    for key,value in payload.model_dump().items():setattr(row,key,value)
    row.updated_by=str(user.id);row.updated_at=datetime.now(timezone.utc);create_audit_log(db,user.username,"ALERT_RULE_CHANGED","AlertRule",str(row.id),f"Updated predefined rule {row.name}");db.commit();return row
@router.get("/notifications")
def notifications(db:Session=Depends(get_db),user:User=Depends(reader)):return [{"id":str(x.id),"alert_id":str(x.alert_id),"channel":x.channel,"status":x.delivery_status,"read_at":x.read_at,"created_at":x.created_at} for x in db.query(InAppNotification).filter(InAppNotification.user_id==str(user.id)).order_by(InAppNotification.created_at.desc()).limit(200)]
