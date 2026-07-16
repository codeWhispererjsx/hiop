import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.models.user import User
from app.schemas.user import UserResponse
from app.schemas.user import UserLogin, Token
from app.core.security import authenticate_user, create_access_token
from app.core.security import get_current_user
from app.api.dependencies import get_db
from app.core.rate_limit import login_limiter

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

    login_limiter.success(client)
    security_logger.info("authentication_succeeded client=%s user_id=%s", client, user.id)
    access_token = create_access_token(
        data={
            "sub": user.email,
            "role": user.role
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
