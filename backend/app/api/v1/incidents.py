from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.security import get_db,require_roles
from app.models.incidents import OperationalIncident,IncidentTimelineEntry,IncidentTask,OperationalIncidentSource,IncidentParticipant
router=APIRouter(prefix="/incidents",tags=["Incidents"]); reader=require_roles(["admin","technician","viewer"]); admin=require_roles(["admin","technician"])
ALLOWED={"detected":{"declared","cancelled"},"declared":{"acknowledged","cancelled"},"acknowledged":{"investigating","cancelled"},"investigating":{"contained","mitigating","monitoring"},"contained":{"mitigating","monitoring"},"mitigating":{"monitoring","recovered"},"monitoring":{"recovered","resolved"},"recovered":{"resolved"},"resolved":{"closed","monitoring"}}
class IncidentWrite(BaseModel): property_id:UUID; title:str; description:str|None=None; incident_type:str="unknown"; severity:str="medium"; priority:str="P3"
class TaskWrite(BaseModel): title:str; assigned_user_id:str|None=None
class TimelineWrite(BaseModel): entry_type:str="note"; title:str; summary:str|None=None
class ParticipantWrite(BaseModel): user_id:str; participant_role:str="responder"
class SourceWrite(BaseModel): source_type:str; source_entity_id:UUID|None=None; relationship_type:str="related"
class TaskStatusWrite(BaseModel): status:str; output_summary:str|None=None
@router.get("")
def list_incidents(db:Session=Depends(get_db),_=Depends(reader)): return {"items":db.query(OperationalIncident).order_by(OperationalIncident.created_at.desc()).limit(100).all()}
@router.post("",status_code=201)
def create_incident(p:IncidentWrite,db:Session=Depends(get_db),user=Depends(admin)):
    row=OperationalIncident(**p.model_dump(),incident_number=f"INC-{__import__('secrets').token_hex(4).upper()}",created_by=user.username);db.add(row);db.flush();db.add(IncidentTimelineEntry(incident_id=row.id,entry_type="incident_created",title="Incident declared",actor_user_id=user.username));db.commit();db.refresh(row);return row
@router.get("/{incident_id}")
def get_incident(incident_id:UUID,db:Session=Depends(get_db),_=Depends(reader)):
    row=db.get(OperationalIncident,incident_id)
    if not row: raise HTTPException(404,"Incident not found")
    return row
@router.post("/{incident_id}/status")
def change_status(incident_id:UUID,status_value:str,db:Session=Depends(get_db),user=Depends(admin)):
    row=db.get(OperationalIncident,incident_id)
    if not row: raise HTTPException(404,"Incident not found")
    if status_value not in ALLOWED.get(row.status,set()): raise HTTPException(409,"Invalid incident status transition")
    row.status=status_value;db.add(IncidentTimelineEntry(incident_id=row.id,entry_type="status_changed",title=f"Status changed to {status_value}",actor_user_id=user.username));db.commit();return {"status":status_value}
@router.get("/{incident_id}/timeline")
def timeline(incident_id:UUID,db:Session=Depends(get_db),_=Depends(reader)): return {"items":db.query(IncidentTimelineEntry).filter_by(incident_id=incident_id).order_by(IncidentTimelineEntry.occurred_at).limit(200).all()}
@router.post("/{incident_id}/timeline",status_code=201)
def add_timeline(incident_id:UUID,p:TimelineWrite,db:Session=Depends(get_db),user=Depends(admin)):
    if not db.get(OperationalIncident,incident_id): raise HTTPException(404,"Incident not found")
    row=IncidentTimelineEntry(incident_id=incident_id,**p.model_dump(),actor_user_id=user.username);db.add(row);db.commit();db.refresh(row);return row
@router.get("/{incident_id}/tasks")
def tasks(incident_id:UUID,db:Session=Depends(get_db),_=Depends(reader)): return {"items":db.query(IncidentTask).filter_by(incident_id=incident_id).limit(100).all()}
@router.post("/{incident_id}/tasks",status_code=201)
def create_task(incident_id:UUID,p:TaskWrite,db:Session=Depends(get_db),user=Depends(admin)): row=IncidentTask(incident_id=incident_id,**p.model_dump());db.add(row);db.commit();db.refresh(row);return row
@router.post("/{incident_id}/participants",status_code=201)
def add_participant(incident_id:UUID,p:ParticipantWrite,db:Session=Depends(get_db),user=Depends(admin)):
    if not db.get(OperationalIncident,incident_id): raise HTTPException(404,"Incident not found")
    row=IncidentParticipant(incident_id=incident_id,**p.model_dump());db.add(row);db.commit();db.refresh(row);return row
@router.get("/{incident_id}/participants")
def participants(incident_id:UUID,db:Session=Depends(get_db),_=Depends(reader)): return {"items":db.query(IncidentParticipant).filter_by(incident_id=incident_id,active=True).limit(100).all()}
@router.post("/{incident_id}/sources",status_code=201)
def add_source(incident_id:UUID,p:SourceWrite,db:Session=Depends(get_db),user=Depends(admin)):
    if not db.get(OperationalIncident,incident_id): raise HTTPException(404,"Incident not found")
    row=OperationalIncidentSource(incident_id=incident_id,**p.model_dump());db.add(row);db.commit();db.refresh(row);return row
@router.get("/{incident_id}/sources")
def sources(incident_id:UUID,db:Session=Depends(get_db),_=Depends(reader)): return {"items":db.query(OperationalIncidentSource).filter_by(incident_id=incident_id).limit(100).all()}
@router.patch("/{incident_id}/tasks/{task_id}")
def update_task(incident_id:UUID,task_id:UUID,p:TaskStatusWrite,db:Session=Depends(get_db),user=Depends(admin)):
    row=db.query(IncidentTask).filter_by(id=task_id,incident_id=incident_id).first()
    if not row: raise HTTPException(404,"Task not found")
    if p.status not in {"open","in_progress","blocked","completed","cancelled"}: raise HTTPException(422,"Invalid task status")
    row.status=p.status;row.output_summary=p.output_summary;db.commit();db.refresh(row);return row
