from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.security import get_current_user, require_roles
from app.models.discovered_device import ReviewStatus
from app.models.user import User
from app.schemas.discovery import (
    ApprovalResponse,
    BulkActionResponse,
    BulkApproveRequest,
    BulkReviewRequest,
    DiscoveredDeviceResponse,
    DiscoveryPage,
    DiscoveryRunResponse,
    DiscoveryStatsResponse,
    InventoryApproval,
    RejectRequest,
    RunDiscoveryRequest,
)
from app.services.discovery_service import (
    DiscoveryConflictError,
    DiscoveryNotFoundError,
    DiscoveryService,
    DiscoveryStateError,
)


router = APIRouter(prefix="/discovery", tags=["Discovery"])
admin = require_roles(["admin"])


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DiscoveryNotFoundError):
        return HTTPException(404, str(exc))
    if isinstance(exc, DiscoveryConflictError):
        return HTTPException(409, str(exc))
    if isinstance(exc, (DiscoveryStateError, ValidationError)):
        return HTTPException(422, str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(400, str(exc))
    return HTTPException(500, "Discovery operation failed")


@router.get("/export")
def export_discovery(
    db: Session = Depends(get_db),
    _: User = Depends(admin),
):
    content, filename = DiscoveryService(db).export_csv()
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/stats", response_model=DiscoveryStatsResponse)
def discovery_stats(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return DiscoveryService(db).statistics()


@router.get("", response_model=DiscoveryPage)
@router.get("/", response_model=DiscoveryPage, include_in_schema=False)
def list_discovery(
    search: str | None = Query(default=None, max_length=200),
    status: str | None = Query(default=None, pattern="^(online|offline|unknown)$"),
    review_status: str | None = Query(default=None, pattern="^(pending|approved|ignored|rejected)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    try:
        return DiscoveryService(db).list_discovered_devices(
            search=search,
            status=status,
            review_status=review_status,
            page=page,
            page_size=page_size,
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/{discovery_id}", response_model=DiscoveredDeviceResponse)
def discovery_detail(
    discovery_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    try:
        return DiscoveryService(db).get_discovered_device(discovery_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/run", response_model=DiscoveryRunResponse)
def run_discovery(
    payload: RunDiscoveryRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(admin),
):
    try:
        return DiscoveryService(db).discover_range(
            payload.range_scanned,
            trigger_type="manual",
            triggered_by=actor.id,
            audit_actor=actor.username,
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/{discovery_id}/approve", response_model=ApprovalResponse)
def approve_discovery(
    discovery_id: UUID,
    payload: InventoryApproval,
    db: Session = Depends(get_db),
    actor: User = Depends(admin),
):
    try:
        discovered, device = DiscoveryService(db).approve(discovery_id, payload, actor)
        return {"discovery": discovered, "device": device}
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/{discovery_id}/ignore", response_model=DiscoveredDeviceResponse)
def ignore_discovery(
    discovery_id: UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(admin),
):
    try:
        return DiscoveryService(db).review(discovery_id, ReviewStatus.IGNORED, actor)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/{discovery_id}/reject", response_model=DiscoveredDeviceResponse)
def reject_discovery(
    discovery_id: UUID,
    payload: RejectRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(admin),
):
    try:
        return DiscoveryService(db).review(discovery_id, ReviewStatus.REJECTED, actor, payload.reason)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/bulk-approve", response_model=BulkActionResponse)
def bulk_approve(
    payload: BulkApproveRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(admin),
):
    try:
        results = DiscoveryService(db).bulk_approve(
            [(item.discovery_id, item.inventory) for item in payload.items],
            actor,
        )
        return {"processed": len(results), "discovery_ids": [item[0].id for item in results]}
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/bulk-ignore", response_model=BulkActionResponse)
def bulk_ignore(
    payload: BulkReviewRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(admin),
):
    try:
        results = DiscoveryService(db).bulk_review(payload.discovery_ids, ReviewStatus.IGNORED, actor)
        return {"processed": len(results), "discovery_ids": [item.id for item in results]}
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/bulk-reject", response_model=BulkActionResponse)
def bulk_reject(
    payload: BulkReviewRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(admin),
):
    try:
        results = DiscoveryService(db).bulk_review(
            payload.discovery_ids,
            ReviewStatus.REJECTED,
            actor,
            payload.reason,
        )
        return {"processed": len(results), "discovery_ids": [item.id for item in results]}
    except Exception as exc:
        raise _http_error(exc) from exc
