from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.security import get_db, require_roles
from app.models.configuration_restore import ConfigurationChangeRequest,ConfigurationChangeWindow,ConfigurationRestorePlan,ConfigurationRestoreDryRun
router=APIRouter(prefix="/configuration-management",tags=["Configuration restore workflow"]); reader=require_roles(["admin","technician","viewer"]); admin=require_roles(["admin"])
class ChangeWrite(BaseModel): property_id:UUID; title:str; business_reason:str; description:str|None=None
class WindowWrite(BaseModel): property_id:UUID; name:str; start_at:str; end_at:str; timezone:str="UTC"
@router.get("/change-requests")
def changes(db:Session=Depends(get_db),_=Depends(reader)): return {"items":db.query(ConfigurationChangeRequest).order_by(ConfigurationChangeRequest.created_at.desc()).limit(100).all()}
@router.post("/change-requests",status_code=201)
def create_change(p:ChangeWrite,db:Session=Depends(get_db),user=Depends(admin)): row=ConfigurationChangeRequest(**p.model_dump(),requested_by=user.username);db.add(row);db.commit();db.refresh(row);return row
@router.post("/change-requests/{change_id}/submit")
def submit(change_id:UUID,db:Session=Depends(get_db),_=Depends(admin)):
    row=db.get(ConfigurationChangeRequest,change_id)
    if not row: raise HTTPException(404,"Change request not found")
    row.status="submitted";db.commit();return {"status":row.status}
@router.post("/change-requests/{change_id}/approve")
def approve(change_id:UUID,db:Session=Depends(get_db),user=Depends(admin)):
    row=db.get(ConfigurationChangeRequest,change_id)
    if not row: raise HTTPException(404,"Change request not found")
    if row.requested_by==user.username: raise HTTPException(403,"Requester cannot approve own change")
    row.status="approved";row.approved_by=user.username;db.commit();return {"status":row.status}
@router.get("/change-windows")
def windows(db:Session=Depends(get_db),_=Depends(reader)): return {"items":db.query(ConfigurationChangeWindow).order_by(ConfigurationChangeWindow.start_at).limit(100).all()}
@router.post("/change-windows",status_code=201)
def create_window(p:WindowWrite,db:Session=Depends(get_db),_=Depends(admin)): row=ConfigurationChangeWindow(property_id=p.property_id,name=p.name,start_at=p.start_at,end_at=p.end_at,timezone=p.timezone);db.add(row);db.commit();db.refresh(row);return row
@router.get("/restore-plans")
def plans(db:Session=Depends(get_db),_=Depends(reader)): return {"items":db.query(ConfigurationRestorePlan).order_by(ConfigurationRestorePlan.created_at.desc()).limit(100).all()}
@router.post("/restore-plans/{plan_id}/dry-run")
def dry_run(plan_id:UUID,db:Session=Depends(get_db),_=Depends(admin)):
    plan=db.get(ConfigurationRestorePlan,plan_id)
    if not plan: raise HTTPException(404,"Restore plan not found")
    row=ConfigurationRestoreDryRun(restore_plan_id=plan.id,status="failed",safe_results="No restore adapter is enabled; dry run is blocked safely.");db.add(row);db.commit();db.refresh(row);return row
