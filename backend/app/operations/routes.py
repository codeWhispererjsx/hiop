from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.security import get_current_user, require_roles
from app.models.alert import Alert
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.settings import GeneralSettings, NetworkSettings, NotificationSettings, OrganizationSettings, PublicSettings, SettingsBundle, SystemHealth
from app.services.audit_service import create_audit_log
from app.services import settings_service
from app.services.scheduler_service import configure_scheduler

router = APIRouter(tags=["Operations"])
ALLOWED_ROLES = {"admin", "technician", "staff"}


class UserUpdate(BaseModel):
    role: str | None = None
    is_active: bool | None = None


@router.get("/alerts")
def list_alerts(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(Alert).order_by(Alert.created_at.desc()).limit(200).all()


@router.patch("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(404, "Alert not found")
    alert.acknowledged = True
    create_audit_log(db, current_user.username, "ACKNOWLEDGE_ALERT", "Alert", str(alert.id), alert.message)
    db.commit()
    return {"id": str(alert.id), "acknowledged": True}


@router.get("/audit-logs", include_in_schema=False)
def list_audit_logs(db: Session = Depends(get_db), _: User = Depends(require_roles(["admin", "technician"]))):
    return db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(500).all()


@router.get("/users", include_in_schema=False)
def list_users(db: Session = Depends(get_db), _: User = Depends(require_roles(["admin"]))):
    return db.query(User).order_by(User.created_at.desc()).all()


@router.patch("/users/{user_id}", include_in_schema=False)
def update_user(user_id: str, payload: UserUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_roles(["admin"]))):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if payload.role is not None:
        if payload.role not in ALLOWED_ROLES:
            raise HTTPException(422, "Unsupported role")
        user.role = payload.role
    if payload.is_active is not None:
        if user.id == current_user.id and not payload.is_active:
            raise HTTPException(400, "You cannot deactivate your own account")
        user.is_active = payload.is_active
    create_audit_log(db, current_user.username, "UPDATE_USER", "User", user.id, f"Updated access for {user.username}")
    db.commit(); db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=204, include_in_schema=False)
def deactivate_user(user_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_roles(["admin"]))):
    if user_id == current_user.id:
        raise HTTPException(400, "You cannot deactivate your own account")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    user.is_active = False
    create_audit_log(db, current_user.username, "DEACTIVATE_USER", "User", user.id, f"Deactivated {user.username}")
    db.commit()


@router.get("/settings", response_model=SettingsBundle)
def get_settings(db: Session = Depends(get_db), _: User = Depends(require_roles(["admin"]))):
    return settings_service.read_bundle(db)


@router.get("/settings/public", response_model=PublicSettings)
def public_settings(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return settings_service.read_public(db)


def save_settings_group(db: Session, user: User, group: str, payload):
    try:
        settings_service.save_group(db, group, payload)
        create_audit_log(db, user.username, f"UPDATE_{group.upper()}_SETTINGS", "Settings", group, f"Updated {group} settings")
        db.commit()
    except Exception:
        db.rollback(); raise
    return settings_service.read_bundle(db)


@router.put("/settings/general", response_model=SettingsBundle)
def update_general(payload: GeneralSettings, db: Session = Depends(get_db), user: User = Depends(require_roles(["admin"]))):
    return save_settings_group(db, user, "general", payload)


@router.put("/settings/organization", response_model=SettingsBundle)
def update_organization(payload: OrganizationSettings, db: Session = Depends(get_db), user: User = Depends(require_roles(["admin"]))):
    return save_settings_group(db, user, "organization", payload)


@router.put("/settings/network", response_model=SettingsBundle)
def update_network(payload: NetworkSettings, db: Session = Depends(get_db), user: User = Depends(require_roles(["admin"]))):
    result = save_settings_group(db, user, "network", payload)
    configure_scheduler(payload.automatic_scanning, payload.scan_interval_minutes)
    return result


@router.put("/settings/notifications", response_model=SettingsBundle)
def update_notifications(payload: NotificationSettings, db: Session = Depends(get_db), user: User = Depends(require_roles(["admin"]))):
    return save_settings_group(db, user, "notifications", payload)


@router.get("/settings/system-health", response_model=SystemHealth)
def system_health(db: Session = Depends(get_db), _: User = Depends(require_roles(["admin"]))):
    return settings_service.health(db)
