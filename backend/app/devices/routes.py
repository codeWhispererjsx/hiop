from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.models.device import Device
from app.schemas.device import DeviceCreate, DeviceResponse
from fastapi import APIRouter, Depends, HTTPException, status

router = APIRouter(
    prefix="/devices",
    tags=["Devices"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/", response_model=DeviceResponse)
def create_device(
    device: DeviceCreate,
    db: Session = Depends(get_db)
):
    new_device = Device(**device.model_dump())

    db.add(new_device)
    db.commit()
    db.refresh(new_device)

    return new_device

from typing import List


@router.get("/", response_model=List[DeviceResponse])
def get_devices(
    db: Session = Depends(get_db)
):
    devices = db.query(Device).all()

    return devices

@router.get("/{device_id}", response_model=DeviceResponse)
def get_device(
    device_id: str,
    db: Session = Depends(get_db)
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