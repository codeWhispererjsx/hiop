from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.security import get_current_user, get_db, require_roles
from app.models.hierarchy import Property, Organization
from app.models.property_access import UserPropertyAccess
from app.models.user import User

router = APIRouter(tags=["Property context"])
class PropertySelection(BaseModel): property_id: UUID
class AccessWrite(BaseModel):
    property_id: UUID
    access_level: str = "property_viewer"
    is_default: bool = False
    enabled: bool = True

def authorized(db: Session, user: User):
    if user.role in {"admin", "superadmin"}:
        return db.query(Property).filter(Property.operational_status == "active").order_by(Property.name).all()
    rows = db.query(Property).join(UserPropertyAccess, UserPropertyAccess.property_id == Property.id).filter(UserPropertyAccess.user_id == user.id, UserPropertyAccess.enabled.is_(True), Property.operational_status == "active").all()
    return [p for p in rows if not any(a.expires_at and a.expires_at <= datetime.now(timezone.utc) for a in db.query(UserPropertyAccess).filter(UserPropertyAccess.user_id == user.id, UserPropertyAccess.property_id == p.id).all())]

@router.get("/context")
def context(db:Session=Depends(get_db), user:User=Depends(get_current_user), x_hiop_property_id:UUID|None=Header(None)):
    props=authorized(db,user); active=None
    if x_hiop_property_id:
        active=next((p for p in props if p.id==x_hiop_property_id),None)
        if not active: raise HTTPException(403,"Property is not authorized or inactive")
    elif len(props)==1: active=props[0]
    access=None
    if active:
        access=db.query(UserPropertyAccess).filter_by(user_id=user.id,property_id=active.id,enabled=True).first()
    return {"user": {"id":user.id,"username":user.username,"role":user.role},"authorized_properties":props,"active_property":active,"default_property":active,"access_level":access.access_level if access else ("global_admin" if user.role in {"admin","superadmin"} else None),"selection_required":len(props)>1 and active is None}

@router.post("/context/property")
def select_property(payload:PropertySelection, db:Session=Depends(get_db), user:User=Depends(get_current_user)):
    props=authorized(db,user); prop=next((p for p in props if p.id==payload.property_id),None)
    if not prop: raise HTTPException(403,"Property is not authorized or inactive")
    if user.role not in {"admin","superadmin"}:
        db.query(UserPropertyAccess).filter(UserPropertyAccess.user_id==user.id).update({"is_default":False})
        row=db.query(UserPropertyAccess).filter_by(user_id=user.id,property_id=prop.id).first()
        if row: row.is_default=True
        db.commit()
    return context(db,user,payload.property_id)

@router.get("/users/{user_id}/property-access")
def list_access(user_id:str, db:Session=Depends(get_db), _=Depends(require_roles(["admin"]))):
    return db.query(UserPropertyAccess).filter(UserPropertyAccess.user_id==user_id).all()

@router.post("/users/{user_id}/property-access", status_code=201)
def grant_access(user_id:str, payload:AccessWrite, db:Session=Depends(get_db), actor=Depends(require_roles(["admin"]))):
    if not db.get(User,user_id) or not db.get(Property,payload.property_id): raise HTTPException(404,"User or property not found")
    if db.query(UserPropertyAccess).filter_by(user_id=user_id,property_id=payload.property_id).first(): raise HTTPException(409,"Property access already exists")
    if payload.is_default: db.query(UserPropertyAccess).filter(UserPropertyAccess.user_id==user_id).update({"is_default":False})
    row=UserPropertyAccess(user_id=user_id,granted_by=actor.username,**payload.model_dump()); db.add(row); db.commit(); db.refresh(row); return row

@router.delete("/users/{user_id}/property-access/{access_id}", status_code=204)
def revoke_access(user_id:str,access_id:UUID,db:Session=Depends(get_db),_=Depends(require_roles(["admin"]))):
    row=db.query(UserPropertyAccess).filter_by(id=access_id,user_id=user_id).first()
    if not row: raise HTTPException(404,"Access assignment not found")
    row.enabled=False; db.commit()
