import hashlib, os
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from app.core.security import get_db, require_roles
from app.models.device import Device
from app.models.configuration_management import ConfigurationDeviceProfile, ConfigurationBackupPolicy, ConfigurationBackupRun, DeviceConfigurationVersion
from app.services.secret_encryption_service import SecretEncryptionService
router=APIRouter(prefix="/configuration-management",tags=["Configuration management"]); reader=require_roles(["admin","technician","viewer"]); admin=require_roles(["admin"])
def page(q,page=1,size=50): return {"items":q.offset((page-1)*size).limit(size).all(),"total":q.count(),"page":page,"page_size":size}
@router.get("/profiles")
def profiles(db:Session=Depends(get_db),_=Depends(reader)): return page(db.query(ConfigurationDeviceProfile).order_by(ConfigurationDeviceProfile.name))
@router.post("/profiles",status_code=201)
def create_profile(name:str,code:str,db:Session=Depends(get_db),_=Depends(admin)): row=ConfigurationDeviceProfile(name=name,code=code);db.add(row);db.commit();db.refresh(row);return row
@router.get("/policies")
def policies(db:Session=Depends(get_db),_=Depends(reader)): return page(db.query(ConfigurationBackupPolicy).order_by(ConfigurationBackupPolicy.name))
@router.post("/policies",status_code=201)
def create_policy(name:str,db:Session=Depends(get_db),_=Depends(admin)): row=ConfigurationBackupPolicy(name=name);db.add(row);db.commit();db.refresh(row);return row
@router.get("/runs")
def runs(db:Session=Depends(get_db),_=Depends(reader)): return page(db.query(ConfigurationBackupRun).order_by(ConfigurationBackupRun.created_at.desc()))
@router.get("/versions")
def versions(db:Session=Depends(get_db),_=Depends(reader)): return page(db.query(DeviceConfigurationVersion).order_by(DeviceConfigurationVersion.captured_at.desc()))
@router.post("/devices/{device_id}/upload",status_code=201)
async def upload(device_id:UUID,file:UploadFile=File(...),configuration_scope:str=Form("full"),db:Session=Depends(get_db),_=Depends(admin)):
    device=db.get(Device,device_id)
    if not device: raise HTTPException(404,"Device not found")
    allowed={".txt",".cfg",".conf",".json",".xml",".yaml",".yml"}; ext=os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed: raise HTTPException(400,"Unsupported configuration format")
    content=await file.read()
    if not content or len(content)>10*1024*1024: raise HTTPException(400,"Configuration file is empty or exceeds the size limit")
    checksum=hashlib.sha256(content).hexdigest(); encrypted=SecretEncryptionService.encrypt(content.decode("utf-8",errors="replace"))
    run=ConfigurationBackupRun(property_id=device.property_id,device_id=device.id,status="completed",bytes_received=len(content),checksum=checksum);db.add(run);db.flush()
    latest=db.query(DeviceConfigurationVersion).filter_by(device_id=device.id,configuration_scope=configuration_scope).order_by(DeviceConfigurationVersion.version_number.desc()).first(); version_no=(latest.version_number+1 if latest else 1)
    row=DeviceConfigurationVersion(property_id=device.property_id,device_id=device.id,backup_run_id=run.id,version_number=version_no,configuration_scope=configuration_scope,format=ext.lstrip("."),encrypted_content=encrypted.encode(),original_filename=os.path.basename(file.filename or "configuration"),content_size_bytes=len(content),checksum=checksum);db.add(row);db.commit();db.refresh(row);return {"id":str(row.id),"run_id":str(run.id),"version_number":version_no,"checksum":checksum,"status":"completed"}
