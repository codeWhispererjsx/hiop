import logging
from app.core.config import settings

from fastapi import APIRouter, Depends, HTTPException, Request, status, Header
from sqlalchemy.orm import Session
from app.models.user import User
from app.schemas.user import UserResponse
from app.schemas.user import UserLogin, Token
from app.core.security import authenticate_user, create_access_token, get_current_user, verify_password, hash_password, revoke_token, decode_access_token
from app.schemas.user import PasswordChange
from app.api.dependencies import get_db
from app.core.rate_limit import login_limiter
from app.services.audit_service import create_audit_log
from datetime import datetime, timezone

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)
security_logger = logging.getLogger("hiop.security")

@router.post("/login", response_model=Token)
def login(
    user_data: UserLogin,
    request: Request,
    db: Session = Depends(get_db)
):
    client = request.client.host if request.client else "unknown"
    login_limiter.check(client)
    user = db.query(User).filter(
        User.email == user_data.email
    ).first()

    user = authenticate_user(user, user_data.password)

    if not user:
        login_limiter.failure(client)
        security_logger.warning("authentication_failed client=%s", client)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # Check if user must change password
    if user.must_change_password:
        login_limiter.failure(client)
        security_logger.warning("password_change_required user=%s", user.id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password change required. Please change your password before continuing."
        )

    if settings.require_email_verification and not user.email_verified_at:
        login_limiter.failure(client)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verify your email before signing in.")

    login_limiter.success(client)
    user.last_login_at = datetime.now(timezone.utc)
    create_audit_log(db, user.username, "LOGIN_SUCCESS", "User", user.id, "Authenticated successfully")
    db.commit()
    security_logger.info("authentication_succeeded client=%s user_id=%s", client, user.id)
    access_token = create_access_token(
        data={
            "sub": user.email,
            "role": user.role,
            "uid": user.id,
            "organization_id": str(user.organization_id) if user.organization_id else None,
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(get_current_user)
):
    return current_user


@router.post("/logout")
def logout(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    authorization: str = Header(None, alias="Authorization")
):
    """Logout endpoint - revokes the current token"""
    # Extract token from Authorization header
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        payload = decode_access_token(token)
        if payload and "jti" in payload:
            revoke_token(db, payload["jti"], current_user.id, "logout")

    create_audit_log(db, current_user.username, "LOGOUT", "User", current_user.id, "User logged out")
    db.commit()
    return {"message": "Successfully logged out"}


@router.post("/change-password")
def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Change password for authenticated user"""
    # Verify current password
    if not verify_password(password_data.current_password, current_user.hashed_password):
        security_logger.warning("password_change_failed user=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    
    # Update password
    current_user.hashed_password = hash_password(password_data.new_password)
    current_user.must_change_password = False  # Clear must_change_password flag
    create_audit_log(db, current_user.username, "PASSWORD_CHANGED", "User", current_user.id, "User changed password")
    db.commit()
    
    security_logger.info("password_changed user=%s", current_user.id)
    return {"message": "Password changed successfully"}
