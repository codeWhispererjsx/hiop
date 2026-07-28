import hashlib, os
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from app.core.security import get_db, require_roles
from app.models.device import Device
from app.models.configuration_management import ConfigurationDeviceProfile, ConfigurationBackupPolicy, ConfigurationBackupRun, DeviceConfigurationVersion
from app.services.secret_encryption_service import SecretEncryptionService
from app.models.configuration_collectors import ConfigurationKnownHost, ConfigurationConnectionTestRun
from app.services.configuration_collector_service import MockCollector
from app.models.configuration_drift import ConfigurationComparison, ConfigurationDriftRecord
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
@router.get("/known-hosts")
def known_hosts(db:Session=Depends(get_db),_=Depends(reader)): return page(db.query(ConfigurationKnownHost).order_by(ConfigurationKnownHost.created_at.desc()))
@router.post("/known-hosts/{host_id}/trust")
def trust_host(host_id:UUID,db:Session=Depends(get_db),user=Depends(admin)):
    row=db.get(ConfigurationKnownHost,host_id)
    if not row: raise HTTPException(404,"Known host not found")
    row.trust_status="trusted";row.approved_by=user.username;db.commit();return {"status":"trusted"}
@router.post("/known-hosts/{host_id}/reject")
def reject_host(host_id:UUID,db:Session=Depends(get_db),_=Depends(admin)):
    row=db.get(ConfigurationKnownHost,host_id)
    if not row: raise HTTPException(404,"Known host not found")
    row.trust_status="rejected";db.commit();return {"status":"rejected"}
@router.post("/assignments/{assignment_id}/test")
def test_assignment(assignment_id:UUID,db:Session=Depends(get_db),user=Depends(admin)):
    result=MockCollector().test_connection(); row=ConfigurationConnectionTestRun(status=result["status"],triggered_by=user.username,safe_message="Mock collector; no device connection performed");db.add(row);db.commit();db.refresh(row);return {"test_run_id":str(row.id),**result}
@router.get("/connection-tests")
def connection_tests(db:Session=Depends(get_db),_=Depends(reader)): return page(db.query(ConfigurationConnectionTestRun).order_by(ConfigurationConnectionTestRun.created_at.desc()))
@router.get("/comparisons")
def comparisons(db:Session=Depends(get_db),_=Depends(reader)): return page(db.query(ConfigurationComparison).order_by(ConfigurationComparison.generated_at.desc()))
@router.post("/comparisons",status_code=201)
def create_comparison(source_version_id:UUID,target_version_id:UUID,db:Session=Depends(get_db),user=Depends(admin)):
    source=db.get(DeviceConfigurationVersion,source_version_id);target=db.get(DeviceConfigurationVersion,target_version_id)
    if not source or not target or source.device_id!=target.device_id or source.property_id!=target.property_id or source.id==target.id: raise HTTPException(400,"Versions must belong to the same device and property")
    unchanged=source.checksum==target.checksum; row=ConfigurationComparison(property_id=source.property_id,device_id=source.device_id,source_version_id=source.id,target_version_id=target.id,status="unchanged" if unchanged else "completed",change_count=0 if unchanged else 1,risk_level="none" if unchanged else "unknown",summary="Checksums match; no normalized change detected." if unchanged else "Content differs; encrypted content requires approved comparison worker.");db.add(row);db.commit();db.refresh(row);return row
@router.get("/drift")
def drift(db:Session=Depends(get_db),_=Depends(reader)): return page(db.query(ConfigurationDriftRecord).order_by(ConfigurationDriftRecord.last_detected_at.desc()))
@router.post("/versions/{version_id}/promote-baseline")
def promote_baseline(version_id:UUID,db:Session=Depends(get_db),_=Depends(admin)):
    row=db.get(DeviceConfigurationVersion,version_id)
    if not row: raise HTTPException(404,"Version not found")
    db.query(DeviceConfigurationVersion).filter(DeviceConfigurationVersion.device_id==row.device_id,DeviceConfigurationVersion.configuration_scope==row.configuration_scope).update({"is_baseline":False});row.is_baseline=True;db.commit();return {"status":"baseline","version_id":str(row.id)}
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
