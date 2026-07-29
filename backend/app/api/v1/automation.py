from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
import hashlib,json
from datetime import datetime,timezone
from time import monotonic
from sqlalchemy.orm import Session
from app.core.security import get_db,require_roles
from app.models.automation import AutomationWorkflow,AutomationWorkflowVersion,AutomationAction,AutomationDryRun,AutomationWorkflowRun,AutomationWorkflowStep,AutomationStepDependency,AutomationStepRun,AutomationApprovalRequest
from app.services.automation_validation_service import validate_graph
from app.services.automation_execution_service import execute_graph,SAFE_HANDLERS
from app.services.audit_service import create_audit_log
from app.services.automation_planning_service import build_plan
from app.services.automation_notification_service import notify_automation
from app.websocket.connection_manager import manager
from app.models.property_access import UserPropertyAccess
router=APIRouter(prefix="/automation",tags=["Automation"]); reader=require_roles(["admin","technician","viewer"]); admin=require_roles(["admin"])
class WorkflowWrite(BaseModel): property_id:UUID|None=None; name:str; code:str; workflow_category:str="custom"
class VersionWrite(BaseModel): trigger_definition:dict=Field(default_factory=dict); workflow_graph:dict=Field(default_factory=dict)
class RunWrite(BaseModel): idempotency_key:str|None=None; dry_run:bool=True
class StepWrite(BaseModel): step_key:str=Field(min_length=1,max_length=80); name:str=Field(min_length=1,max_length=160); step_type:str="action"; action_key:str|None=None; sequence_order:int=Field(0,ge=0,le=1000); timeout_seconds:int=Field(60,ge=1,le=3600); retry_policy:dict=Field(default_factory=dict); condition_definition:dict|None=None; approval_required:bool=False; compensation_action_key:str|None=None; continue_on_failure:bool=False; enabled:bool=True
class DependencyWrite(BaseModel): upstream_step_id:UUID; downstream_step_id:UUID; dependency_type:str="success"
class ApprovalDecision(BaseModel): decision:str; reason:str|None=None
def _publish(event,**safe): manager.broadcast_from_thread({"type":event,**{key:str(value) if isinstance(value,UUID) else value for key,value in safe.items()}})
def _authorized_property_ids(db,user):
    if user.role in {"admin","superadmin"}: return None
    return [row.property_id for row in db.query(UserPropertyAccess).filter_by(user_id=user.id,enabled=True).all()]
def _assert_workflow_access(db,user,workflow):
    allowed=_authorized_property_ids(db,user)
    if allowed is not None and workflow.property_id not in allowed: raise HTTPException(403,"Workflow property is not authorized")
    return workflow
def _version_workflow(db,user,version_id):
    version=db.get(AutomationWorkflowVersion,version_id)
    if not version: raise HTTPException(404,"Workflow version not found")
    return version,_assert_workflow_access(db,user,db.get(AutomationWorkflow,version.workflow_id))
def _execute_steps(db,run,version,start_after:UUID|None=None):
    steps=db.query(AutomationWorkflowStep).filter_by(workflow_version_id=version.id).all();deps=db.query(AutomationStepDependency).filter_by(workflow_version_id=version.id).all();plan=build_plan(steps,deps);step_map={str(s.id):s for s in steps};resume=start_after is None
    run.status="running"
    for item in plan:
        step=step_map[item["step_id"]]
        if not resume:
            resume=step.id==start_after;continue
        sr=AutomationStepRun(workflow_run_id=run.id,step_id=step.id,status="running",attempt_count=1,started_at=datetime.now(timezone.utc));db.add(sr);db.flush()
        if step.approval_required or step.step_type=="approval":
            sr.status="waiting_approval";run.status="waiting_approval";db.add(AutomationApprovalRequest(workflow_run_id=run.id,step_run_id=sr.id,requested_by=run.triggered_by));_publish("automation_approval_requested",run_id=run.id,step_id=step.id);return
        policy=json.loads(step.retry_policy or "{}");attempts=max(1,min(int(policy.get("max_attempts",1)),3));failure=None
        for attempt in range(1,attempts+1):
            sr.attempt_count=attempt;started=monotonic()
            try:
                result=execute_graph({"nodes":[{"id":step.step_key,"type":"action","action_key":step.action_key or "noop"}],"edges":[]})
                if monotonic()-started>step.timeout_seconds: raise TimeoutError("step exceeded its bounded timeout")
                sr.status="completed";sr.output_summary=json.dumps(result,separators=(",",":"));sr.completed_at=datetime.now(timezone.utc);failure=None;break
            except (ValueError,TimeoutError) as exc: failure=exc
        if failure:
            sr.status="failed";sr.error_category="timeout" if isinstance(failure,TimeoutError) else "action_failed";sr.output_summary=str(failure)[:500];sr.completed_at=datetime.now(timezone.utc);run.status="failed";run.error_summary="Workflow step failed safely"
            if step.compensation_action_key in SAFE_HANDLERS: execute_graph({"nodes":[{"id":"compensate","type":"action","action_key":step.compensation_action_key}],"edges":[]})
            if not step.continue_on_failure:return
    run.status="completed";_publish("automation_run_completed",run_id=run.id,workflow_id=run.workflow_id)
@router.get("/workflows")
def workflows(db:Session=Depends(get_db),user=Depends(reader)):
    q=db.query(AutomationWorkflow);allowed=_authorized_property_ids(db,user)
    if allowed is not None:q=q.filter(AutomationWorkflow.property_id.in_(allowed))
    return {"items":q.order_by(AutomationWorkflow.name).limit(100).all()}
@router.post("/workflows",status_code=201)
def create_workflow(p:WorkflowWrite,db:Session=Depends(get_db),user=Depends(admin)): row=AutomationWorkflow(**p.model_dump(),created_by=user.username);db.add(row);db.flush();create_audit_log(db,user.username,"AUTOMATION_WORKFLOW_CREATED","AutomationWorkflow",str(row.id),f"Created workflow {row.code}");db.commit();db.refresh(row);return row
@router.get("/workflows/{workflow_id}/versions")
def versions(workflow_id:UUID,db:Session=Depends(get_db),user=Depends(reader)):
    workflow=db.get(AutomationWorkflow,workflow_id)
    if not workflow: raise HTTPException(404,"Workflow not found")
    _assert_workflow_access(db,user,workflow)
    return {"items":db.query(AutomationWorkflowVersion).filter_by(workflow_id=workflow_id).order_by(AutomationWorkflowVersion.version_number.desc()).limit(100).all()}
@router.post("/workflows/{workflow_id}/versions",status_code=201)
def create_version(workflow_id:UUID,p:VersionWrite,db:Session=Depends(get_db),user=Depends(admin)):
    workflow=db.get(AutomationWorkflow,workflow_id)
    if not workflow: raise HTTPException(404,"Workflow not found")
    number=(db.query(AutomationWorkflowVersion).filter_by(workflow_id=workflow_id).count()+1)
    graph=json.dumps(p.workflow_graph,separators=(",",":"),sort_keys=True); trigger=json.dumps(p.trigger_definition,separators=(",",":"),sort_keys=True)
    errors=validate_graph(p.workflow_graph,{a.action_key for a in db.query(AutomationAction).filter_by(enabled=True).all()} | SAFE_HANDLERS)
    if errors: raise HTTPException(422,{"message":"Invalid workflow definition","errors":errors})
    if len(graph)>100000 or len(trigger)>20000: raise HTTPException(422,"Workflow definition exceeds safe size limits")
    checksum=hashlib.sha256((trigger+"\n"+graph).encode()).hexdigest()
    row=AutomationWorkflowVersion(workflow_id=workflow_id,version_number=number,trigger_definition=trigger,workflow_graph=graph,checksum=checksum,created_by=user.username)
    db.add(row);db.commit();db.refresh(row);return row
@router.post("/workflow-versions/{version_id}/validate")
def validate_version(version_id:UUID,db:Session=Depends(get_db),user=Depends(reader)):
    row,_=_version_workflow(db,user,version_id)
    try: graph=json.loads(row.workflow_graph or "{}")
    except json.JSONDecodeError: return {"valid":False,"errors":["workflow graph is not valid JSON"]}
    errors=validate_graph(graph,{a.action_key for a in db.query(AutomationAction).filter_by(enabled=True).all()} | SAFE_HANDLERS)
    return {"valid":not errors,"errors":errors,"checksum":row.checksum}
@router.get("/workflow-versions/{version_id}/steps")
def list_steps(version_id:UUID,db:Session=Depends(get_db),user=Depends(reader)): _version_workflow(db,user,version_id);return {"items":db.query(AutomationWorkflowStep).filter_by(workflow_version_id=version_id).order_by(AutomationWorkflowStep.sequence_order).all()}
@router.post("/workflow-versions/{version_id}/steps",status_code=201)
def create_step(version_id:UUID,p:StepWrite,db:Session=Depends(get_db),user=Depends(admin)):
    version=db.get(AutomationWorkflowVersion,version_id)
    if not version: raise HTTPException(404,"Workflow version not found")
    if version.status=="approved": raise HTTPException(409,"Approved workflow versions are immutable")
    if db.query(AutomationWorkflowStep).filter_by(workflow_version_id=version_id).count()>=100: raise HTTPException(409,"Maximum workflow step count reached")
    if p.action_key and p.action_key not in SAFE_HANDLERS and not db.get(AutomationAction,p.action_key): raise HTTPException(422,"Unknown action")
    row=AutomationWorkflowStep(workflow_version_id=version_id,**p.model_dump(exclude={"retry_policy","condition_definition"}),retry_policy=json.dumps(p.retry_policy,separators=(",",":")),condition_definition=json.dumps(p.condition_definition,separators=(",",":")) if p.condition_definition else None);db.add(row);db.commit();db.refresh(row);return row
@router.patch("/workflow-versions/{version_id}/steps/{step_id}")
def update_step(version_id:UUID,step_id:UUID,p:StepWrite,db:Session=Depends(get_db),_=Depends(admin)):
    version=db.get(AutomationWorkflowVersion,version_id);row=db.query(AutomationWorkflowStep).filter_by(id=step_id,workflow_version_id=version_id).first()
    if not version or not row: raise HTTPException(404,"Workflow step not found")
    if version.status=="approved": raise HTTPException(409,"Approved workflow versions are immutable")
    for key,value in p.model_dump(exclude={"retry_policy","condition_definition"}).items(): setattr(row,key,value)
    row.retry_policy=json.dumps(p.retry_policy,separators=(",",":"));row.condition_definition=json.dumps(p.condition_definition,separators=(",",":")) if p.condition_definition else None;db.commit();db.refresh(row);return row
@router.delete("/workflow-versions/{version_id}/steps/{step_id}",status_code=204)
def delete_step(version_id:UUID,step_id:UUID,db:Session=Depends(get_db),_=Depends(admin)):
    version=db.get(AutomationWorkflowVersion,version_id);row=db.query(AutomationWorkflowStep).filter_by(id=step_id,workflow_version_id=version_id).first()
    if not version or not row: raise HTTPException(404,"Workflow step not found")
    if version.status=="approved": raise HTTPException(409,"Approved workflow versions are immutable")
    db.delete(row);db.commit()
@router.post("/workflow-versions/{version_id}/dependencies",status_code=201)
def create_dependency(version_id:UUID,p:DependencyWrite,db:Session=Depends(get_db),_=Depends(admin)):
    version=db.get(AutomationWorkflowVersion,version_id)
    if not version: raise HTTPException(404,"Workflow version not found")
    if version.status=="approved": raise HTTPException(409,"Approved workflow versions are immutable")
    steps=db.query(AutomationWorkflowStep).filter(AutomationWorkflowStep.id.in_([p.upstream_step_id,p.downstream_step_id]),AutomationWorkflowStep.workflow_version_id==version_id).all()
    if len(steps)!=2 or p.upstream_step_id==p.downstream_step_id: raise HTTPException(422,"Invalid step dependency")
    row=AutomationStepDependency(workflow_version_id=version_id,**p.model_dump());db.add(row);db.flush()
    try: build_plan(db.query(AutomationWorkflowStep).filter_by(workflow_version_id=version_id).all(),db.query(AutomationStepDependency).filter_by(workflow_version_id=version_id).all())
    except ValueError as exc: db.rollback();raise HTTPException(422,str(exc))
    db.commit();db.refresh(row);return row
@router.get("/workflow-versions/{version_id}/plan")
def execution_plan(version_id:UUID,db:Session=Depends(get_db),user=Depends(reader)):
    _version_workflow(db,user,version_id)
    try: plan=build_plan(db.query(AutomationWorkflowStep).filter_by(workflow_version_id=version_id).all(),db.query(AutomationStepDependency).filter_by(workflow_version_id=version_id).all())
    except ValueError as exc: raise HTTPException(422,str(exc))
    return {"workflow_version_id":version_id,"steps":plan,"step_count":len(plan),"approval_checkpoints":sum(item["approval_required"] for item in plan)}
@router.post("/workflow-versions/{version_id}/approve")
def approve_version(version_id:UUID,db:Session=Depends(get_db),user=Depends(admin)):
    row=db.get(AutomationWorkflowVersion,version_id)
    if not row: raise HTTPException(404,"Workflow version not found")
    if row.status not in {"draft","rejected"}: raise HTTPException(409,"Only draft or rejected versions can be approved")
    workflow=db.get(AutomationWorkflow,row.workflow_id)
    if workflow.requires_approval and row.created_by==user.username: raise HTTPException(409,"Requester cannot approve their own version")
    row.status="approved";row.approved_by=user.username;workflow.current_version_id=row.id;workflow.status="approved";create_audit_log(db,user.username,"AUTOMATION_VERSION_APPROVED","AutomationWorkflowVersion",str(row.id),"Approved immutable workflow version");db.commit();db.refresh(row);return row
@router.post("/workflow-versions/{version_id}/reject")
def reject_version(version_id:UUID,db:Session=Depends(get_db),user=Depends(admin)):
    row=db.get(AutomationWorkflowVersion,version_id)
    if not row: raise HTTPException(404,"Workflow version not found")
    if row.status not in {"draft","approved"}: raise HTTPException(409,"Version cannot be rejected in its current state")
    row.status="rejected";row.approved_by=None;db.commit();return {"status":row.status}
@router.post("/workflows/{workflow_id}/enable")
def enable_workflow(workflow_id:UUID,db:Session=Depends(get_db),user=Depends(admin)):
    workflow=db.get(AutomationWorkflow,workflow_id)
    if not workflow: raise HTTPException(404,"Workflow not found")
    version=db.get(AutomationWorkflowVersion,workflow.current_version_id) if workflow.current_version_id else None
    if not version or version.status!="approved": raise HTTPException(409,"An approved version is required")
    errors=validate_graph(json.loads(version.workflow_graph or "{}"),{a.action_key for a in db.query(AutomationAction).filter_by(enabled=True).all()} | SAFE_HANDLERS)
    if errors: raise HTTPException(409,{"message":"Workflow is no longer valid","errors":errors})
    workflow.enabled=True;workflow.status="enabled";db.commit();return {"enabled":True,"status":workflow.status}
@router.post("/workflows/{workflow_id}/disable")
def disable_workflow(workflow_id:UUID,db:Session=Depends(get_db),user=Depends(admin)):
    workflow=db.get(AutomationWorkflow,workflow_id)
    if not workflow: raise HTTPException(404,"Workflow not found")
    workflow.enabled=False;workflow.status="disabled";db.commit();return {"enabled":False,"status":workflow.status}
@router.get("/actions")
def actions(db:Session=Depends(get_db),_=Depends(reader)): return {"items":db.query(AutomationAction).filter_by(enabled=True).all()}
@router.post("/workflows/{workflow_id}/dry-run")
def dry_run(workflow_id:UUID,db:Session=Depends(get_db),_=Depends(admin)):
    workflow=db.get(AutomationWorkflow,workflow_id)
    if not workflow: raise HTTPException(404,"Workflow not found")
    version=db.query(AutomationWorkflowVersion).filter_by(workflow_id=workflow.id,status="approved").first()
    if not version: raise HTTPException(409,"No approved workflow version")
    try: graph=json.loads(version.workflow_graph or "{}")
    except json.JSONDecodeError: raise HTTPException(422,"Workflow graph is invalid JSON")
    errors=validate_graph(graph,{a.action_key for a in db.query(AutomationAction).filter_by(enabled=True).all()} | SAFE_HANDLERS)
    actions=[n.get("action_key") for n in graph.get("nodes",[]) if isinstance(n,dict) and n.get("type")=="action"]
    warnings=["Dry run performs no external side effects."]
    if workflow.requires_approval: warnings.append("Workflow requires a separate approved execution request.")
    row=AutomationDryRun(workflow_version_id=version.id,property_id=workflow.property_id,status="failed" if errors else "passed",warnings_count=len(errors)+len(warnings),execution_path=json.dumps({"nodes":len(graph.get("nodes",[])),"edges":len(graph.get("edges",[])),"actions":actions,"warnings":warnings,"errors":errors},separators=(",",":")),eligible_for_execution=not errors and not workflow.requires_approval)
    db.add(row);db.commit();db.refresh(row);return row
@router.get("/runs")
def runs(db:Session=Depends(get_db),user=Depends(reader)):
    q=db.query(AutomationWorkflowRun);allowed=_authorized_property_ids(db,user)
    if allowed is not None:q=q.filter(AutomationWorkflowRun.property_id.in_(allowed))
    return {"items":q.order_by(AutomationWorkflowRun.created_at.desc()).limit(100).all()}
@router.get("/runs/{run_id}")
def run_detail(run_id:UUID,db:Session=Depends(get_db),user=Depends(reader)):
    row=db.get(AutomationWorkflowRun,run_id)
    if not row: raise HTTPException(404,"Workflow run not found")
    _assert_workflow_access(db,user,db.get(AutomationWorkflow,row.workflow_id))
    return row
@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id:UUID,db:Session=Depends(get_db),user=Depends(admin)):
    row=db.get(AutomationWorkflowRun,run_id)
    if not row: raise HTTPException(404,"Workflow run not found")
    if row.status not in {"pending","running","retry_pending"}: raise HTTPException(409,"Only active workflow runs can be cancelled")
    row.status="cancelled";create_audit_log(db,user.username,"AUTOMATION_RUN_CANCELLED","AutomationWorkflowRun",str(row.id),"Cancelled active workflow run");db.commit();return {"status":row.status}
@router.get("/runs/{run_id}/steps")
def run_steps(run_id:UUID,db:Session=Depends(get_db),user=Depends(reader)):
    run=db.get(AutomationWorkflowRun,run_id)
    if not run: raise HTTPException(404,"Workflow run not found")
    _assert_workflow_access(db,user,db.get(AutomationWorkflow,run.workflow_id));return {"items":db.query(AutomationStepRun).filter_by(workflow_run_id=run_id).order_by(AutomationStepRun.started_at).all()}
@router.get("/approvals")
def approvals(status:str="pending",db:Session=Depends(get_db),user=Depends(reader)):
    q=db.query(AutomationApprovalRequest).join(AutomationWorkflowRun,AutomationWorkflowRun.id==AutomationApprovalRequest.workflow_run_id).filter(AutomationApprovalRequest.status==status);allowed=_authorized_property_ids(db,user)
    if allowed is not None:q=q.filter(AutomationWorkflowRun.property_id.in_(allowed))
    return {"items":q.order_by(AutomationApprovalRequest.created_at).limit(100).all()}
@router.post("/approvals/{approval_id}/decision")
def decide_approval(approval_id:UUID,p:ApprovalDecision,db:Session=Depends(get_db),user=Depends(admin)):
    row=db.get(AutomationApprovalRequest,approval_id)
    if not row: raise HTTPException(404,"Approval request not found")
    if row.status!="pending" or p.decision not in {"approved","rejected"}: raise HTTPException(409,"Invalid approval decision")
    run=db.get(AutomationWorkflowRun,row.workflow_run_id);sr=db.get(AutomationStepRun,row.step_run_id) if row.step_run_id else None
    if row.requested_by==user.username: raise HTTPException(409,"Requester cannot approve their own execution checkpoint")
    row.status=p.decision;row.reviewed_by=user.username;row.decision_reason=p.reason
    if sr: sr.status="completed" if p.decision=="approved" else "rejected";sr.completed_at=datetime.now(timezone.utc)
    if p.decision=="rejected": run.status="rejected"
    else: _execute_steps(db,run,db.get(AutomationWorkflowVersion,run.workflow_version_id),start_after=sr.step_id if sr else None)
    create_audit_log(db,user.username,"AUTOMATION_APPROVAL_DECIDED","AutomationApprovalRequest",str(row.id),f"Workflow approval {p.decision}");db.commit();_publish("automation_approval_decided",approval_id=row.id,run_id=run.id,status=row.status);return {"status":row.status,"run_status":run.status}
@router.post("/runs/{run_id}/retry",status_code=202)
def retry_run(run_id:UUID,db:Session=Depends(get_db),user=Depends(admin)):
    source=db.get(AutomationWorkflowRun,run_id)
    if not source: raise HTTPException(404,"Workflow run not found")
    if source.status not in {"failed","cancelled","rejected"}: raise HTTPException(409,"Only failed, cancelled, or rejected runs can be retried")
    row=AutomationWorkflowRun(property_id=source.property_id,workflow_id=source.workflow_id,workflow_version_id=source.workflow_version_id,status="pending",trigger_type="retry",triggered_by=user.username,idempotency_key=f"retry:{source.id}:{datetime.now(timezone.utc).isoformat()}");db.add(row);db.flush();_execute_steps(db,row,db.get(AutomationWorkflowVersion,row.workflow_version_id));create_audit_log(db,user.username,"AUTOMATION_RUN_RETRIED","AutomationWorkflowRun",str(row.id),f"Retried workflow run {source.id}");db.commit();_publish("automation_run_retried",run_id=row.id,source_run_id=source.id,status=row.status);return {"run_id":row.id,"status":row.status}
@router.post("/workflows/{workflow_id}/run",status_code=202)
def run_workflow(workflow_id:UUID,p:RunWrite,db:Session=Depends(get_db),user=Depends(admin)):
    workflow=db.get(AutomationWorkflow,workflow_id)
    if not workflow: raise HTTPException(404,"Workflow not found")
    version=db.get(AutomationWorkflowVersion,workflow.current_version_id) if workflow.current_version_id else None
    if not version or version.status!="approved": raise HTTPException(409,"No approved workflow version")
    persisted_steps=db.query(AutomationWorkflowStep).filter_by(workflow_version_id=version.id,enabled=True).count()
    if not p.dry_run and not persisted_steps:
        if not workflow.enabled: raise HTTPException(409,"Workflow is disabled")
        try: result=execute_graph(json.loads(version.workflow_graph or "{}"))
        except (ValueError,json.JSONDecodeError) as exc: raise HTTPException(409,str(exc))
    else: result={"executed":[],"side_effects":False}
    if p.idempotency_key:
        existing=db.query(AutomationWorkflowRun).filter_by(idempotency_key=p.idempotency_key).first()
        if existing: return {"run_id":existing.id,"status":existing.status,"replayed":True}
    row=AutomationWorkflowRun(property_id=workflow.property_id,workflow_id=workflow.id,workflow_version_id=version.id,status="completed" if p.dry_run or not persisted_steps else "pending",trigger_type="manual",triggered_by=user.username,idempotency_key=p.idempotency_key,error_summary=json.dumps(result,separators=(",",":")))
    db.add(row);db.flush()
    if not p.dry_run and persisted_steps:_execute_steps(db,row,version)
    create_audit_log(db,user.username,"AUTOMATION_RUN_COMPLETED" if row.status=="completed" else "AUTOMATION_RUN_STARTED","AutomationWorkflowRun",str(row.id),f"Processed {'dry' if p.dry_run else 'approved safe'} workflow run");db.commit();db.refresh(row);_publish("automation_run_completed" if row.status=="completed" else "automation_run_started",run_id=row.id,workflow_id=workflow.id,status=row.status);notify_automation(db,"HIOP automation run update",f"Workflow run {row.id} is {row.status}.");return {"run_id":row.id,"status":row.status,"dry_run":p.dry_run,"result":result,"replayed":False}
