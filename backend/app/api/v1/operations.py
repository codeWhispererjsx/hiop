from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.core.security import get_db, get_current_user, require_roles
from app.models.hierarchy import Property
from app.models.hospitality_operations import HospitalityAssetCategory, HospitalityAssetType, HospitalityTechnologyService
from app.models.property_access import UserPropertyAccess

router=APIRouter(tags=["Hospitality operations"]); reader=require_roles(["admin","technician","viewer"]); admin=require_roles(["admin"])
class CategoryWrite(BaseModel): name:str=Field(min_length=1,max_length=120); code:str=Field(min_length=1,max_length=40); description:str|None=None; criticality_default:str="medium"
class TypeWrite(BaseModel): category_id:UUID; name:str; code:str; default_device_type:str|None=None; default_criticality:str="medium"
class ServiceWrite(BaseModel): property_id:UUID; name:str; code:str; service_category:str; criticality:str="medium"; status:str="unknown"; description:str|None=None
def scope(db,user,pid):
    p=db.get(Property,pid)
    if not p or p.operational_status!="active": raise HTTPException(404,"Property not found")
    if user.role not in {"admin","superadmin"} and not db.query(UserPropertyAccess).filter_by(user_id=user.id,property_id=pid,enabled=True).first(): raise HTTPException(403,"Property is not authorized")
    return p
@router.get("/hospitality/asset-categories")
def categories(db:Session=Depends(get_db),_=Depends(reader)): return db.query(HospitalityAssetCategory).filter_by(enabled=True).order_by(HospitalityAssetCategory.sort_order).all()
@router.post("/hospitality/asset-categories",status_code=201)
def create_category(p:CategoryWrite,db:Session=Depends(get_db),_=Depends(admin)): row=HospitalityAssetCategory(**p.model_dump());db.add(row);db.commit();db.refresh(row);return row
@router.get("/hospitality/asset-types")
def types(category_id:UUID|None=None,db:Session=Depends(get_db),_=Depends(reader)):
    q=db.query(HospitalityAssetType).filter_by(enabled=True)
    return q.filter(HospitalityAssetType.category_id==category_id).all() if category_id else q.all()
@router.post("/hospitality/asset-types",status_code=201)
def create_type(p:TypeWrite,db:Session=Depends(get_db),_=Depends(admin)): row=HospitalityAssetType(**p.model_dump());db.add(row);db.commit();db.refresh(row);return row
@router.get("/hospitality/technology-services")
def services(property_id:UUID,db:Session=Depends(get_db),user=Depends(reader)): scope(db,user,property_id); return db.query(HospitalityTechnologyService).filter_by(property_id=property_id).order_by(HospitalityTechnologyService.name).all()
@router.post("/hospitality/technology-services",status_code=201)
def create_service(p:ServiceWrite,db:Session=Depends(get_db),user=Depends(admin)): scope(db,user,p.property_id); row=HospitalityTechnologyService(**p.model_dump());db.add(row);db.commit();db.refresh(row);return row
@router.get("/properties/{property_id}/operations-summary")
def operations_summary(property_id:UUID,db:Session=Depends(get_db),user=Depends(reader)):
    p=scope(db,user,property_id); return {"property":{"id":str(p.id),"name":p.name,"code":p.code,"operational_status":p.operational_status},"overall_status":"unknown","health_score":None,"data_quality":"unknown","critical_alerts":0,"open_critical_tickets":0,"services":db.query(HospitalityTechnologyService).filter_by(property_id=property_id).count()}
@router.get("/properties/{property_id}/operations-dashboard")
def operations_dashboard(property_id:UUID,db:Session=Depends(get_db),user=Depends(reader)):
    summary=operations_summary(property_id,db,user); summary.update({"devices_by_status":{},"assets_by_category":{},"guest_facing_systems":[],"revenue_affecting_systems":[],"security_systems":[],"last_updated":None}); return summary
