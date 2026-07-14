from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.user import User
from app.schemas.device import DeviceCreate, DeviceUpdate
from app.services.audit_service import create_audit_log


def create_device(
    db: Session,
    device: DeviceCreate,
    current_user: User
):
    new_device = Device(**device.model_dump())

    db.add(new_device)
    db.flush()

    create_audit_log(
        db=db,
        actor=current_user.username,
        action="CREATE_DEVICE",
        entity_type="Device",
        entity_id=str(new_device.id),
        description=f"Created device {new_device.hostname}"
    )

    try:
        db.commit()
        db.refresh(new_device)
    except Exception:
        db.rollback()
        raise

    return new_device


def update_device(
    db: Session,
    device_id: str,
    device_data: DeviceUpdate,
    current_user: User
):
    device = db.query(Device).filter(
        Device.id == device_id
    ).first()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )

    update_data = device_data.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        setattr(device, key, value)

    create_audit_log(
        db=db,
        actor=current_user.username,
        action="UPDATE_DEVICE",
        entity_type="Device",
        entity_id=str(device.id),
        description=f"Updated device {device.hostname}"
    )

    try:
        db.commit()
        db.refresh(device)
    except Exception:
        db.rollback()
        raise

    return device


def delete_device(
    db: Session,
    device_id: str,
    current_user: User
):
    device = db.query(Device).filter(
        Device.id == device_id
    ).first()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )

    device.status = "Retired"

    create_audit_log(
        db=db,
        actor=current_user.username,
        action="RETIRE_DEVICE",
        entity_type="Device",
        entity_id=str(device.id),
        description=f"Retired device {device.hostname}"
    )

    try:
        db.commit()
        db.refresh(device)
    except Exception:
        db.rollback()
        raise

    return {
        "message": "Device retired successfully"
    }