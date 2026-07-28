import uuid
from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from app.core.security import get_db,require_roles
from app.models.automation import AutomationWorkflow,AutomationWorkflowVersion
from app.models.automation_triggers import AutomationEventRecord,AutomationTriggerSubscription,AutomationWorkflowSchedule
router=APIRouter(prefix="/automation",tags=["Automation triggers"]); reader=require_roles(["admin","technician","viewer"]); admin=require_roles(["admin"])
ALLOWED_EVENTS={"alert_created","ticket_created","device_offline","device_restored","technology_service_degraded","configuration_drift_detected","compliance_violation_created","maintenance_window_started"}
class EventWrite(BaseModel): event_type:str; property_id:UUID|None=None; source_entity_type:str|None=None; source_entity_id:UUID|None=None; safe_payload:dict=Field(default_factory=dict)
class SubscriptionWrite(BaseModel): workflow_id:UUID; workflow_version_id:UUID; property_id:UUID|None=None; event_type:str; trigger_mode:str="notify_only"; cooldown_seconds:int=Field(default=300,ge=0,le=86400)
@router.get("/events")
def events(db:Session=Depends(get_db),_=Depends(reader)): return {"items":db.query(AutomationEventRecord).order_by(AutomationEventRecord.received_at.desc()).limit(100).all()}
@router.post("/events",status_code=202)
def publish_event(p:EventWrite,db:Session=Depends(get_db),_=Depends(admin)):
    if p.event_type not in ALLOWED_EVENTS: raise HTTPException(400,"Event type is not registered")
    if len(str(p.safe_payload))>10000: raise HTTPException(400,"Event payload exceeds limit")
    row=AutomationEventRecord(event_id=uuid.uuid4(),event_type=p.event_type,property_id=p.property_id,source_entity_type=p.source_entity_type,source_entity_id=p.source_entity_id,safe_payload=str(p.safe_payload),occurred_at=datetime.now(timezone.utc));db.add(row);db.commit();return {"event_id":str(row.event_id),"status":"received"}
@router.get("/triggers")
def triggers(db:Session=Depends(get_db),_=Depends(reader)): return {"items":db.query(AutomationTriggerSubscription).limit(100).all()}
@router.post("/triggers",status_code=201)
def create_trigger(p:SubscriptionWrite,db:Session=Depends(get_db),_=Depends(admin)):
    if p.event_type not in ALLOWED_EVENTS: raise HTTPException(400,"Event type is not registered")
    if not db.get(AutomationWorkflow,p.workflow_id) or not db.get(AutomationWorkflowVersion,p.workflow_version_id): raise HTTPException(404,"Workflow or version not found")
    row=AutomationTriggerSubscription(**p.model_dump());db.add(row);db.commit();db.refresh(row);return row
@router.get("/schedules")
def schedules(db:Session=Depends(get_db),_=Depends(reader)): return {"items":db.query(AutomationWorkflowSchedule).order_by(AutomationWorkflowSchedule.next_run_at).limit(100).all()}
@router.post("/schedules",status_code=201)
def create_schedule(workflow_id:UUID,workflow_version_id:UUID,name:str,db:Session=Depends(get_db),_=Depends(admin)):
    row=AutomationWorkflowSchedule(workflow_id=workflow_id,workflow_version_id=workflow_version_id,name=name);db.add(row);db.commit();db.refresh(row);return row
