from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import PasswordReset, UserCreate, UserRoleUpdate, UserStatusUpdate, UserUpdate
from app.services.audit_service import create_audit_log

SUPPORTED_ROLES = ("admin", "technician", "staff")


def _get(db: Session, user_id: str) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    return user


def _ensure_unique(db: Session, username: str, email: str, exclude_id: str | None = None):
    query = db.query(User).filter(or_(func.lower(User.username) == username.lower(), func.lower(User.email) == email.lower()))
    if exclude_id:
        query = query.filter(User.id != exclude_id)
    if query.first():
        raise HTTPException(409, "A user with this username or email already exists")


def _ensure_role(role: str):
    if role not in SUPPORTED_ROLES:
        raise HTTPException(422, "Unsupported role")


def _ensure_not_last_admin(db: Session, user: User):
    if user.role == "admin" and user.is_active:
        count = db.query(User).filter(User.role == "admin", User.is_active.is_(True)).count()
        if count <= 1:
            raise HTTPException(409, "The last active administrator cannot be changed")


def create_user(db: Session, payload: UserCreate, actor: User):
    _ensure_role(payload.role)
    _ensure_unique(db, payload.username.strip(), str(payload.email).lower())
    user = User(username=payload.username.strip(), email=str(payload.email).lower(), hashed_password=hash_password(payload.password), role=payload.role, is_active=payload.is_active)
    try:
        db.add(user); db.flush()
        create_audit_log(db, actor.username, "USER_CREATED", "User", user.id, f"Created account {user.username}")
        db.commit(); db.refresh(user); return user
    except Exception:
        db.rollback(); raise


def update_user(db: Session, user_id: str, payload: UserUpdate, actor: User):
    user = _get(db, user_id)
    username = payload.username.strip() if payload.username is not None else user.username
    email = str(payload.email).lower() if payload.email is not None else user.email
    _ensure_unique(db, username, email, user.id)
    user.username, user.email = username, email
    try:
        create_audit_log(db, actor.username, "USER_UPDATED", "User", user.id, f"Updated account {user.username}")
        db.commit(); db.refresh(user); return user
    except Exception:
        db.rollback(); raise


def set_status(db: Session, user_id: str, payload: UserStatusUpdate, actor: User):
    user = _get(db, user_id)
    if user.id == actor.id and not payload.is_active:
        raise HTTPException(400, "You cannot deactivate your own account")
    if not payload.is_active:
        _ensure_not_last_admin(db, user)
    user.is_active = payload.is_active
    action = "USER_ACTIVATED" if payload.is_active else "USER_DEACTIVATED"
    try:
        create_audit_log(db, actor.username, action, "User", user.id, f"{'Activated' if payload.is_active else 'Deactivated'} {user.username}")
        db.commit(); db.refresh(user); return user
    except Exception:
        db.rollback(); raise


def set_role(db: Session, user_id: str, payload: UserRoleUpdate, actor: User):
    _ensure_role(payload.role)
    user = _get(db, user_id)
    if user.role == "admin" and payload.role != "admin":
        _ensure_not_last_admin(db, user)
    previous = user.role; user.role = payload.role
    try:
        create_audit_log(db, actor.username, "USER_ROLE_CHANGED", "User", user.id, f"Changed {user.username} role from {previous} to {payload.role}")
        db.commit(); db.refresh(user); return user
    except Exception:
        db.rollback(); raise


def reset_password(db: Session, user_id: str, payload: PasswordReset, actor: User):
    user = _get(db, user_id); user.hashed_password = hash_password(payload.password)
    try:
        create_audit_log(db, actor.username, "USER_PASSWORD_RESET", "User", user.id, f"Administrator reset the password for {user.username}")
        db.commit(); return {"message": "Temporary password set successfully"}
    except Exception:
        db.rollback(); raise
