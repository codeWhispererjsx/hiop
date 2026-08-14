from datetime import date
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.core.security import get_db,require_roles
from app.core.tenant import organization_context
from app.models.procurement import AssetProcurement,ProcurementAssetLink
from app.models.asset_management import Vendor
from app.schemas.procurement import ProcurementAction,ProcurementAssetLinkCreate,ProcurementCreate,ProcurementOrder,ProcurementReceipt,ProcurementUpdate
from app.services import procurement_service as service
router=APIRouter(prefix="/procurement",tags=["V4C Procurement"]);reader=require_roles(["platformadmin","admin","technician","viewer"]);manager=require_roles(["admin"])
def record(db,id,org):
    row=db.query(AssetProcurement).filter(AssetProcurement.id==id,AssetProcurement.organization_id==org).first()
    if not row:raise HTTPException(404,"Procurement record not found")
    return row
@router.get("")
def list_records(search:str|None=Query(None,max_length=180),status:str|None=None,department_id:UUID|None=None,requested_by:str|None=None,currency:str|None=None,expected_before:date|None=None,db:Session=Depends(get_db),_=Depends(reader),org=Depends(organization_context)):
    q=db.query(AssetProcurement).filter(AssetProcurement.organization_id==org)
    if search:q=q.filter(or_(AssetProcurement.procurement_number.ilike(f"%{search}%"),AssetProcurement.reference_number.ilike(f"%{search}%"),AssetProcurement.title.ilike(f"%{search}%"),AssetProcurement.description.ilike(f"%{search}%")))
    if status:q=q.filter(AssetProcurement.status==status)
    if department_id:q=q.filter(AssetProcurement.department_id==department_id)
    if requested_by:q=q.filter(AssetProcurement.requested_by==requested_by)
    if currency:q=q.filter(AssetProcurement.currency==currency.upper())
    if expected_before:q=q.filter(AssetProcurement.expected_delivery_date<=expected_before)
    return [service.present(db,x) for x in q.order_by(AssetProcurement.created_at.desc()).all()]
@router.get("/summary")
def summary(db:Session=Depends(get_db),_=Depends(reader),org=Depends(organization_context)):
    rows=[service.present(db,x) for x in db.query(AssetProcurement).filter(AssetProcurement.organization_id==org).all()];currencies={x["currency"] for x in rows}
    return {"total":len(rows),**{s:sum(x["status"]==s for x in rows) for s in ("draft","requested","approved","ordered","partially_received","received","cancelled")},"overdue":sum(x["overdue"] for x in rows),"totals_by_currency":{code:str(sum((x["total_cost"] for x in rows if x["currency"]==code),0)) for code in currencies}}
@router.post("",status_code=201)
def create_record(payload:ProcurementCreate,db:Session=Depends(get_db),actor=Depends(manager),org=Depends(organization_context)):return service.present(db,service.create(db,payload,actor,org),True)
@router.get("/{record_id}")
def get_record(record_id:UUID,db:Session=Depends(get_db),_=Depends(reader),org=Depends(organization_context)):return service.present(db,record(db,record_id,org),True)
@router.patch("/{record_id}")
def update_record(record_id:UUID,payload:ProcurementUpdate,db:Session=Depends(get_db),actor=Depends(manager),org=Depends(organization_context)):
    row=record(db,record_id,org)
    if row.status!="draft":raise HTTPException(422,"Only draft procurement can be edited")
    if payload.vendor_id and not db.query(Vendor).filter(Vendor.id==payload.vendor_id,Vendor.organization_id==org,Vendor.status=="active").first():raise HTTPException(422,"Select an active vendor from this organization")
    for key,value in payload.model_dump(exclude_unset=True).items():setattr(row,key,value)
    service._event(db,row,actor,"updated",row.status);db.commit();return service.present(db,row,True)
@router.post("/{record_id}/request")
def request(record_id:UUID,payload:ProcurementAction,db:Session=Depends(get_db),actor=Depends(manager),org=Depends(organization_context)):return service.present(db,service.transition(db,record(db,record_id,org),"requested",actor,payload.notes),True)
@router.post("/{record_id}/approve")
def approve(record_id:UUID,payload:ProcurementAction,db:Session=Depends(get_db),actor=Depends(manager),org=Depends(organization_context)):return service.present(db,service.transition(db,record(db,record_id,org),"approved",actor,payload.notes),True)
@router.post("/{record_id}/order")
def order(record_id:UUID,payload:ProcurementOrder,db:Session=Depends(get_db),actor=Depends(manager),org=Depends(organization_context)):return service.present(db,service.transition(db,record(db,record_id,org),"ordered",actor,payload.notes,reference_number=payload.reference_number,expected_delivery_date=payload.expected_delivery_date),True)
@router.post("/{record_id}/receive")
def receive(record_id:UUID,payload:ProcurementReceipt,db:Session=Depends(get_db),actor=Depends(manager),org=Depends(organization_context)):return service.present(db,service.receive(db,record(db,record_id,org),payload.item_id,payload.quantity,actor,payload.notes),True)
@router.post("/{record_id}/cancel")
def cancel(record_id:UUID,payload:ProcurementAction,db:Session=Depends(get_db),actor=Depends(manager),org=Depends(organization_context)):return service.present(db,service.transition(db,record(db,record_id,org),"cancelled",actor,payload.notes),True)
@router.post("/{record_id}/assets")
def link(record_id:UUID,payload:ProcurementAssetLinkCreate,db:Session=Depends(get_db),actor=Depends(manager),org=Depends(organization_context)):return service.present(db,service.link_asset(db,record(db,record_id,org),payload.asset_id,payload.item_id,actor),True)
@router.delete("/{record_id}/assets/{asset_id}",status_code=204)
def unlink(record_id:UUID,asset_id:UUID,db:Session=Depends(get_db),actor=Depends(manager),org=Depends(organization_context)):
    row=record(db,record_id,org);link=db.query(ProcurementAssetLink).filter_by(procurement_id=row.id,asset_id=asset_id).first()
    if not link:raise HTTPException(404,"Asset link not found")
    db.delete(link);service._event(db,row,actor,"asset_unlinked",row.status);db.commit()
