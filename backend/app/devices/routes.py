from sqlalchemy.orm import Session
from app.models.device import Device
from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas.device import (
    DeviceCreate,
    DeviceResponse,
    DeviceUpdate,
)
from typing import List
from app.core.security import get_current_user, require_roles
from app.models.user import User
from app.api.dependencies import get_db

router = APIRouter(
    prefix="/devices",
    tags=["Devices"]
)


@router.post("/", response_model=DeviceResponse)
def create_device(
    device: DeviceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin"]))
):
    new_device = Device(**device.model_dump())

    db.add(new_device)
    db.commit()
    db.refresh(new_device)

    return new_device

from typing import List


@router.get("/", response_model=List[DeviceResponse])
def get_devices(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    devices = db.query(Device).all()

    return devices

@router.put("/{device_id}", response_model=DeviceResponse)
def update_device(
    device_id: str,
    device_data: DeviceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "technician"]))
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

    db.commit()
    db.refresh(device)

    return device

@router.delete("/{device_id}")
def delete_device(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin"]))
):
    device = db.query(Device).filter(
        Device.id == device_id
    ).first()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )

    db.delete(device)
    db.commit()

    return {
        "message": "Device deleted successfully"
    }

@router.get("/{device_id}", response_model=DeviceResponse)
def get_device(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    device = db.query(Device).filter(
        Device.id == device_id
    ).first()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )

    return device