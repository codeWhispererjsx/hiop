from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.core.tenant import organization_context, property_context
from app.models.asset_intelligence import ManagedAsset
from app.schemas.asset_intelligence import AssetCreate, AssetResponse, AssetUpdate, LifecycleEventResponse, LifecycleTransition
from app.services.asset_intelligence_service import create_asset, list_assets, present, transition_asset, update_asset
from app.services.billing_service import enforce_limit

router=APIRouter(prefix="/assets",tags=["V4A Asset Intelligence"])
reader=require_roles(["platformadmin","admin","technician","viewer"])
writer=require_roles(["admin"])
lifecycle_writer=require_roles(["admin","technician"])


def require_asset(db,asset_id,organization_id):
    row=db.query(ManagedAsset).filter(ManagedAsset.id==asset_id,ManagedAsset.organization_id==organization_id).first()
    if not row: raise HTTPException(404,"Managed asset not found")
    return row


@router.get("",response_model=list[AssetResponse])
def assets(search:str|None=Query(None,max_length=180),status:str|None=None,device_type:str|None=None,department:str|None=None,location:str|None=None,health:str|None=None,vendor:str|None=None,db:Session=Depends(get_db),_=Depends(reader),organization_id=Depends(organization_context),property_id=Depends(property_context)):
    return list_assets(db,search,status,device_type,department,location,health,vendor,organization_id,property_id)


@router.post("",response_model=AssetResponse,status_code=201)
def add_asset(payload:AssetCreate,db:Session=Depends(get_db),actor=Depends(writer),organization_id=Depends(organization_context),property_id=Depends(property_context)):
    enforce_limit(db,organization_id,"assets")
    return present(db,create_asset(db,payload,actor,organization_id,property_id),True)


@router.get("/device/{device_id}",response_model=AssetResponse)
def device_asset(device_id:UUID,db:Session=Depends(get_db),_=Depends(reader),organization_id=Depends(organization_context)):
    row=db.query(ManagedAsset).filter_by(device_id=device_id,organization_id=organization_id).first()
    if not row: raise HTTPException(404,"Managed asset not found for device")
    return present(db,row,True)


@router.get("/{asset_id}",response_model=AssetResponse)
def asset(asset_id:UUID,db:Session=Depends(get_db),_=Depends(reader),organization_id=Depends(organization_context)):
    return present(db,require_asset(db,asset_id,organization_id),True)


@router.put("/{asset_id}",response_model=AssetResponse)
def edit_asset(asset_id:UUID,payload:AssetUpdate,db:Session=Depends(get_db),actor=Depends(writer),organization_id=Depends(organization_context)):
    return present(db,update_asset(db,require_asset(db,asset_id,organization_id),payload,actor),True)


@router.get("/{asset_id}/lifecycle",response_model=AssetResponse)
def lifecycle(asset_id:UUID,db:Session=Depends(get_db),_=Depends(reader),organization_id=Depends(organization_context)):
    return present(db,require_asset(db,asset_id,organization_id),True)


@router.get("/{asset_id}/lifecycle/history",response_model=list[LifecycleEventResponse])
def lifecycle_history(asset_id:UUID,db:Session=Depends(get_db),_=Depends(reader),organization_id=Depends(organization_context)):
    return present(db,require_asset(db,asset_id,organization_id),True)["lifecycle_history"]


@router.post("/{asset_id}/lifecycle",response_model=AssetResponse)
def change_lifecycle(asset_id:UUID,payload:LifecycleTransition,db:Session=Depends(get_db),actor=Depends(lifecycle_writer),organization_id=Depends(organization_context)):
    row=require_asset(db,asset_id,organization_id)
    if actor.role=="technician" and not ({row.status,payload.status}<={"active","in_maintenance"}):raise HTTPException(403,"Technicians may only manage maintenance transitions")
    return present(db,transition_asset(db,row,payload,actor),True)
