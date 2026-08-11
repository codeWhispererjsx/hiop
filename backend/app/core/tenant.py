from uuid import UUID

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.security import get_current_user, get_db
from app.models.hierarchy import Organization
from app.models.user import User


def organization_context(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    x_organization_id: UUID | None = Header(default=None),
) -> UUID:
    organization_id = x_organization_id if user.role == "platformadmin" else user.organization_id
    if not organization_id:
        raise HTTPException(403, "Select an organization before opening operational data")
    organization = db.get(Organization, organization_id)
    if not organization:
        raise HTTPException(404, "Organization not found")
    if organization.status != "active" and user.role != "platformadmin":
        raise HTTPException(403, "This organization is suspended or inactive")
    return organization_id


def device_in_organization(db: Session, device_id, organization_id: UUID):
    from app.models.device import Device
    from app.models.hierarchy import Property
    return db.query(Device).outerjoin(Property, Device.property_id == Property.id).filter(
        Device.id == device_id, Property.organization_id == organization_id
    ).first()
