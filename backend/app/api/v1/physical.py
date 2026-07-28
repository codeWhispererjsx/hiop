from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.core.security import get_db, require_roles
from app.models.hierarchy import Building, Floor, Zone, Property
from app.schemas.physical import BuildingWrite, BuildingRead, FloorWrite, FloorRead, ZoneWrite, ZoneRead
from app.services.physical_infrastructure_service import PhysicalInfrastructureService
from app.services.audit_service import create_audit_log

router = APIRouter(tags=["Physical infrastructure"])
reader = require_roles(["admin", "technician"]); admin = require_roles(["admin"])
def page(q, page, size): return {"items": q.offset((page-1)*size).limit(size).all(), "total": q.count(), "page": page, "page_size": size}

@router.get("/buildings")
def buildings(search: str|None=None, property_id: UUID|None=None, status_filter: str|None=Query(None, alias="status"), page_number:int=Query(1,alias="page",ge=1), page_size:int=Query(50,ge=1,le=100), db:Session=Depends(get_db), _=Depends(reader)):
    q=db.query(Building).order_by(Building.name)
    if search:q=q.filter(Building.name.ilike(f"%{search.strip()}%"))
    if property_id:q=q.filter(Building.property_id==property_id)
    if status_filter:q=q.filter(Building.status==status_filter)
    return page(q,page_number,page_size)
@router.post("/buildings", response_model=BuildingRead, status_code=201)
def create_building(p:BuildingWrite, db:Session=Depends(get_db), user=Depends(admin)):
    s=PhysicalInfrastructureService(db); s.validate_parent(Property,p.property_id); s.ensure_unique(Building,p.name,"property_id",p.property_id)
    row=Building(**p.model_dump()); db.add(row); db.flush(); create_audit_log(db,user.username,"CREATE_BUILDING","Building",str(row.id),f"Created building {row.name}"); db.commit(); db.refresh(row); return row
@router.patch("/buildings/{ident}", response_model=BuildingRead)
def update_building(ident:UUID,p:BuildingWrite,db:Session=Depends(get_db),user=Depends(admin)):
    s=PhysicalInfrastructureService(db); row=s.get(Building,ident); s.validate_parent(Property,p.property_id); s.ensure_unique(Building,p.name,"property_id",p.property_id,ident)
    for k,v in p.model_dump().items(): setattr(row,k,v)
    row.is_active=p.status=="active"; create_audit_log(db,user.username,"UPDATE_BUILDING","Building",str(row.id),f"Updated building {row.name}"); db.commit(); db.refresh(row); return row
@router.delete("/buildings/{ident}",status_code=204)
def delete_building(ident:UUID,db:Session=Depends(get_db),user=Depends(admin)):
    row=PhysicalInfrastructureService(db).get(Building,ident); row.status="inactive"; row.is_active=False; db.commit()

@router.get("/floors")
def floors(search:str|None=None,building_id:UUID|None=None,status_filter:str|None=Query(None,alias="status"),page_number:int=Query(1,alias="page",ge=1),page_size:int=Query(50,ge=1,le=100),db:Session=Depends(get_db),_=Depends(reader)):
    q=db.query(Floor).order_by(Floor.floor_number,Floor.name)
    if search:q=q.filter(Floor.name.ilike(f"%{search.strip()}%"))
    if building_id:q=q.filter(Floor.building_id==building_id)
    if status_filter:q=q.filter(Floor.status==status_filter)
    return page(q,page_number,page_size)
@router.post("/floors",response_model=FloorRead,status_code=201)
def create_floor(p:FloorWrite,db:Session=Depends(get_db),user=Depends(admin)):
    s=PhysicalInfrastructureService(db); s.validate_parent(Building,p.building_id); s.ensure_unique(Floor,p.name,"building_id",p.building_id); row=Floor(**p.model_dump()); db.add(row); db.commit(); db.refresh(row); return row
@router.patch("/floors/{ident}",response_model=FloorRead)
def update_floor(ident:UUID,p:FloorWrite,db:Session=Depends(get_db),user=Depends(admin)):
    s=PhysicalInfrastructureService(db); row=s.get(Floor,ident); s.validate_parent(Building,p.building_id); s.ensure_unique(Floor,p.name,"building_id",p.building_id,ident)
    for k,v in p.model_dump().items():setattr(row,k,v)
    row.is_active=p.status=="active"; db.commit(); db.refresh(row); return row
@router.delete("/floors/{ident}",status_code=204)
def delete_floor(ident:UUID,db:Session=Depends(get_db),user=Depends(admin)):
    row=PhysicalInfrastructureService(db).get(Floor,ident); row.status="inactive"; row.is_active=False; db.commit()

@router.get("/zones")
def zones(search:str|None=None,floor_id:UUID|None=None,status_filter:str|None=Query(None,alias="status"),zone_type:str|None=Query(None,alias="type"),page_number:int=Query(1,alias="page",ge=1),page_size:int=Query(50,ge=1,le=100),db:Session=Depends(get_db),_=Depends(reader)):
    q=db.query(Zone).order_by(Zone.name)
    if search:q=q.filter(Zone.name.ilike(f"%{search.strip()}%"))
    if floor_id:q=q.filter(Zone.floor_id==floor_id)
    if status_filter:q=q.filter(Zone.status==status_filter)
    if zone_type:q=q.filter(Zone.type==zone_type)
    return page(q,page_number,page_size)
@router.post("/zones",response_model=ZoneRead,status_code=201)
def create_zone(p:ZoneWrite,db:Session=Depends(get_db),user=Depends(admin)):
    s=PhysicalInfrastructureService(db); s.validate_parent(Floor,p.floor_id); s.ensure_unique(Zone,p.name,"floor_id",p.floor_id); row=Zone(**p.model_dump()); db.add(row); db.commit(); db.refresh(row); return row
@router.patch("/zones/{ident}",response_model=ZoneRead)
def update_zone(ident:UUID,p:ZoneWrite,db:Session=Depends(get_db),user=Depends(admin)):
    s=PhysicalInfrastructureService(db); row=s.get(Zone,ident); s.validate_parent(Floor,p.floor_id); s.ensure_unique(Zone,p.name,"floor_id",p.floor_id,ident)
    for k,v in p.model_dump().items():setattr(row,k,v)
    row.is_active=p.status=="active"; db.commit(); db.refresh(row); return row
@router.delete("/zones/{ident}",status_code=204)
def delete_zone(ident:UUID,db:Session=Depends(get_db),user=Depends(admin)):
    row=PhysicalInfrastructureService(db).get(Zone,ident); row.status="inactive"; row.is_active=False; db.commit()
