from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.security import get_current_user, require_roles
from app.models.user import User
from app.models.audit_log import AuditLog
from app.schemas.user import PasswordReset, UserCreate, UserResponse, UserRoleUpdate, UserStatusUpdate, UserUpdate
from app.services import user_service

router = APIRouter(prefix="/users", tags=["Users"])
admin = require_roles(["admin"])


@router.get("/roles")
def roles(_: User = Depends(get_current_user)):
    return list(user_service.SUPPORTED_ROLES)


@router.get("/eligible-assignees", response_model=list[UserResponse])
def eligible(db: Session = Depends(get_db), _: User = Depends(require_roles(["admin", "technician"]))):
    return db.query(User).filter(User.is_active.is_(True), User.role.in_(["admin", "technician"])).order_by(User.username).all()


@router.get("/{user_id}/audit")
def user_audit(user_id: str, db: Session = Depends(get_db), _: User = Depends(admin)):
    user_service._get(db, user_id)
    return db.query(AuditLog).filter(AuditLog.entity_type == "User", AuditLog.entity_id == user_id).order_by(AuditLog.created_at.desc()).all()


@router.get("", response_model=list[UserResponse])
@router.get("/", response_model=list[UserResponse], include_in_schema=False)
def list_users(db: Session = Depends(get_db), _: User = Depends(admin)):
    return db.query(User).order_by(User.created_at.desc()).all()


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: str, db: Session = Depends(get_db), _: User = Depends(admin)):
    return user_service._get(db, user_id)


@router.post("", response_model=UserResponse, status_code=201)
def create(payload: UserCreate, db: Session = Depends(get_db), actor: User = Depends(admin)):
    return user_service.create_user(db, payload, actor)


@router.patch("/{user_id}", response_model=UserResponse)
def update(user_id: str, payload: UserUpdate, db: Session = Depends(get_db), actor: User = Depends(admin)):
    return user_service.update_user(db, user_id, payload, actor)


@router.patch("/{user_id}/status", response_model=UserResponse)
def status(user_id: str, payload: UserStatusUpdate, db: Session = Depends(get_db), actor: User = Depends(admin)):
    return user_service.set_status(db, user_id, payload, actor)


@router.delete("/{user_id}", response_model=UserResponse)
def deactivate(user_id: str, db: Session = Depends(get_db), actor: User = Depends(admin)):
    """Compatibility route: retain the account and safely deactivate it."""
    return user_service.set_status(db, user_id, UserStatusUpdate(is_active=False), actor)


@router.patch("/{user_id}/role", response_model=UserResponse)
def role(user_id: str, payload: UserRoleUpdate, db: Session = Depends(get_db), actor: User = Depends(admin)):
    return user_service.set_role(db, user_id, payload, actor)


@router.post("/{user_id}/reset-password")
def password(user_id: str, payload: PasswordReset, db: Session = Depends(get_db), actor: User = Depends(admin)):
    return user_service.reset_password(db, user_id, payload, actor)
