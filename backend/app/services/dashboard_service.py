from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.network_scan import NetworkScan
from app.models.ticket import Ticket
from app.schemas.dashboard import (
    DashboardResponse,
    DeviceStats,
    NetworkStats,
    TicketStats,
)


def get_dashboard(db: Session):
    total_devices, online_devices, offline_devices = db.query(
        func.count(Device.id),
        func.sum(case((Device.network_status == "Online", 1), else_=0)),
        func.sum(case((Device.network_status == "Offline", 1), else_=0)),
    ).filter(Device.inventory_status != "Retired").one()
    total_devices = total_devices or 0
    online_devices = online_devices or 0
    offline_devices = offline_devices or 0

    unknown_devices = total_devices - (
    online_devices + offline_devices
    )

    open_tickets, in_progress_tickets, closed_tickets = db.query(
        func.sum(case((Ticket.status == "Open", 1), else_=0)),
        func.sum(case((Ticket.status == "In Progress", 1), else_=0)),
        func.sum(case((Ticket.status == "Closed", 1), else_=0)),
    ).one()

    last_scan = db.query(
        func.max(NetworkScan.scanned_at)
    ).scalar()

    return DashboardResponse(
        devices=DeviceStats(
        total=total_devices,
        online=online_devices,
        offline=offline_devices,
        unknown=unknown_devices,
    ),
        tickets=TicketStats(
            open=open_tickets or 0,
            in_progress=in_progress_tickets or 0,
            closed=closed_tickets or 0,
        ),
        network=NetworkStats(
            last_scan=str(last_scan) if last_scan else None,
        ),
    )
