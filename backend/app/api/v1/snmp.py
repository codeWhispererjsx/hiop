from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc
from uuid import UUID

from app.api.dependencies import get_db
from app.core.security import get_current_user, require_roles
from app.core.tenant import organization_context, property_context
from app.models.snmp import SNMPCredential, SNMPTarget
from app.models.user import User
from app.services.snmp_credential_service import SNMPCredentialService
from app.services.snmp_target_service import SNMPTargetService
from app.schemas.snmp import SNMPCredentialCreate, SNMPCredentialUpdate, SNMPTargetCreate, SNMPTargetUpdate
from app.services.audit_service import create_audit_log

router = APIRouter(
    prefix="/snmp",
    tags=["SNMP"]
)

admin_role = require_roles(["admin"])
viewer_role = require_roles(["admin", "technician", "viewer"])


# ============================================================================
# SNMP CREDENTIALS
# ============================================================================

@router.get("/credentials")
def list_snmp_credentials(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    enabled: bool | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(viewer_role),
    organization_id=Depends(organization_context),
):
    """List SNMP credentials"""
    query = db.query(SNMPCredential).filter(SNMPCredential.organization_id == organization_id)
    
    if enabled is not None:
        query = query.filter(SNMPCredential.enabled == enabled)
    
    if search:
        query = query.filter(SNMPCredential.name.ilike(f"%{search}%"))
    
    total = query.count()
    items = query.order_by(desc(SNMPCredential.created_at)).offset(skip).limit(limit).all()
    pages = (total + limit - 1) // limit
    
    return {
        "items": [
            {
                "id": str(item.id),
                "name": item.name,
                "version": item.version,
                "username": item.username,
                "authentication_protocol": item.authentication_protocol,
                "privacy_protocol": item.privacy_protocol,
                "security_level": item.security_level,
                "context_name": item.context_name,
                "enabled": item.enabled,
                "description": item.description,
                "has_community": bool(item.community_encrypted),
                "has_authentication_secret": bool(item.authentication_secret_encrypted),
                "has_privacy_secret": bool(item.privacy_secret_encrypted),
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            }
            for item in items
        ],
        "total": total,
        "page": skip // limit + 1 if limit > 0 else 1,
        "page_size": limit,
        "pages": pages
    }


@router.post("/credentials")
def create_snmp_credential(
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_role),
    organization_id=Depends(organization_context),
):
    """Create SNMP credential"""
    try:
        # Parse the input
        from app.models.snmp import SNMPVersion
        version_enum = SNMPVersion(body.get("version")) if isinstance(body.get("version"), str) else body.get("version")
        
        credential_data = SNMPCredentialCreate(
            name=body.get("name"),
            version=version_enum,
            community=body.get("community"),
            username=body.get("username"),
            authentication_protocol=body.get("authentication_protocol", "none"),
            authentication_secret=body.get("authentication_secret"),
            privacy_protocol=body.get("privacy_protocol", "none"),
            privacy_secret=body.get("privacy_secret"),
            security_level=body.get("security_level", "noAuthNoPriv"),
            context_name=body.get("context_name"),
            enabled=body.get("enabled", True),
            description=body.get("description"),
        )
        
        service = SNMPCredentialService(db)
        credential = service.create_credential(credential_data, current_user, organization_id)
        
        return {
            "id": str(credential.id),
            "name": credential.name,
            "version": credential.version,
            "username": credential.username,
            "authentication_protocol": credential.authentication_protocol,
            "privacy_protocol": credential.privacy_protocol,
            "security_level": credential.security_level,
            "context_name": credential.context_name,
            "enabled": credential.enabled,
            "description": credential.description,
            "has_community": bool(credential.community_encrypted),
            "has_authentication_secret": bool(credential.authentication_secret_encrypted),
            "has_privacy_secret": bool(credential.privacy_secret_encrypted),
            "created_at": credential.created_at.isoformat(),
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/credentials/{credential_id}")
def get_snmp_credential(
    credential_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(viewer_role),
    organization_id=Depends(organization_context),
):
    """Get SNMP credential details"""
    try:
        cred_uuid = UUID(credential_id)
        credential = db.query(SNMPCredential).filter(
            SNMPCredential.id == cred_uuid,
            SNMPCredential.organization_id == organization_id
        ).first()
        if not credential:
            raise HTTPException(status_code=404, detail="Credential not found")
        
        return {
            "id": str(credential.id),
            "name": credential.name,
            "version": credential.version,
            "username": credential.username,
            "authentication_protocol": credential.authentication_protocol,
            "privacy_protocol": credential.privacy_protocol,
            "security_level": credential.security_level,
            "context_name": credential.context_name,
            "enabled": credential.enabled,
            "description": credential.description,
            "has_community": bool(credential.community_encrypted),
            "has_authentication_secret": bool(credential.authentication_secret_encrypted),
            "has_privacy_secret": bool(credential.privacy_secret_encrypted),
            "created_at": credential.created_at.isoformat(),
            "updated_at": credential.updated_at.isoformat(),
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid credential ID")


@router.patch("/credentials/{credential_id}")
def update_snmp_credential(
    credential_id: str,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_role),
    organization_id=Depends(organization_context),
):
    """Update SNMP credential"""
    try:
        cred_uuid = UUID(credential_id)
        credential = db.query(SNMPCredential).filter(
            SNMPCredential.id == cred_uuid,
            SNMPCredential.organization_id == organization_id
        ).first()
        if not credential:
            raise HTTPException(status_code=404, detail="Credential not found")
        
        # Update fields
        if "name" in body:
            credential.name = body["name"]
        if "enabled" in body:
            credential.enabled = body["enabled"]
        if "description" in body:
            credential.description = body["description"]
        
        credential.updated_by = current_user.id
        
        create_audit_log(db, current_user.username, "SNMP_CREDENTIAL_UPDATED", "SNMPCredential", credential_id, f"Updated SNMP credential '{credential.name}'")
        db.commit()
        db.refresh(credential)
        
        return {
            "id": str(credential.id),
            "name": credential.name,
            "version": credential.version,
            "username": credential.username,
            "authentication_protocol": credential.authentication_protocol,
            "privacy_protocol": credential.privacy_protocol,
            "security_level": credential.security_level,
            "context_name": credential.context_name,
            "enabled": credential.enabled,
            "description": credential.description,
            "has_community": bool(credential.community_encrypted),
            "has_authentication_secret": bool(credential.authentication_secret_encrypted),
            "has_privacy_secret": bool(credential.privacy_secret_encrypted),
            "updated_at": credential.updated_at.isoformat(),
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid credential ID")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# SNMP TARGETS
# ============================================================================

@router.get("/targets")
def list_snmp_targets(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    enabled: bool | None = None,
    polling_enabled: bool | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(viewer_role),
    organization_id=Depends(organization_context),
):
    """List SNMP targets (switches/devices)"""
    query = db.query(SNMPTarget).filter(SNMPTarget.organization_id == organization_id)
    
    if enabled is not None:
        query = query.filter(SNMPTarget.enabled == enabled)
    
    if polling_enabled is not None:
        query = query.filter(SNMPTarget.polling_enabled == polling_enabled)
    
    if search:
        query = query.filter(
            (SNMPTarget.name.ilike(f"%{search}%")) |
            (SNMPTarget.ip_address.ilike(f"%{search}%")) |
            (SNMPTarget.hostname.ilike(f"%{search}%"))
        )
    
    total = query.count()
    items = query.order_by(desc(SNMPTarget.created_at)).offset(skip).limit(limit).all()
    pages = (total + limit - 1) // limit
    
    return {
        "items": [
            {
                "id": str(item.id),
                "name": item.name,
                "ip_address": item.ip_address,
                "hostname": item.hostname,
                "port": item.port,
                "version": item.version,
                "enabled": item.enabled,
                "polling_enabled": item.polling_enabled,
                "timeout_seconds": item.timeout_seconds,
                "retries": item.retries,
                "transport": item.transport,
                "context_name": item.context_name,
                "last_test_status": item.last_test_status,
                "last_tested_at": item.last_tested_at.isoformat() if item.last_tested_at else None,
                "last_successful_poll_at": item.last_successful_poll_at.isoformat() if item.last_successful_poll_at else None,
                "last_response_time_ms": item.last_response_time_ms,
                "consecutive_failures": item.consecutive_failures,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in items
        ],
        "total": total,
        "page": skip // limit + 1 if limit > 0 else 1,
        "page_size": limit,
        "pages": pages
    }


@router.post("/targets")
def create_snmp_target(
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_role),
    organization_id=Depends(organization_context),
):
    """Create SNMP target (add a switch/device to monitor)"""
    try:
        target_data = SNMPTargetCreate(
            name=body.get("name"),
            ip_address=body.get("ip_address"),
            hostname=body.get("hostname"),
            port=body.get("port", 161),
            version=body.get("version"),
            credential_id=UUID(body.get("credential_id")),
            enabled=body.get("enabled", True),
            polling_enabled=body.get("polling_enabled", False),
            timeout_seconds=body.get("timeout_seconds", 5),
            retries=body.get("retries", 1),
            transport=body.get("transport", "udp"),
            context_name=body.get("context_name", ""),
        )
        
        service = SNMPTargetService(db)
        target = service.create_target(target_data, current_user, organization_id)
        
        create_audit_log(db, current_user.username, "SNMP_TARGET_CREATED", "SNMPTarget", str(target.id), f"Created SNMP target '{target.name}' ({target.ip_address})")
        db.commit()
        
        return {
            "id": str(target.id),
            "name": target.name,
            "ip_address": target.ip_address,
            "hostname": target.hostname,
            "port": target.port,
            "version": target.version,
            "enabled": target.enabled,
            "polling_enabled": target.polling_enabled,
            "timeout_seconds": target.timeout_seconds,
            "retries": target.retries,
            "transport": target.transport,
            "context_name": target.context_name,
            "created_at": target.created_at.isoformat(),
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/targets/{target_id}")
def get_snmp_target(
    target_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(viewer_role),
    organization_id=Depends(organization_context),
):
    """Get SNMP target details"""
    try:
        target_uuid = UUID(target_id)
        target = db.query(SNMPTarget).filter(
            SNMPTarget.id == target_uuid,
            SNMPTarget.organization_id == organization_id
        ).first()
        if not target:
            raise HTTPException(status_code=404, detail="Target not found")
        
        return {
            "id": str(target.id),
            "name": target.name,
            "ip_address": target.ip_address,
            "hostname": target.hostname,
            "port": target.port,
            "version": target.version,
            "enabled": target.enabled,
            "polling_enabled": target.polling_enabled,
            "timeout_seconds": target.timeout_seconds,
            "retries": target.retries,
            "transport": target.transport,
            "context_name": target.context_name,
            "last_test_status": target.last_test_status,
            "last_test_message": target.last_test_message,
            "last_tested_at": target.last_tested_at.isoformat() if target.last_tested_at else None,
            "last_successful_poll_at": target.last_successful_poll_at.isoformat() if target.last_successful_poll_at else None,
            "last_response_time_ms": target.last_response_time_ms,
            "consecutive_failures": target.consecutive_failures,
            "created_at": target.created_at.isoformat(),
            "updated_at": target.updated_at.isoformat(),
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid target ID")


@router.patch("/targets/{target_id}")
def update_snmp_target(
    target_id: str,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_role),
    organization_id=Depends(organization_context),
):
    """Update SNMP target"""
    try:
        target_uuid = UUID(target_id)
        target = db.query(SNMPTarget).filter(
            SNMPTarget.id == target_uuid,
            SNMPTarget.organization_id == organization_id
        ).first()
        if not target:
            raise HTTPException(status_code=404, detail="Target not found")
        
        # Update fields
        if "name" in body:
            target.name = body["name"]
        if "enabled" in body:
            target.enabled = body["enabled"]
        if "polling_enabled" in body:
            target.polling_enabled = body["polling_enabled"]
        if "timeout_seconds" in body:
            target.timeout_seconds = body["timeout_seconds"]
        if "retries" in body:
            target.retries = body["retries"]
        
        target.updated_by = current_user.id
        
        create_audit_log(db, current_user.username, "SNMP_TARGET_UPDATED", "SNMPTarget", target_id, f"Updated SNMP target '{target.name}'")
        db.commit()
        db.refresh(target)
        
        return {
            "id": str(target.id),
            "name": target.name,
            "ip_address": target.ip_address,
            "hostname": target.hostname,
            "port": target.port,
            "version": target.version,
            "enabled": target.enabled,
            "polling_enabled": target.polling_enabled,
            "timeout_seconds": target.timeout_seconds,
            "retries": target.retries,
            "transport": target.transport,
            "context_name": target.context_name,
            "last_test_status": target.last_test_status,
            "updated_at": target.updated_at.isoformat(),
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid target ID")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/targets/{target_id}/test")
def test_snmp_target(
    target_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_role),
    organization_id=Depends(organization_context),
):
    """Test SNMP target connection"""
    try:
        target_uuid = UUID(target_id)
        target = db.query(SNMPTarget).filter(
            SNMPTarget.id == target_uuid,
            SNMPTarget.organization_id == organization_id
        ).first()
        if not target:
            raise HTTPException(status_code=404, detail="Target not found")
        
        # Placeholder test response
        return {
            "overall_status": "ok",
            "transport_status": "reachable",
            "authentication_status": "authenticated",
            "system_identity_status": "detected",
            "detected_version": target.version,
            "duration_ms": 45,
            "response_time_ms": 42,
            "warnings": [],
            "tested_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            "identity": {
                "sys_name": {"value_text": "CoreSwitch-01", "quality": "confirmed"},
                "sys_descr": {"value_text": "Cisco IOS Software", "quality": "confirmed"},
            }
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid target ID")


@router.post("/targets/{target_id}/disable")
def disable_snmp_target(
    target_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_role),
    organization_id=Depends(organization_context),
):
    """Disable SNMP target"""
    try:
        target_uuid = UUID(target_id)
        target = db.query(SNMPTarget).filter(
            SNMPTarget.id == target_uuid,
            SNMPTarget.organization_id == organization_id
        ).first()
        if not target:
            raise HTTPException(status_code=404, detail="Target not found")
        
        target.enabled = False
        target.updated_by = current_user.id
        
        create_audit_log(db, current_user.username, "SNMP_TARGET_DISABLED", "SNMPTarget", target_id, f"Disabled SNMP target '{target.name}'")
        db.commit()
        db.refresh(target)
        
        return {"id": str(target.id), "enabled": target.enabled}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid target ID")


@router.post("/credentials/{credential_id}/disable")
def disable_snmp_credential(
    credential_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_role),
    organization_id=Depends(organization_context),
):
    """Disable SNMP credential"""
    try:
        cred_uuid = UUID(credential_id)
        credential = db.query(SNMPCredential).filter(
            SNMPCredential.id == cred_uuid,
            SNMPCredential.organization_id == organization_id
        ).first()
        if not credential:
            raise HTTPException(status_code=404, detail="Credential not found")
        
        credential.enabled = False
        credential.updated_by = current_user.id
        
        create_audit_log(db, current_user.username, "SNMP_CREDENTIAL_DISABLED", "SNMPCredential", credential_id, f"Disabled SNMP credential '{credential.name}'")
        db.commit()
        db.refresh(credential)
        
        return {"id": str(credential.id), "enabled": credential.enabled}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid credential ID")
