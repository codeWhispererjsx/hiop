from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.models.backup import BackupRecord, RestoreTest
from app.models.user import User
from app.services.backup_service import (
    get_backup_health,
    get_latest_restore_test,
    perform_backup,
    record_restore_test_failure,
    record_restore_test_start,
    record_restore_test_success,
    verify_backup,
)

router = APIRouter(prefix="/backup-recovery", tags=["Backup & Recovery"])
platform_admin = require_roles(["platformadmin"])

BackupStatus = Literal["in_progress", "success", "failed", "verification_failed"]
RestoreStatus = Literal["in_progress", "success", "failed"]


class BackupHealth(BaseModel):
    status: str
    last_success: str | None
    age_hours: float | None
    details: str


class BackupRecordModel(BaseModel):
    id: str
    backup_type: str
    status: BackupStatus
    started_at: str
    completed_at: str | None
    file_path: str | None
    file_size_bytes: int | None
    checksum: str | None
    checksum_verified: bool
    error: str | None
    retention_days: int
    database_version: str | None


class RestoreTestModel(BaseModel):
    id: str
    status: RestoreStatus
    started_at: str
    completed_at: str | None
    backup_file: str
    database_version: str | None
    restore_duration_seconds: int | None
    organizations_verified: int
    properties_verified: int
    users_verified: int
    assets_verified: int
    devices_verified: int
    incidents_verified: int
    error: str | None
    performed_by: str


class BackupRequest(BaseModel):
    backup_type: str = Field(default="manual", pattern="^(manual|scheduled)$")
    retention_days: int = Field(default=14, ge=1, le=365)


class RestoreTestRequest(BaseModel):
    backup_file: str = Field(..., min_length=1, max_length=500)
    organizations_verified: int = Field(default=0, ge=0)
    properties_verified: int = Field(default=0, ge=0)
    users_verified: int = Field(default=0, ge=0)
    assets_verified: int = Field(default=0, ge=0)
    devices_verified: int = Field(default=0, ge=0)
    incidents_verified: int = Field(default=0, ge=0)
    data_integrity_checks: str = Field(default="{}")
    restore_duration_seconds: int = Field(default=0, ge=0)


@router.get("/health", response_model=BackupHealth)
def get_health(db: Session = Depends(get_db), _: User = Depends(platform_admin)):
    """Get backup health status."""
    health = get_backup_health(db)
    return BackupHealth(**health)


@router.get("/backups", response_model=list[BackupRecordModel])
def list_backups(
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(platform_admin),
):
    """List backup records."""
    records = db.query(BackupRecord).order_by(BackupRecord.started_at.desc()).limit(limit).all()
    return [
        BackupRecordModel(
            id=str(record.id),
            backup_type=record.backup_type,
            status=record.status,
            started_at=record.started_at.isoformat(),
            completed_at=record.completed_at.isoformat() if record.completed_at else None,
            file_path=record.file_path,
            file_size_bytes=record.file_size_bytes,
            checksum=record.checksum,
            checksum_verified=record.checksum_verified,
            error=record.error,
            retention_days=record.retention_days,
            database_version=record.database_version,
        )
        for record in records
    ]


@router.post("/backups", response_model=BackupRecordModel, status_code=201)
def create_backup(
    request: BackupRequest,
    db: Session = Depends(get_db),
    _: User = Depends(platform_admin),
):
    """Trigger a manual backup."""
    try:
        record = perform_backup(db, request.backup_type, request.retention_days)
        return BackupRecordModel(
            id=str(record.id),
            backup_type=record.backup_type,
            status=record.status,
            started_at=record.started_at.isoformat(),
            completed_at=record.completed_at.isoformat() if record.completed_at else None,
            file_path=record.file_path,
            file_size_bytes=record.file_size_bytes,
            checksum=record.checksum,
            checksum_verified=record.checksum_verified,
            error=record.error,
            retention_days=record.retention_days,
            database_version=record.database_version,
        )
    except Exception as exc:
        raise HTTPException(500, f"Backup failed: {str(exc)}")


@router.post("/backups/{backup_id}/verify")
def verify_backup_endpoint(
    backup_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(platform_admin),
):
    """Verify a backup file."""
    record = db.query(BackupRecord).filter_by(id=backup_id).first()
    if not record:
        raise HTTPException(404, "Backup record not found")
    
    if not record.file_path:
        raise HTTPException(400, "Backup has no file path")
    
    is_valid = verify_backup(record.file_path)
    
    if is_valid:
        record.checksum_verified = True
        db.commit()
        return {"status": "verified", "file_path": record.file_path}
    else:
        record.checksum_verified = False
        db.commit()
        raise HTTPException(400, "Backup verification failed")


@router.get("/restore-tests", response_model=list[RestoreTestModel])
def list_restore_tests(
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(platform_admin),
):
    """List restore test records."""
    records = db.query(RestoreTest).order_by(RestoreTest.started_at.desc()).limit(limit).all()
    return [
        RestoreTestModel(
            id=str(record.id),
            status=record.status,
            started_at=record.started_at.isoformat(),
            completed_at=record.completed_at.isoformat() if record.completed_at else None,
            backup_file=record.backup_file,
            database_version=record.database_version,
            restore_duration_seconds=record.restore_duration_seconds,
            organizations_verified=record.organizations_verified,
            properties_verified=record.properties_verified,
            users_verified=record.users_verified,
            assets_verified=record.assets_verified,
            devices_verified=record.devices_verified,
            incidents_verified=record.incidents_verified,
            error=record.error,
            performed_by=record.performed_by,
        )
        for record in records
    ]


@router.post("/restore-tests", response_model=RestoreTestModel, status_code=201)
def create_restore_test(
    request: RestoreTestRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(platform_admin),
):
    """Record the start of a restore test drill."""
    performed_by = actor.username
    record = record_restore_test_start(db, request.backup_file, performed_by)
    
    return RestoreTestModel(
        id=str(record.id),
        status=record.status,
        started_at=record.started_at.isoformat(),
        completed_at=None,
        backup_file=record.backup_file,
        database_version=None,
        restore_duration_seconds=None,
        organizations_verified=0,
        properties_verified=0,
        users_verified=0,
        assets_verified=0,
        devices_verified=0,
        incidents_verified=0,
        error=None,
        performed_by=performed_by,
    )


@router.post("/restore-tests/{test_id}/complete")
def complete_restore_test(
    test_id: UUID,
    request: RestoreTestRequest,
    db: Session = Depends(get_db),
    _: User = Depends(platform_admin),
):
    """Record successful restore test completion."""
    record = record_restore_test_success(
        db,
        test_id,
        None,  # backup_id would be set if referencing a backup record
        request.restore_duration_seconds,
        request.organizations_verified,
        request.properties_verified,
        request.users_verified,
        request.assets_verified,
        request.devices_verified,
        request.incidents_verified,
        request.data_integrity_checks,
    )
    
    return {"status": "completed", "test_id": str(test_id)}


@router.post("/restore-tests/{test_id}/fail")
def fail_restore_test(
    test_id: UUID,
    error: str = Query(..., max_length=1000),
    db: Session = Depends(get_db),
    _: User = Depends(platform_admin),
):
    """Record restore test failure."""
    record = record_restore_test_failure(db, test_id, error)
    return {"status": "failed", "test_id": str(test_id)}
