from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.security import get_db, require_roles
from app.core.tenant import organization_context
from app.schemas.vendor_management import VendorContactCreate, VendorContactUpdate, VendorCreate, VendorUpdate
from app.services import vendor_management_service as service

router=APIRouter(prefix="/vendors",tags=["V4D Vendor Management"])
reader=require_roles(["platformadmin","admin","technician","viewer"])
manager=require_roles(["admin"])

@router.get("")
def vendors(search:str|None=Query(None,max_length=180),vendor_type:str|None=None,status:str|None=None,db:Session=Depends(get_db),_=Depends(reader),organization_id=Depends(organization_context)):
    return service.list_vendors(db,organization_id,search,vendor_type,status)
@router.post("",status_code=201)
def create_vendor(payload:VendorCreate,db:Session=Depends(get_db),actor=Depends(manager),organization_id=Depends(organization_context)):
    return service.present(db,service.create(db,payload,actor,organization_id),True)
@router.get("/{vendor_id}")
def vendor(vendor_id:UUID,db:Session=Depends(get_db),_=Depends(reader),organization_id=Depends(organization_context)):
    return service.present(db,service.require_vendor(db,vendor_id,organization_id),True)
@router.patch("/{vendor_id}")
def update_vendor(vendor_id:UUID,payload:VendorUpdate,db:Session=Depends(get_db),actor=Depends(manager),organization_id=Depends(organization_context)):
    return service.present(db,service.update(db,service.require_vendor(db,vendor_id,organization_id),payload,actor),True)
@router.post("/{vendor_id}/activate")
def activate_vendor(vendor_id:UUID,db:Session=Depends(get_db),actor=Depends(manager),organization_id=Depends(organization_context)):
    return service.present(db,service.set_status(db,service.require_vendor(db,vendor_id,organization_id),"active",actor),True)
@router.post("/{vendor_id}/deactivate")
def deactivate_vendor(vendor_id:UUID,db:Session=Depends(get_db),actor=Depends(manager),organization_id=Depends(organization_context)):
    return service.present(db,service.set_status(db,service.require_vendor(db,vendor_id,organization_id),"inactive",actor),True)
@router.get("/{vendor_id}/contacts")
def contacts(vendor_id:UUID,db:Session=Depends(get_db),_=Depends(reader),organization_id=Depends(organization_context)):
    return service.present(db,service.require_vendor(db,vendor_id,organization_id),True)["contacts"]
@router.post("/{vendor_id}/contacts",status_code=201)
def add_contact(vendor_id:UUID,payload:VendorContactCreate,db:Session=Depends(get_db),actor=Depends(manager),organization_id=Depends(organization_context)):
    row=service.require_vendor(db,vendor_id,organization_id);return service._contact(db,service.add_contact(db,row,payload,actor))
@router.patch("/{vendor_id}/contacts/{contact_id}")
def edit_contact(vendor_id:UUID,contact_id:UUID,payload:VendorContactUpdate,db:Session=Depends(get_db),actor=Depends(manager),organization_id=Depends(organization_context)):
    row=service.require_vendor(db,vendor_id,organization_id);return service._contact(db,service.update_contact(db,row,contact_id,payload,actor))
@router.get("/{vendor_id}/assets")
def vendor_assets(vendor_id:UUID,db:Session=Depends(get_db),_=Depends(reader),organization_id=Depends(organization_context)):
    return service.present(db,service.require_vendor(db,vendor_id,organization_id),True)["assets"]
@router.post("/{vendor_id}/assets/{asset_id}")
def link_asset(vendor_id:UUID,asset_id:UUID,db:Session=Depends(get_db),actor=Depends(manager),organization_id=Depends(organization_context)):
    row=service.require_vendor(db,vendor_id,organization_id);service.link_asset(db,row,asset_id,actor);return service.present(db,row,True)
@router.get("/{vendor_id}/procurement")
def vendor_procurement(vendor_id:UUID,db:Session=Depends(get_db),_=Depends(reader),organization_id=Depends(organization_context)):
    return service.present(db,service.require_vendor(db,vendor_id,organization_id),True)["procurement"]
@router.post("/{vendor_id}/procurement/{procurement_id}")
def link_procurement(vendor_id:UUID,procurement_id:UUID,db:Session=Depends(get_db),actor=Depends(manager),organization_id=Depends(organization_context)):
    row=service.require_vendor(db,vendor_id,organization_id);service.link_procurement(db,row,procurement_id,actor);return service.present(db,row,True)
