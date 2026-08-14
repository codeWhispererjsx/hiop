from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.security import get_current_user
from app.core.tenant import organization_context, property_context
from app.models.user import User
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard_service import (
    get_dashboard as get_dashboard_service,
)

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)


@router.get("/", response_model=DashboardResponse)
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization_id=Depends(organization_context),
    property_id=Depends(property_context),
):
    return get_dashboard_service(db, organization_id, property_id)
