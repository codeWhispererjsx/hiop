from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.hierarchy import Department, NetworkZone, Room


def resolve_device_hierarchy(db: Session, values: dict) -> dict:
    """Validate hierarchy IDs and keep legacy display columns compatible."""
    mappings = {"department_id": (Department, "department"), "room_id": (Room, "location"), "network_zone_id": (NetworkZone, None)}
    for id_field, (model, text_field) in mappings.items():
        if id_field not in values or values[id_field] is None:
            continue
        row = db.query(model).filter(model.id == values[id_field], model.is_active.is_(True)).first()
        if not row:
            label = id_field.removesuffix("_id").replace("_", " ")
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Selected {label} is unavailable")
        if text_field:
            values[text_field] = row.name
    return values
