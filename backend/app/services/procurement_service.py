from datetime import date,datetime,timezone
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import func,or_,select,text
from sqlalchemy.exc import IntegrityError
from app.models.asset_intelligence import ManagedAsset
from app.models.asset_management import Vendor
from app.models.hierarchy import Department
from app.models.procurement import AssetProcurement,ProcurementAssetLink,ProcurementEvent,ProcurementLineItem
from app.models.user import User
from app.services.audit_service import create_audit_log

def _number(db):return f"PO-{int(db.scalar(text("SELECT nextval('asset_procurement_number_seq')"))):06d}"
def _event(db,row,actor,action,previous,notes=None):db.add(ProcurementEvent(procurement_id=row.id,organization_id=row.organization_id,action=action,previous_status=previous,new_status=row.status,actor_id=str(actor.id),actor_name=actor.username,notes=notes));create_audit_log(db,actor.username,f"PROCUREMENT_{action.upper()}","AssetProcurement",str(row.id),f"{row.procurement_number}: {previous or 'new'} -> {row.status}")
def _items(db,row):return db.scalars(select(ProcurementLineItem).where(ProcurementLineItem.procurement_id==row.id).order_by(ProcurementLineItem.id)).all()
def present(db,row,detail=False):
    items=_items(db,row);links=db.execute(select(ProcurementAssetLink,ManagedAsset).join(ManagedAsset,ManagedAsset.id==ProcurementAssetLink.asset_id).where(ProcurementAssetLink.procurement_id==row.id)).all();requester=db.get(User,row.requested_by);approver=db.get(User,row.approved_by) if row.approved_by else None;department=db.get(Department,row.department_id) if row.department_id else None
    requested=sum(x.quantity_requested for x in items);received=sum(x.quantity_received for x in items);total=sum((Decimal(x.unit_cost)*x.quantity_requested for x in items),Decimal("0"));overdue=bool(row.expected_delivery_date and row.expected_delivery_date<date.today() and row.status not in {"received","cancelled"});vendor=db.get(Vendor,row.vendor_id) if row.vendor_id else None
    return {"id":row.id,"procurement_number":row.procurement_number,"reference_number":row.reference_number,"title":row.title,"description":row.description,"status":row.status,"requested_date":row.requested_date,"approved_date":row.approved_date,"ordered_date":row.ordered_date,"expected_delivery_date":row.expected_delivery_date,"received_date":row.received_date,"department_id":row.department_id,"department":department.name if department else None,"vendor":{"id":vendor.id,"vendor_id":vendor.vendor_number,"name":vendor.legal_name,"status":vendor.status} if vendor else None,"requested_by":row.requested_by,"requested_by_name":requester.username if requester else "Unknown","approved_by":row.approved_by,"approved_by_name":approver.username if approver else None,"currency":row.currency,"notes":row.notes,"quantity_requested":requested,"quantity_received":received,"outstanding":requested-received,"total_cost":total,"overdue":overdue,"items":[{"id":x.id,"description":x.description,"device_type":x.device_type,"quantity_requested":x.quantity_requested,"quantity_received":x.quantity_received,"outstanding":x.quantity_requested-x.quantity_received,"unit_cost":x.unit_cost,"line_total":Decimal(x.unit_cost)*x.quantity_requested} for x in items],"linked_assets":[{"id":asset.id,"asset_number":asset.asset_number,"asset_tag":asset.asset_tag,"name":asset.name,"line_item_id":link.line_item_id} for link,asset in links],"history":db.scalars(select(ProcurementEvent).where(ProcurementEvent.procurement_id==row.id).order_by(ProcurementEvent.created_at.desc())).all() if detail else [],"created_at":row.created_at,"updated_at":row.updated_at}
def create(db,payload,actor,organization_id):
    if payload.vendor_id:
        vendor=db.scalar(select(Vendor).where(Vendor.id==payload.vendor_id,Vendor.organization_id==organization_id,Vendor.status=="active"))
        if not vendor:raise HTTPException(422,"Select an active vendor from this organization")
    row=AssetProcurement(id=__import__('uuid').uuid4(),organization_id=organization_id,procurement_number=_number(db),title=payload.title.strip(),description=payload.description,reference_number=payload.reference_number,department_id=payload.department_id,vendor_id=payload.vendor_id,requested_by=str(actor.id),currency=payload.currency,expected_delivery_date=payload.expected_delivery_date,notes=payload.notes);db.add(row);db.flush()
    for item in payload.items:db.add(ProcurementLineItem(procurement_id=row.id,**item.model_dump()))
    _event(db,row,actor,"created",None);db.commit();db.refresh(row);return row
def transition(db,row,target,actor,notes=None,**values):
    allowed={"draft":{"requested","cancelled"},"requested":{"approved","cancelled"},"approved":{"ordered","cancelled"},"ordered":{"partially_received","received","cancelled"},"partially_received":{"partially_received","received","cancelled"}}
    if target not in allowed.get(row.status,set()):raise HTTPException(422,f"Cannot move procurement from {row.status} to {target}")
    previous=row.status;row.status=target;today=date.today()
    if target=="requested":row.requested_date=today
    elif target=="approved":row.approved_date=today;row.approved_by=str(actor.id)
    elif target=="ordered":row.ordered_date=today;row.reference_number=values.get("reference_number") or row.reference_number;row.expected_delivery_date=values.get("expected_delivery_date") or row.expected_delivery_date
    elif target=="received":row.received_date=today
    row.updated_at=datetime.now(timezone.utc);_event(db,row,actor,target,previous,notes);db.commit();db.refresh(row);return row
def receive(db,row,item_id,quantity,actor,notes=None):
    if row.status not in {"ordered","partially_received"}:raise HTTPException(422,"Only ordered procurement can be received")
    item=db.scalar(select(ProcurementLineItem).where(ProcurementLineItem.id==item_id,ProcurementLineItem.procurement_id==row.id))
    if not item:raise HTTPException(404,"Procurement item not found")
    if item.quantity_received+quantity>item.quantity_requested:raise HTTPException(422,"Received quantity cannot exceed requested quantity")
    item.quantity_received+=quantity;items=_items(db,row);complete=all(x.quantity_received==x.quantity_requested for x in items);target="received" if complete else "partially_received";return transition(db,row,target,actor,notes)
def link_asset(db,row,asset_id,item_id,actor):
    asset=db.scalar(select(ManagedAsset).where(ManagedAsset.id==asset_id,ManagedAsset.organization_id==row.organization_id))
    if not asset:raise HTTPException(404,"Managed asset not found")
    if item_id and not db.scalar(select(ProcurementLineItem.id).where(ProcurementLineItem.id==item_id,ProcurementLineItem.procurement_id==row.id)):raise HTTPException(404,"Procurement item not found")
    db.add(ProcurementAssetLink(procurement_id=row.id,line_item_id=item_id,asset_id=asset.id,linked_by=str(actor.id)))
    try:_event(db,row,actor,"asset_linked",row.status,f"Linked {asset.asset_number}");db.commit()
    except IntegrityError as exc:db.rollback();raise HTTPException(409,"Asset is already linked to a procurement record") from exc
    return row
