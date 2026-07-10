from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.security import get_current_user
from app.models.device import Device
from app.models.network_scan import NetworkScan
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.dashboard import (
    DashboardResponse,
    DeviceStats,
    NetworkStats,
    TicketStats,
)


router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)


@router.get("/", response_model=DashboardResponse)
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    total_devices = db.query(Device).count()

    latest_scan_times = (
        db.query(
            NetworkScan.device_id.label("device_id"),
            func.max(NetworkScan.scanned_at).label("latest_scanned_at")
        )
        .group_by(NetworkScan.device_id)
        .subquery()
    )

    latest_scans = (
        db.query(NetworkScan)
        .join(
            latest_scan_times,
            (NetworkScan.device_id == latest_scan_times.c.device_id)
            & (
                NetworkScan.scanned_at
                == latest_scan_times.c.latest_scanned_at
            )
        )
        .all()
    )

    online_devices = sum(
        1 for scan in latest_scans if scan.status == "Online"
    )

    offline_devices = sum(
        1 for scan in latest_scans if scan.status == "Offline"
    )

    open_tickets = db.query(Ticket).filter(
        Ticket.status == "Open"
    ).count()

    in_progress_tickets = db.query(Ticket).filter(
        Ticket.status == "In Progress"
    ).count()

    closed_tickets = db.query(Ticket).filter(
        Ticket.status == "Closed"
    ).count()

    last_scan = db.query(
        func.max(NetworkScan.scanned_at)
    ).scalar()

    return DashboardResponse(
        devices=DeviceStats(
            total=total_devices,
            online=online_devices,
            offline=offline_devices
        ),
        tickets=TicketStats(
            open=open_tickets,
            in_progress=in_progress_tickets,
            closed=closed_tickets
        ),
        network=NetworkStats(
            last_scan=str(last_scan) if last_scan else None
        )
    )