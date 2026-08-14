import json
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from app.models.asset_intelligence import ManagedAsset
from app.models.asset_management import Vendor, VendorContact
from app.models.procurement import AssetProcurement
from app.schemas.vendor_management import VendorCreate, VendorUpdate
from app.services.audit_service import create_audit_log

def _number(db):return f"VND-{int(db.scalar(text("SELECT nextval('operational_vendor_number_seq')"))):06d}"
def _services(row):
    try:return json.loads(row.products_services or "[]")
    except (TypeError,json.JSONDecodeError):return []
def require_vendor(db,vendor_id,organization_id):
    row=db.scalar(select(Vendor).where(Vendor.id==vendor_id,Vendor.organization_id==organization_id))
    if not row:raise HTTPException(404,"Vendor not found")
    return row
def _contact(db,row):return {"id":row.id,"vendor_id":row.vendor_id,"name":row.name,"role":row.role,"email":row.email,"phone":row.phone,"department":row.department,"primary":row.primary,"notes":row.notes,"updated_at":row.updated_at}
def present(db,row,detail=False):
    contacts=db.scalars(select(VendorContact).where(VendorContact.vendor_id==row.id).order_by(VendorContact.primary.desc(),VendorContact.name)).all()
    assets=db.scalars(select(ManagedAsset).where(ManagedAsset.vendor_id==row.id,ManagedAsset.organization_id==row.organization_id).order_by(ManagedAsset.asset_number)).all()
    procurement=db.scalars(select(AssetProcurement).where(AssetProcurement.vendor_id==row.id,AssetProcurement.organization_id==row.organization_id).order_by(AssetProcurement.created_at.desc())).all()
    return {"id":row.id,"vendor_id":row.vendor_number,"vendor_code":row.vendor_code,"name":row.legal_name,"vendor_type":row.vendor_type,"status":row.status,"description":row.description,"website":row.website,"primary_email":row.primary_email,"primary_phone":row.primary_phone,"address":row.address,"country":row.country,"notes":row.notes,"support_agreement_reference":row.support_agreement_reference,"renewal_date":row.renewal_date,"products_services":_services(row),"contact_count":len(contacts),"asset_count":len(assets),"procurement_count":len(procurement),"contacts":[_contact(db,x) for x in contacts] if detail else [],"assets":[{"id":x.id,"asset_number":x.asset_number,"asset_tag":x.asset_tag,"name":x.name,"status":x.status,"manufacturer":x.vendor} for x in assets] if detail else [],"procurement":[{"id":x.id,"procurement_number":x.procurement_number,"title":x.title,"status":x.status,"reference_number":x.reference_number} for x in procurement] if detail else [],"created_at":row.created_at,"updated_at":row.updated_at}
def list_vendors(db,organization_id,search=None,vendor_type=None,status=None):
    query=select(Vendor).where(Vendor.organization_id==organization_id)
    if vendor_type:query=query.where(Vendor.vendor_type==vendor_type)
    if status:query=query.where(Vendor.status==status)
    rows=db.scalars(query.order_by(Vendor.legal_name)).all()
    if search:
        needle=search.casefold();filtered=[]
        for row in rows:
            contacts=db.scalars(select(VendorContact).where(VendorContact.vendor_id==row.id)).all()
            values=[row.legal_name,row.vendor_number,row.vendor_code,*_services(row),*(x.name for x in contacts),*(x.email for x in contacts)]
            if any(needle in str(value).casefold() for value in values if value):filtered.append(row)
        rows=filtered
    return [present(db,row) for row in rows]
def create(db,payload:VendorCreate,actor,organization_id):
    exists=db.scalar(select(Vendor.id).where(Vendor.organization_id==organization_id,func.lower(Vendor.legal_name)==payload.name.strip().lower()))
    if exists:raise HTTPException(409,"A vendor with this name already exists")
    values=payload.model_dump(exclude={"name","products_services"});values["primary_email"]=str(values["primary_email"]) if values.get("primary_email") else None
    row=Vendor(vendor_number=_number(db),organization_id=organization_id,legal_name=payload.name.strip(),trading_name=None,products_services=json.dumps(payload.products_services),status="active",approved=True,created_by=str(actor.id),**values);db.add(row)
    try:db.flush();create_audit_log(db,actor.username,"VENDOR_CREATED","Vendor",str(row.id),f"{row.vendor_number} created for organization {organization_id}");db.commit();db.refresh(row)
    except IntegrityError as exc:db.rollback();raise HTTPException(409,"Vendor code or name already exists") from exc
    return row
def update(db,row,payload:VendorUpdate,actor):
    changes=[];values=payload.model_dump(exclude_unset=True)
    if "name" in values:values["legal_name"]=values.pop("name").strip()
    if "products_services" in values:values["products_services"]=json.dumps(values["products_services"] or [])
    if values.get("primary_email"):values["primary_email"]=str(values["primary_email"])
    for key,value in values.items():
        old=getattr(row,key)
        if old!=value:changes.append(f"{key}: {old or 'Unknown'} -> {value or 'Unknown'}");setattr(row,key,value)
    row.updated_at=datetime.now(timezone.utc)
    try:create_audit_log(db,actor.username,"VENDOR_UPDATED","Vendor",str(row.id),"; ".join(changes) or "No material changes");db.commit();db.refresh(row)
    except IntegrityError as exc:db.rollback();raise HTTPException(409,"Vendor code or name already exists") from exc
    return row
def set_status(db,row,status,actor):
    if row.status==status:return row
    row.status=status;row.updated_at=datetime.now(timezone.utc);create_audit_log(db,actor.username,f"VENDOR_{status.upper()}","Vendor",str(row.id),f"{row.vendor_number} marked {status}; historical relationships preserved");db.commit();db.refresh(row);return row
def add_contact(db,row,payload,actor):
    if payload.primary:db.query(VendorContact).filter(VendorContact.vendor_id==row.id).update({VendorContact.primary:False})
    contact=VendorContact(vendor_id=row.id,name=payload.name.strip(),role=payload.role,email=str(payload.email) if payload.email else None,phone=payload.phone,department=payload.department,primary=payload.primary,notes=payload.notes);db.add(contact);db.flush();create_audit_log(db,actor.username,"VENDOR_CONTACT_ADDED","Vendor",str(row.id),f"Added contact {contact.name} to {row.vendor_number}");db.commit();db.refresh(contact);return contact
def update_contact(db,row,contact_id,payload,actor):
    contact=db.scalar(select(VendorContact).where(VendorContact.id==contact_id,VendorContact.vendor_id==row.id))
    if not contact:raise HTTPException(404,"Vendor contact not found")
    if payload.primary:db.query(VendorContact).filter(VendorContact.vendor_id==row.id,VendorContact.id!=contact.id).update({VendorContact.primary:False})
    for key,value in payload.model_dump().items():setattr(contact,key,str(value) if key=="email" and value else value)
    contact.updated_at=datetime.now(timezone.utc);create_audit_log(db,actor.username,"VENDOR_CONTACT_UPDATED","Vendor",str(row.id),f"Updated contact {contact.name}");db.commit();db.refresh(contact);return contact
def link_asset(db,row,asset_id,actor):
    asset=db.scalar(select(ManagedAsset).where(ManagedAsset.id==asset_id,ManagedAsset.organization_id==row.organization_id))
    if not asset:raise HTTPException(404,"Managed asset not found")
    asset.vendor_id=row.id;asset.updated_by=str(actor.id);create_audit_log(db,actor.username,"VENDOR_LINKED_TO_ASSET","Vendor",str(row.id),f"Linked {row.vendor_number} to {asset.asset_number}");db.commit();return asset
def link_procurement(db,row,procurement_id,actor):
    if row.status!="active":raise HTTPException(422,"Inactive vendors cannot be selected for procurement")
    procurement=db.scalar(select(AssetProcurement).where(AssetProcurement.id==procurement_id,AssetProcurement.organization_id==row.organization_id))
    if not procurement:raise HTTPException(404,"Procurement record not found")
    procurement.vendor_id=row.id;create_audit_log(db,actor.username,"VENDOR_LINKED_TO_PROCUREMENT","Vendor",str(row.id),f"Linked {row.vendor_number} to {procurement.procurement_number}");db.commit();return procurement
