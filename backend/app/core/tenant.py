from uuid import UUID

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.security import get_current_user, get_db
from app.models.hierarchy import Organization, Property
from app.models.property_access import UserPropertyAccess
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


def allowed_property_ids(db: Session, user: User, organization_id: UUID) -> set[UUID]:
    organization_properties = {row[0] for row in db.query(Property.id).filter(Property.organization_id == organization_id, Property.is_active.is_(True)).all()}
    if user.role in {"platformadmin", "admin"}:
        return organization_properties
    grants = {row[0] for row in db.query(UserPropertyAccess.property_id).join(Property, Property.id == UserPropertyAccess.property_id).filter(UserPropertyAccess.user_id == user.id, UserPropertyAccess.enabled.is_(True), Property.organization_id == organization_id).all()}
    return grants


def property_context(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    organization_id: UUID = Depends(organization_context),
    x_hiop_property_id: UUID | None = Header(default=None),
) -> UUID | None:
    """Resolve the visible property. Admins may omit it for organization-wide summaries."""
    if x_hiop_property_id is None:
        if user.role in {"platformadmin", "admin"}:
            return None
        permitted = allowed_property_ids(db, user, organization_id)
        if len(permitted) == 1:
            return next(iter(permitted))
        if not permitted:
            raise HTTPException(403, "No property access has been assigned")
        raise HTTPException(400, "Select a property before opening operational data")
    prop = db.query(Property).filter(Property.id == x_hiop_property_id, Property.organization_id == organization_id).first()
    if not prop or x_hiop_property_id not in allowed_property_ids(db, user, organization_id):
        raise HTTPException(403, "Property is outside your permitted scope")
    if not prop.is_active and user.role != "platformadmin":
        raise HTTPException(403, "This property is inactive")
    return prop.id


def device_in_organization(db: Session, device_id, organization_id: UUID):
    from app.models.device import Device
    from app.models.hierarchy import Property
    return db.query(Device).outerjoin(Property, Device.property_id == Property.id).filter(
        Device.id == device_id, Property.organization_id == organization_id
    ).first()


def device_in_scope(db: Session, device_id, organization_id: UUID, property_id: UUID | None):
    from app.models.device import Device
    from app.models.hierarchy import Property

    query = db.query(Device).join(Property, Device.property_id == Property.id).filter(
        Device.id == device_id, Property.organization_id == organization_id
    )
    if property_id is not None:
        query = query.filter(Device.property_id == property_id)
    return query.first()
