from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.security import get_current_user, require_roles
from app.models.device import Device
from app.models.hierarchy import Building, Department, Floor, NetworkZone, Property, Room
from app.models.user import User
from app.schemas.hierarchy import HierarchyCatalog, HierarchyMutation, NetworkZoneInput, ParentInput, PropertyInput
from app.services.audit_service import create_audit_log

router = APIRouter(prefix="/hierarchy", tags=["Hierarchy"])
Kind = Literal["properties", "buildings", "floors", "rooms", "departments", "network-zones"]
MODELS = {"properties": Property, "buildings": Building, "floors": Floor, "rooms": Room, "departments": Department, "network-zones": NetworkZone}
PARENT_FIELDS = {"buildings": "property_id", "floors": "building_id", "rooms": "floor_id", "departments": "property_id", "network-zones": "property_id"}
PARENT_MODELS = {"buildings": Property, "floors": Building, "rooms": Floor, "departments": Property, "network-zones": Property}


def serialize(kind: Kind, row: Any) -> dict[str, Any]:
    result = {"id": row.id, "name": row.name, "is_active": row.is_active}
    if kind == "properties":
        result.update(code=row.code, address=row.address)
    else:
        result["parent_id"] = getattr(row, PARENT_FIELDS[kind])
    if kind == "network-zones":
        result.update(cidr=row.cidr, vlan_id=row.vlan_id)
    return result


def validate_parent(db: Session, kind: Kind, parent_id: UUID | None) -> None:
    if parent_id and not db.query(PARENT_MODELS[kind]).filter(PARENT_MODELS[kind].id == parent_id).first():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Selected parent does not exist")


@router.get("", response_model=HierarchyCatalog)
def catalog(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    def rows(kind: Kind):
        model = MODELS[kind]
        return [serialize(kind, row) for row in db.query(model).order_by(model.name).all()]
    return {"properties": rows("properties"), "buildings": rows("buildings"), "floors": rows("floors"), "rooms": rows("rooms"), "departments": rows("departments"), "network_zones": rows("network-zones")}


@router.post("/{kind}", status_code=status.HTTP_201_CREATED)
def create(kind: Kind, payload: HierarchyMutation, db: Session = Depends(get_db), user: User = Depends(require_roles(["admin"]))):
    model = MODELS[kind]
    raw = payload.model_dump()
    if kind == "properties":
        values = PropertyInput.model_validate(raw).model_dump()
    elif kind == "network-zones":
        parsed = NetworkZoneInput.model_validate(raw)
        validate_parent(db, kind, parsed.parent_id)
        values = parsed.model_dump(exclude={"parent_id"}) | {PARENT_FIELDS[kind]: parsed.parent_id}
    else:
        parsed = ParentInput.model_validate(raw)
        validate_parent(db, kind, parsed.parent_id)
        values = parsed.model_dump(exclude={"parent_id"}) | {PARENT_FIELDS[kind]: parsed.parent_id}
    values["name"] = values["name"].strip()
    if db.query(model).filter(func.lower(model.name) == values["name"].lower()).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "A record with this name already exists")
    row = model(**values)
    db.add(row); db.flush()
    create_audit_log(db, user.username, "CREATE_HIERARCHY", model.__name__, str(row.id), f"Created {row.name}")
    try:
        db.commit(); db.refresh(row)
    except IntegrityError as exc:
        db.rollback(); raise HTTPException(status.HTTP_409_CONFLICT, "Hierarchy record conflicts with existing data") from exc
    return serialize(kind, row)


@router.put("/{kind}/{row_id}")
def update(kind: Kind, row_id: UUID, payload: HierarchyMutation, db: Session = Depends(get_db), user: User = Depends(require_roles(["admin"]))):
    model = MODELS[kind]
    row = db.query(model).filter(model.id == row_id).first()
    if not row: raise HTTPException(status.HTTP_404_NOT_FOUND, "Hierarchy record not found")
    raw = payload.model_dump()
    if kind == "properties": values = PropertyInput.model_validate(raw).model_dump()
    elif kind == "network-zones":
        parsed = NetworkZoneInput.model_validate(raw); validate_parent(db, kind, parsed.parent_id)
        values = parsed.model_dump(exclude={"parent_id"}) | {PARENT_FIELDS[kind]: parsed.parent_id}
    else:
        parsed = ParentInput.model_validate(raw); validate_parent(db, kind, parsed.parent_id)
        values = parsed.model_dump(exclude={"parent_id"}) | {PARENT_FIELDS[kind]: parsed.parent_id}
    duplicate = db.query(model).filter(model.id != row_id, func.lower(model.name) == values["name"].strip().lower()).first()
    if duplicate: raise HTTPException(status.HTTP_409_CONFLICT, "A record with this name already exists")
    for key, value in values.items(): setattr(row, key, value.strip() if key == "name" else value)
    create_audit_log(db, user.username, "UPDATE_HIERARCHY", model.__name__, str(row.id), f"Updated {row.name}")
    db.commit(); db.refresh(row)
    return serialize(kind, row)


@router.delete("/{kind}/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate(kind: Kind, row_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_roles(["admin"]))):
    model = MODELS[kind]; row = db.query(model).filter(model.id == row_id).first()
    if not row: raise HTTPException(status.HTTP_404_NOT_FOUND, "Hierarchy record not found")
    row.is_active = False
    create_audit_log(db, user.username, "DEACTIVATE_HIERARCHY", model.__name__, str(row.id), f"Deactivated {row.name}")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
