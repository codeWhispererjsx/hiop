from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.security import require_roles
from app.models.user import User
from app.services.circuit_breaker import get_all_circuit_breakers, reset_circuit_breaker

router = APIRouter(prefix="/circuit-breakers", tags=["Circuit Breakers"])


@router.get("/")
def get_circuit_breaker_status(
    current_user: User = Depends(require_roles(["admin", "platformadmin"]))
):
    """Get status of all circuit breakers"""
    return get_all_circuit_breakers()


@router.post("/{name}/reset")
def reset_circuit_breaker_endpoint(
    name: str,
    current_user: User = Depends(require_roles(["admin", "platformadmin"]))
):
    """Reset a specific circuit breaker"""
    reset_circuit_breaker(name)
    return {"message": f"Circuit breaker '{name}' has been reset"}