import uuid
import json
from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from app.core.security import get_db,require_roles
from app.models.automation import AutomationWorkflow,AutomationWorkflowRun,AutomationWorkflowVersion
from app.models.automation_triggers import AutomationEventRecord,AutomationTriggerSubscription,AutomationWorkflowSchedule,AutomationTriggerExecution
from app.models.property_access import UserPropertyAccess
from app.services.automation_trigger_service import EVENT_CATALOG,preview_subscription,process_event,validate_payload,validate_subscription
from app.services.scheduler_service import reconcile_automation_jobs,remove_automation_job,scheduled_automation_workflow
from app.services.audit_service import create_audit_log
router=APIRouter(prefix="/automation",tags=["Automation triggers"]); reader=require_roles(["admin","technician","viewer"]); admin=require_roles(["admin"])
ALLOWED_EVENTS=set(EVENT_CATALOG)
class EventWrite(BaseModel): event_type:str; event_id:UUID|None=None; property_id:UUID|None=None; source_entity_type:str|None=None; source_entity_id:UUID|None=None; severity:str|None=None; status:str|None=None; correlation_key:str|None=Field(None,max_length=160); safe_payload:dict=Field(default_factory=dict)
class SubscriptionWrite(BaseModel): workflow_id:UUID; workflow_version_id:UUID; property_id:UUID|None=None; event_type:str; trigger_mode:str="notify_only"; filter_definition:dict=Field(default_factory=dict); condition_definition:dict=Field(default_factory=dict); input_mapping:dict=Field(default_factory=dict); cooldown_seconds:int=Field(default=300,ge=0,le=86400); deduplication_window_seconds:int=Field(default=300,ge=0,le=86400); correlation_window_seconds:int=Field(default=300,ge=0,le=86400); maximum_runs_per_window:int=Field(default=5,ge=1,le=100); run_window_seconds:int=Field(default=3600,ge=60,le=86400); delay_seconds:int=Field(default=0,ge=0,le=3600); approval_mode:str="use_workflow_policy"; maintenance_behavior:str="suppress"; blackout_behavior:str="suppress"; blackout_start:datetime|None=None; blackout_end:datetime|None=None
class ScheduleWrite(BaseModel): workflow_id:UUID; workflow_version_id:UUID; property_id:UUID|None=None; name:str=Field(min_length=1,max_length=120); schedule_type:str="interval"; timezone:str="UTC"; interval_minutes:int|None=Field(default=None,ge=5,le=10080); next_run_at:datetime|None=None; maximum_runs:int|None=Field(default=None,ge=1,le=10000); approval_mode:str="use_workflow_policy"; maintenance_behavior:str="suppress"; blackout_start:datetime|None=None; blackout_end:datetime|None=None; enabled:bool=False
class ReprocessWrite(BaseModel): reason:str=Field(min_length=8,max_length=500); trigger_ids:list[UUID]=Field(default_factory=list,max_length=25)
def _validate_event_payload(payload):
    try:validate_payload(payload)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
def _allowed_properties(db,user):
    if user.role=="admin":return None
    return [row.property_id for row in db.query(UserPropertyAccess).filter_by(user_id=user.id,enabled=True).all()]
def _scope(query,column,db,user):
    allowed=_allowed_properties(db,user)
    return query if allowed is None else query.filter(column.in_(allowed))
def _validate_workflow_scope(workflow,property_id):
    if workflow.property_id!=property_id:raise HTTPException(422,"Workflow and trigger/schedule property must match")
def _validate_schedule(p):
    if p.schedule_type not in {"interval","one_time"}:raise HTTPException(422,"Unsupported schedule type")
    if p.schedule_type=="interval" and not p.interval_minutes:raise HTTPException(422,"Interval schedules require interval_minutes")
    if p.schedule_type=="one_time" and not p.next_run_at:raise HTTPException(422,"One-time schedules require next_run_at")
    if p.blackout_start and p.blackout_end and p.blackout_end<=p.blackout_start:raise HTTPException(422,"Blackout end must be after blackout start")
    if p.approval_mode not in {"use_workflow_policy","always_require"} or p.maintenance_behavior not in {"suppress","allow"}:raise HTTPException(422,"Unsupported execution policy")
@router.get("/events")
def events(db:Session=Depends(get_db),user=Depends(reader)): return {"items":_scope(db.query(AutomationEventRecord),AutomationEventRecord.property_id,db,user).order_by(AutomationEventRecord.received_at.desc()).limit(100).all()}
@router.get("/event-catalogue")
def event_catalogue(_=Depends(reader)):
    return {"items":[{"event_type":key,"source_module":value["module"],"schema_version":1,"triggerable":True,"allowed_filter_fields":sorted(value["fields"])} for key,value in sorted(EVENT_CATALOG.items())]}
@router.get("/events/{event_id}")
def event_detail(event_id:UUID,db:Session=Depends(get_db),user=Depends(reader)):
    row=_scope(db.query(AutomationEventRecord).filter(AutomationEventRecord.id==event_id),AutomationEventRecord.property_id,db,user).first()
    if not row:raise HTTPException(404,"Event not found")
    executions=db.query(AutomationTriggerExecution).filter_by(event_id=row.id).order_by(AutomationTriggerExecution.created_at).all()
    return {"event":row,"executions":executions}
@router.post("/events",status_code=202)
def publish_event(p:EventWrite,db:Session=Depends(get_db),user=Depends(admin)):
    if p.event_type not in ALLOWED_EVENTS: raise HTTPException(400,"Event type is not registered")
    _validate_event_payload(p.safe_payload);encoded=json.dumps(p.safe_payload,separators=(",",":"))
    if len(encoded)>10000: raise HTTPException(400,"Event payload exceeds limit")
    event_id=p.event_id or uuid.uuid4()
    existing=db.query(AutomationEventRecord).filter_by(event_id=event_id).first()
    if existing:return {"event_id":str(existing.event_id),"status":existing.processing_status,"replayed":True}
    row=AutomationEventRecord(event_id=event_id,event_type=p.event_type,property_id=p.property_id,source_module=EVENT_CATALOG[p.event_type]["module"],source_entity_type=p.source_entity_type,source_entity_id=p.source_entity_id,severity=p.severity,status=p.status,correlation_key=p.correlation_key,safe_payload=encoded,occurred_at=datetime.now(timezone.utc));db.add(row);db.flush();result=process_event(db,row);create_audit_log(db,user.username,"AUTOMATION_EVENT_PROCESSED","AutomationEventRecord",str(row.id),f"Processed registered event {row.event_type}");db.commit();return {"event_id":str(row.event_id),"status":row.processing_status,"replayed":False,**result}
@router.post("/events/{event_id}/reprocess",status_code=202)
def reprocess_event(event_id:UUID,p:ReprocessWrite,db:Session=Depends(get_db),user=Depends(admin)):
    source=db.get(AutomationEventRecord,event_id)
    if not source:raise HTTPException(404,"Event not found")
    clone=AutomationEventRecord(event_id=uuid.uuid4(),event_type=source.event_type,event_version=source.event_version,property_id=source.property_id,source_module=source.source_module,source_entity_type=source.source_entity_type,source_entity_id=source.source_entity_id,severity=source.severity,status=source.status,correlation_key=f"reprocess:{source.event_id}:{uuid.uuid4()}",safe_payload=source.safe_payload,occurred_at=datetime.now(timezone.utc));db.add(clone);db.flush()
    result=process_event(db,clone,subscription_ids=set(p.trigger_ids) if p.trigger_ids else None,bypass_deduplication=True)
    create_audit_log(db,user.username,"AUTOMATION_EVENT_REPROCESSED","AutomationEventRecord",str(clone.id),f"Reprocessed event {source.event_id}; reason recorded")
    db.commit();return {"event_id":clone.event_id,"source_event_id":source.event_id,"status":clone.processing_status,**result}
@router.get("/triggers")
def triggers(db:Session=Depends(get_db),user=Depends(reader)): return {"items":_scope(db.query(AutomationTriggerSubscription),AutomationTriggerSubscription.property_id,db,user).limit(100).all()}
@router.get("/triggers/{trigger_id}")
def trigger_detail(trigger_id:UUID,db:Session=Depends(get_db),user=Depends(reader)):
    row=_scope(db.query(AutomationTriggerSubscription).filter_by(id=trigger_id),AutomationTriggerSubscription.property_id,db,user).first()
    if not row:raise HTTPException(404,"Trigger not found")
    history=db.query(AutomationTriggerExecution).filter_by(subscription_id=row.id).order_by(AutomationTriggerExecution.created_at.desc()).limit(100).all()
    return {"trigger":row,"history":history}
@router.post("/triggers",status_code=201)
def create_trigger(p:SubscriptionWrite,db:Session=Depends(get_db),user=Depends(admin)):
    if p.event_type not in ALLOWED_EVENTS: raise HTTPException(400,"Event type is not registered")
    workflow=db.get(AutomationWorkflow,p.workflow_id);version=db.get(AutomationWorkflowVersion,p.workflow_version_id)
    if not workflow or not version or version.workflow_id!=workflow.id: raise HTTPException(404,"Workflow or version not found")
    _validate_workflow_scope(workflow,p.property_id)
    errors=validate_subscription(p)
    if errors:raise HTTPException(422,{"message":"Invalid trigger subscription","errors":errors})
    values=p.model_dump(exclude={"filter_definition","condition_definition","input_mapping"});row=AutomationTriggerSubscription(**values,filter_definition=json.dumps(p.filter_definition,separators=(",",":")) if p.filter_definition else None,condition_definition=json.dumps(p.condition_definition,separators=(",",":")) if p.condition_definition else None,input_mapping=json.dumps(p.input_mapping,separators=(",",":")) if p.input_mapping else None,created_by=user.username);db.add(row);create_audit_log(db,user.username,"AUTOMATION_TRIGGER_CREATED","AutomationTriggerSubscription",str(row.id),f"Created trigger for {p.event_type}");db.commit();db.refresh(row);return row
@router.put("/triggers/{trigger_id}")
def update_trigger(trigger_id:UUID,p:SubscriptionWrite,db:Session=Depends(get_db),user=Depends(admin)):
    row=db.get(AutomationTriggerSubscription,trigger_id)
    if not row:raise HTTPException(404,"Trigger not found")
    workflow=db.get(AutomationWorkflow,p.workflow_id);version=db.get(AutomationWorkflowVersion,p.workflow_version_id)
    if not workflow or not version or version.workflow_id!=workflow.id:raise HTTPException(404,"Workflow or version not found")
    _validate_workflow_scope(workflow,p.property_id);errors=validate_subscription(p)
    if errors:raise HTTPException(422,{"message":"Invalid trigger subscription","errors":errors})
    values=p.model_dump(exclude={"filter_definition","condition_definition","input_mapping"})
    for key,value in values.items():setattr(row,key,value)
    row.filter_definition=json.dumps(p.filter_definition,separators=(",",":")) if p.filter_definition else None;row.condition_definition=json.dumps(p.condition_definition,separators=(",",":")) if p.condition_definition else None;row.input_mapping=json.dumps(p.input_mapping,separators=(",",":")) if p.input_mapping else None;row.enabled=False
    create_audit_log(db,user.username,"AUTOMATION_TRIGGER_UPDATED","AutomationTriggerSubscription",str(row.id),"Updated trigger; re-enable required");db.commit();db.refresh(row);return row
@router.post("/trigger-validation")
def validate_trigger(p:SubscriptionWrite,db:Session=Depends(get_db),_=Depends(admin)):
    workflow=db.get(AutomationWorkflow,p.workflow_id);version=db.get(AutomationWorkflowVersion,p.workflow_version_id);errors=validate_subscription(p)
    if not workflow or not version or version.workflow_id!=p.workflow_id:errors.append("Workflow or exact version does not exist")
    elif workflow.property_id!=p.property_id:errors.append("Workflow property does not match trigger property")
    elif not workflow.enabled or version.status!="approved":errors.append("Workflow must be enabled with an approved exact version")
    return {"valid":not errors,"errors":errors,"warnings":["Automatic execution remains approval-aware and bounded"],"risk":"controlled"}
@router.post("/triggers/{trigger_id}/test")
def test_trigger(trigger_id:UUID,p:EventWrite,db:Session=Depends(get_db),_=Depends(admin)):
    row=db.get(AutomationTriggerSubscription,trigger_id)
    if not row:raise HTTPException(404,"Trigger not found")
    if p.event_type!=row.event_type:raise HTTPException(422,"Test event type does not match trigger")
    _validate_event_payload(p.safe_payload);return preview_subscription(row,p)
@router.post("/triggers/{trigger_id}/enable")
def enable_trigger(trigger_id:UUID,db:Session=Depends(get_db),user=Depends(admin)):
    row=db.get(AutomationTriggerSubscription,trigger_id)
    if not row:raise HTTPException(404,"Trigger not found")
    workflow=db.get(AutomationWorkflow,row.workflow_id);version=db.get(AutomationWorkflowVersion,row.workflow_version_id)
    if not workflow or not version or not workflow.enabled or version.status!="approved":raise HTTPException(409,"Workflow must be enabled with an approved version")
    row.enabled=True;create_audit_log(db,user.username,"AUTOMATION_TRIGGER_ENABLED","AutomationTriggerSubscription",str(row.id),"Enabled internal event trigger");db.commit();return {"enabled":True}
@router.post("/triggers/{trigger_id}/disable")
def disable_trigger(trigger_id:UUID,db:Session=Depends(get_db),user=Depends(admin)):
    row=db.get(AutomationTriggerSubscription,trigger_id)
    if not row:raise HTTPException(404,"Trigger not found")
    row.enabled=False;db.commit();return {"enabled":False}
@router.delete("/triggers/{trigger_id}",status_code=204)
def delete_trigger(trigger_id:UUID,db:Session=Depends(get_db),user=Depends(admin)):
    row=db.get(AutomationTriggerSubscription,trigger_id)
    if not row:raise HTTPException(404,"Trigger not found")
    if row.enabled:raise HTTPException(409,"Disable the trigger before deletion")
    create_audit_log(db,user.username,"AUTOMATION_TRIGGER_DELETED","AutomationTriggerSubscription",str(row.id),"Deleted disabled trigger");db.delete(row);db.commit()
@router.get("/trigger-executions")
def trigger_history(db:Session=Depends(get_db),user=Depends(reader)):return {"items":_scope(db.query(AutomationTriggerExecution),AutomationTriggerExecution.property_id,db,user).order_by(AutomationTriggerExecution.created_at.desc()).limit(100).all()}
@router.get("/schedules")
def schedules(db:Session=Depends(get_db),user=Depends(reader)): return {"items":_scope(db.query(AutomationWorkflowSchedule),AutomationWorkflowSchedule.property_id,db,user).order_by(AutomationWorkflowSchedule.next_run_at).limit(100).all()}
@router.get("/schedules/{schedule_id}")
def schedule_detail(schedule_id:UUID,db:Session=Depends(get_db),user=Depends(reader)):
    row=_scope(db.query(AutomationWorkflowSchedule).filter_by(id=schedule_id),AutomationWorkflowSchedule.property_id,db,user).first()
    if not row:raise HTTPException(404,"Schedule not found")
    history=db.query(AutomationWorkflowRun).filter(AutomationWorkflowRun.workflow_id==row.workflow_id,AutomationWorkflowRun.trigger_type=="scheduled").order_by(AutomationWorkflowRun.created_at.desc()).limit(100).all()
    return {"schedule":row,"history":history}
@router.post("/schedules",status_code=201)
def create_schedule(p:ScheduleWrite,db:Session=Depends(get_db),user=Depends(admin)):
    workflow=db.get(AutomationWorkflow,p.workflow_id);version=db.get(AutomationWorkflowVersion,p.workflow_version_id)
    if not workflow or not version or version.workflow_id!=workflow.id:raise HTTPException(404,"Workflow or version not found")
    _validate_workflow_scope(workflow,p.property_id);_validate_schedule(p)
    if p.enabled and (not workflow.enabled or version.status!="approved"):raise HTTPException(409,"Enabled schedules require an enabled workflow and approved version")
    row=AutomationWorkflowSchedule(**p.model_dump());db.add(row);db.flush();create_audit_log(db,user.username,"AUTOMATION_SCHEDULE_CREATED","AutomationWorkflowSchedule",str(row.id),f"Created {row.schedule_type} workflow schedule");db.commit();db.refresh(row);reconcile_automation_jobs(db);return row
@router.put("/schedules/{schedule_id}")
def update_schedule(schedule_id:UUID,p:ScheduleWrite,db:Session=Depends(get_db),user=Depends(admin)):
    row=db.get(AutomationWorkflowSchedule,schedule_id)
    if not row:raise HTTPException(404,"Schedule not found")
    workflow=db.get(AutomationWorkflow,p.workflow_id);version=db.get(AutomationWorkflowVersion,p.workflow_version_id)
    if not workflow or not version or version.workflow_id!=workflow.id:raise HTTPException(404,"Workflow or version not found")
    _validate_workflow_scope(workflow,p.property_id);_validate_schedule(p)
    if p.enabled and (not workflow.enabled or version.status!="approved"):raise HTTPException(409,"Enabled schedules require an enabled workflow and approved version")
    for key,value in p.model_dump().items():setattr(row,key,value)
    db.commit();reconcile_automation_jobs(db);return row
@router.post("/schedules/{schedule_id}/enable")
def enable_schedule(schedule_id:UUID,db:Session=Depends(get_db),user=Depends(admin)):
    row=db.get(AutomationWorkflowSchedule,schedule_id)
    if not row:raise HTTPException(404,"Schedule not found")
    workflow=db.get(AutomationWorkflow,row.workflow_id);version=db.get(AutomationWorkflowVersion,row.workflow_version_id)
    if not workflow or not version or not workflow.enabled or version.status!="approved":raise HTTPException(409,"Workflow must be enabled with an approved exact version")
    row.enabled=True;create_audit_log(db,user.username,"AUTOMATION_SCHEDULE_ENABLED","AutomationWorkflowSchedule",str(row.id),"Enabled workflow schedule");db.commit();reconcile_automation_jobs(db);return {"enabled":True}
@router.post("/schedules/{schedule_id}/disable")
def disable_schedule(schedule_id:UUID,db:Session=Depends(get_db),user=Depends(admin)):
    row=db.get(AutomationWorkflowSchedule,schedule_id)
    if not row:raise HTTPException(404,"Schedule not found")
    row.enabled=False;create_audit_log(db,user.username,"AUTOMATION_SCHEDULE_DISABLED","AutomationWorkflowSchedule",str(row.id),"Disabled workflow schedule");db.commit();remove_automation_job(str(row.id));return {"enabled":False}
@router.post("/schedules/{schedule_id}/run-now",status_code=202)
def run_schedule_now(schedule_id:UUID,db:Session=Depends(get_db),user=Depends(admin)):
    row=db.get(AutomationWorkflowSchedule,schedule_id)
    if not row:raise HTTPException(404,"Schedule not found")
    if not row.enabled:raise HTTPException(409,"Schedule is disabled")
    create_audit_log(db,user.username,"AUTOMATION_SCHEDULE_RUN_NOW","AutomationWorkflowSchedule",str(row.id),"Requested bounded schedule run");db.commit();scheduled_automation_workflow(str(row.id));return {"accepted":True,"schedule_id":row.id}
@router.delete("/schedules/{schedule_id}",status_code=204)
def delete_schedule(schedule_id:UUID,db:Session=Depends(get_db),_=Depends(admin)):
    row=db.get(AutomationWorkflowSchedule,schedule_id)
    if not row:raise HTTPException(404,"Schedule not found")
    remove_automation_job(str(row.id));db.delete(row);db.commit()
@router.get("/scheduler-status")
def scheduler_status(db:Session=Depends(get_db),_=Depends(reader)):
    from app.services.scheduler_service import scheduler,AUTOMATION_JOB_PREFIX
    jobs=[{"id":job.id,"next_run_time":job.next_run_time} for job in scheduler.get_jobs() if job.id.startswith(AUTOMATION_JOB_PREFIX)]
    return {"scheduler_running":scheduler.running,"jobs":jobs,"enabled_schedules":db.query(AutomationWorkflowSchedule).filter_by(enabled=True).count()}
