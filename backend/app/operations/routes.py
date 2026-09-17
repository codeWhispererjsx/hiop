from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import get_db
from app.core.tenant import organization_context
from app.models.hierarchy import Organization
from app.core.security import get_current_user, require_roles
from app.models.alert import Alert
from app.models.user import User
from app.schemas.settings import DiscoverySettings, GeneralSettings, IncidentSettings, NetworkSettings, NotificationSettings, OrganizationSettings, PublicSettings, SettingsBundle, SNMPSettings, SystemHealth
from app.services.audit_service import create_audit_log
from app.services import settings_service
from app.services.scheduler_service import configure_discovery_scheduler, configure_scheduler

router = APIRouter(tags=["Operations"])
@router.get("/alerts")
def list_alerts(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(Alert).order_by(Alert.created_at.desc()).limit(200).all()


@router.patch("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(require_roles(["admin", "technician"]))):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(404, "Alert not found")
    alert.acknowledged = True
    create_audit_log(db, current_user.username, "ACKNOWLEDGE_ALERT", "Alert", str(alert.id), alert.message)
    db.commit()
    return {"id": str(alert.id), "acknowledged": True}


def user_bundle(db, user):
    if user.organization_id: db.info["organization_id"]=user.organization_id
    result=settings_service.read_bundle(db)
    organization=db.get(Organization,user.organization_id) if user.organization_id else None
    if organization:
        result["general"]["timezone"]=organization.timezone
        result["organization"]["organization_name"]=organization.name
    return result

@router.get("/settings", response_model=SettingsBundle)
def get_settings(db: Session = Depends(get_db), _: User = Depends(require_roles(["admin"]))):
    return user_bundle(db, _)


@router.get("/settings/public", response_model=PublicSettings)
def public_settings(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    if _.organization_id: db.info["organization_id"]=_.organization_id
    result=settings_service.read_public(db)
    organization=db.get(Organization,_.organization_id) if _.organization_id else None
    if organization:
        result.update(timezone=organization.timezone,organization_name=organization.name)
    return result


def save_settings_group(db: Session, user: User, group: str, payload):
    if user.organization_id: db.info["organization_id"]=user.organization_id
    try:
        settings_service.save_group(db, group, payload)
        create_audit_log(db, user.username, f"UPDATE_{group.upper()}_SETTINGS", "Settings", group, f"Updated {group} settings")
        db.commit()
    except Exception:
        db.rollback(); raise
    return user_bundle(db, user)


@router.put("/settings/general", response_model=SettingsBundle)
def update_general(payload: GeneralSettings, db: Session = Depends(get_db), user: User = Depends(require_roles(["admin"])), org=Depends(organization_context)):
    organization=db.get(Organization,org)
    organization.timezone=payload.timezone
    return save_settings_group(db, user, "general", payload)


@router.put("/settings/organization", response_model=SettingsBundle)
def update_organization(payload: OrganizationSettings, db: Session = Depends(get_db), user: User = Depends(require_roles(["admin"]))):
    organization=db.get(Organization,user.organization_id) if user.organization_id else None
    if organization:
        organization.name=payload.organization_name
        organization.address=payload.address
        organization.contact_email=str(payload.support_email) if payload.support_email else None
        organization.contact_phone=payload.support_phone
    return save_settings_group(db, user, "organization", payload)


@router.put("/settings/network", response_model=SettingsBundle)
def update_network(payload: NetworkSettings, db: Session = Depends(get_db), user: User = Depends(require_roles(["admin"]))):
    result = save_settings_group(db, user, "network", payload)
    if not user.organization_id: configure_scheduler(payload.automatic_scanning, payload.scan_interval_minutes)
    return result


@router.put("/settings/notifications", response_model=SettingsBundle)
def update_notifications(payload: NotificationSettings, db: Session = Depends(get_db), user: User = Depends(require_roles(["admin"]))):
    return save_settings_group(db, user, "notifications", payload)


@router.put("/settings/discovery", response_model=SettingsBundle)
def update_discovery(payload: DiscoverySettings, db: Session = Depends(get_db), user: User = Depends(require_roles(["admin"]))):
    result = save_settings_group(db, user, "discovery", payload)
    if not user.organization_id: configure_discovery_scheduler(payload.enabled, payload.interval_minutes)
    return result


@router.put("/settings/incidents", response_model=SettingsBundle)
def update_incidents(payload: IncidentSettings, db: Session = Depends(get_db), user: User = Depends(require_roles(["admin"]))):
    return save_settings_group(db, user, "incidents", payload)


@router.put("/settings/snmp", response_model=SettingsBundle)
def update_snmp(payload: SNMPSettings, db: Session = Depends(get_db), user: User = Depends(require_roles(["admin"]))):
    return save_settings_group(db, user, "snmp", payload)


@router.get("/settings/system-health")
def system_health(db: Session = Depends(get_db), _: User = Depends(require_roles(["admin"]))):
    result=settings_service.health(db)
    return {"status":result["status"],"email":result["email"]}
