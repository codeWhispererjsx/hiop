from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.security import require_roles
from app.models.user import User
from app.services.integration_status import get_integration_tracker, initialize_integrations

router = APIRouter(prefix="/integration-status", tags=["Integration Status"])


@router.get("/")
def get_all_integration_status(
    current_user: User = Depends(require_roles(["admin", "platformadmin"]))
):
    """Get status of all integrations"""
    return get_integration_tracker().get_all_status()


@router.get("/{name}")
def get_integration_status(
    name: str,
    current_user: User = Depends(require_roles(["admin", "platformadmin"]))
):
    """Get status of a specific integration"""
    status = get_integration_tracker().get_status(name)
    if not status:
        return {"error": "Integration not found"}
    
    return {
        "status": status.status.value,
        "last_success": status.last_success.isoformat() if status.last_success else None,
        "last_failure": status.last_failure.isoformat() if status.last_failure else None,
        "last_test": status.last_test.isoformat() if status.last_test else None,
        "error_count": status.error_count,
        "consecutive_failures": status.consecutive_failures,
        "last_error": status.last_error,
        "metadata": status.metadata,
    }


@router.post("/{name}/reset")
def reset_integration_status(
    name: str,
    current_user: User = Depends(require_roles(["admin", "platformadmin"]))
):
    """Reset an integration's status"""
    get_integration_tracker().reset_integration(name)
    return {"message": f"Integration '{name}' status has been reset"}