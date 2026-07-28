from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.security import get_db,require_roles
from app.models.automation import AutomationWorkflow,AutomationWorkflowVersion,AutomationAction,AutomationDryRun,AutomationWorkflowRun
router=APIRouter(prefix="/automation",tags=["Automation"]); reader=require_roles(["admin","technician","viewer"]); admin=require_roles(["admin"])
class WorkflowWrite(BaseModel): property_id:UUID|None=None; name:str; code:str; workflow_category:str="custom"
@router.get("/workflows")
def workflows(db:Session=Depends(get_db),_=Depends(reader)): return {"items":db.query(AutomationWorkflow).order_by(AutomationWorkflow.name).limit(100).all()}
@router.post("/workflows",status_code=201)
def create_workflow(p:WorkflowWrite,db:Session=Depends(get_db),user=Depends(admin)): row=AutomationWorkflow(**p.model_dump(),created_by=user.username);db.add(row);db.commit();db.refresh(row);return row
@router.get("/actions")
def actions(db:Session=Depends(get_db),_=Depends(reader)): return {"items":db.query(AutomationAction).filter_by(enabled=True).all()}
@router.post("/workflows/{workflow_id}/dry-run")
def dry_run(workflow_id:UUID,db:Session=Depends(get_db),_=Depends(admin)):
    workflow=db.get(AutomationWorkflow,workflow_id)
    if not workflow: raise HTTPException(404,"Workflow not found")
    version=db.query(AutomationWorkflowVersion).filter_by(workflow_id=workflow.id,status="approved").first()
    if not version: raise HTTPException(409,"No approved workflow version")
    row=AutomationDryRun(workflow_version_id=version.id,property_id=workflow.property_id,execution_path="manual workflow execution is not enabled in this foundation",eligible_for_execution=False);db.add(row);db.commit();db.refresh(row);return row
@router.get("/runs")
def runs(db:Session=Depends(get_db),_=Depends(reader)): return {"items":db.query(AutomationWorkflowRun).order_by(AutomationWorkflowRun.created_at.desc()).limit(100).all()}
