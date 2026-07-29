from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
import hashlib,json
from sqlalchemy.orm import Session
from app.core.security import get_db,require_roles
from app.models.automation import AutomationWorkflow,AutomationWorkflowVersion,AutomationAction,AutomationDryRun,AutomationWorkflowRun
from app.services.automation_validation_service import validate_graph
router=APIRouter(prefix="/automation",tags=["Automation"]); reader=require_roles(["admin","technician","viewer"]); admin=require_roles(["admin"])
class WorkflowWrite(BaseModel): property_id:UUID|None=None; name:str; code:str; workflow_category:str="custom"
class VersionWrite(BaseModel): trigger_definition:dict=Field(default_factory=dict); workflow_graph:dict=Field(default_factory=dict)
@router.get("/workflows")
def workflows(db:Session=Depends(get_db),_=Depends(reader)): return {"items":db.query(AutomationWorkflow).order_by(AutomationWorkflow.name).limit(100).all()}
@router.post("/workflows",status_code=201)
def create_workflow(p:WorkflowWrite,db:Session=Depends(get_db),user=Depends(admin)): row=AutomationWorkflow(**p.model_dump(),created_by=user.username);db.add(row);db.commit();db.refresh(row);return row
@router.get("/workflows/{workflow_id}/versions")
def versions(workflow_id:UUID,db:Session=Depends(get_db),_=Depends(reader)):
    if not db.get(AutomationWorkflow,workflow_id): raise HTTPException(404,"Workflow not found")
    return {"items":db.query(AutomationWorkflowVersion).filter_by(workflow_id=workflow_id).order_by(AutomationWorkflowVersion.version_number.desc()).limit(100).all()}
@router.post("/workflows/{workflow_id}/versions",status_code=201)
def create_version(workflow_id:UUID,p:VersionWrite,db:Session=Depends(get_db),user=Depends(admin)):
    workflow=db.get(AutomationWorkflow,workflow_id)
    if not workflow: raise HTTPException(404,"Workflow not found")
    number=(db.query(AutomationWorkflowVersion).filter_by(workflow_id=workflow_id).count()+1)
    graph=json.dumps(p.workflow_graph,separators=(",",":"),sort_keys=True); trigger=json.dumps(p.trigger_definition,separators=(",",":"),sort_keys=True)
    errors=validate_graph(p.workflow_graph,{a.action_key for a in db.query(AutomationAction).filter_by(enabled=True).all()})
    if errors: raise HTTPException(422,{"message":"Invalid workflow definition","errors":errors})
    if len(graph)>100000 or len(trigger)>20000: raise HTTPException(422,"Workflow definition exceeds safe size limits")
    checksum=hashlib.sha256((trigger+"\n"+graph).encode()).hexdigest()
    row=AutomationWorkflowVersion(workflow_id=workflow_id,version_number=number,trigger_definition=trigger,workflow_graph=graph,checksum=checksum,created_by=user.username)
    db.add(row);db.commit();db.refresh(row);return row
@router.post("/workflow-versions/{version_id}/validate")
def validate_version(version_id:UUID,db:Session=Depends(get_db),_=Depends(reader)):
    row=db.get(AutomationWorkflowVersion,version_id)
    if not row: raise HTTPException(404,"Workflow version not found")
    try: graph=json.loads(row.workflow_graph or "{}")
    except json.JSONDecodeError: return {"valid":False,"errors":["workflow graph is not valid JSON"]}
    errors=validate_graph(graph,{a.action_key for a in db.query(AutomationAction).filter_by(enabled=True).all()})
    return {"valid":not errors,"errors":errors,"checksum":row.checksum}
@router.post("/workflow-versions/{version_id}/approve")
def approve_version(version_id:UUID,db:Session=Depends(get_db),user=Depends(admin)):
    row=db.get(AutomationWorkflowVersion,version_id)
    if not row: raise HTTPException(404,"Workflow version not found")
    if row.status not in {"draft","rejected"}: raise HTTPException(409,"Only draft or rejected versions can be approved")
    workflow=db.get(AutomationWorkflow,row.workflow_id)
    if workflow.requires_approval and row.created_by==user.username: raise HTTPException(409,"Requester cannot approve their own version")
    row.status="approved";row.approved_by=user.username;workflow.current_version_id=row.id;workflow.status="approved";db.commit();db.refresh(row);return row
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
    errors=validate_graph(graph,{a.action_key for a in db.query(AutomationAction).filter_by(enabled=True).all()})
    actions=[n.get("action_key") for n in graph.get("nodes",[]) if isinstance(n,dict) and n.get("type")=="action"]
    warnings=["Dry run performs no external side effects."]
    if workflow.requires_approval: warnings.append("Workflow requires a separate approved execution request.")
    row=AutomationDryRun(workflow_version_id=version.id,property_id=workflow.property_id,status="failed" if errors else "passed",warnings_count=len(errors)+len(warnings),execution_path=json.dumps({"nodes":len(graph.get("nodes",[])),"edges":len(graph.get("edges",[])),"actions":actions,"warnings":warnings,"errors":errors},separators=(",",":")),eligible_for_execution=not errors and not workflow.requires_approval)
    db.add(row);db.commit();db.refresh(row);return row
@router.get("/runs")
def runs(db:Session=Depends(get_db),_=Depends(reader)): return {"items":db.query(AutomationWorkflowRun).order_by(AutomationWorkflowRun.created_at.desc()).limit(100).all()}
