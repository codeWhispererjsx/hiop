from uuid import UUID
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.security import get_db, require_roles
from app.models.configuration_compliance import ConfigurationComplianceStandard, ConfigurationCompliancePolicy, ConfigurationComplianceRun, ConfigurationComplianceResult, ConfigurationComplianceViolation, ConfigurationComplianceException
router=APIRouter(prefix="/configuration-management/compliance",tags=["Configuration compliance"]); reader=require_roles(["admin","technician","viewer"]); admin=require_roles(["admin"])
class StandardWrite(BaseModel): name:str; code:str; version:str; standard_type:str="internal"; scope_type:str="property"; description:str|None=None
class PolicyWrite(BaseModel): standard_id:UUID; name:str; code:str; severity_default:str="medium"; evaluation_mode:str="manual_only"; property_id:UUID|None=None
def page(q): return {"items":q.limit(100).all(),"total":q.count()}
@router.get("/standards")
def standards(db:Session=Depends(get_db),_=Depends(reader)): return page(db.query(ConfigurationComplianceStandard).order_by(ConfigurationComplianceStandard.name))
@router.post("/standards",status_code=201)
def create_standard(p:StandardWrite,db:Session=Depends(get_db),_=Depends(admin)): row=ConfigurationComplianceStandard(**p.model_dump());db.add(row);db.commit();db.refresh(row);return row
@router.get("/policies")
def policies(db:Session=Depends(get_db),_=Depends(reader)): return page(db.query(ConfigurationCompliancePolicy).order_by(ConfigurationCompliancePolicy.name))
@router.post("/policies",status_code=201)
def create_policy(p:PolicyWrite,db:Session=Depends(get_db),_=Depends(admin)): row=ConfigurationCompliancePolicy(**p.model_dump());db.add(row);db.commit();db.refresh(row);return row
@router.get("/violations")
def violations(db:Session=Depends(get_db),_=Depends(reader)): return page(db.query(ConfigurationComplianceViolation).order_by(ConfigurationComplianceViolation.last_detected_at.desc()))
@router.get("/results")
def results(db:Session=Depends(get_db),_=Depends(reader)): return page(db.query(ConfigurationComplianceResult).order_by(ConfigurationComplianceResult.evaluated_at.desc()))
@router.post("/run",status_code=202)
def run(db:Session=Depends(get_db),user=Depends(admin)): row=ConfigurationComplianceRun(status="pending");db.add(row);db.commit();db.refresh(row);return {"run_id":str(row.id),"status":row.status,"warnings":["Evaluation worker is not enabled in this foundation build"]}
@router.get("/exceptions")
def exceptions(db:Session=Depends(get_db),_=Depends(reader)): return page(db.query(ConfigurationComplianceException).order_by(ConfigurationComplianceException.created_at.desc()))
