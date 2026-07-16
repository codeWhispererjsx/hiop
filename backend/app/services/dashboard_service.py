from sqlalchemy import func
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
    operational_devices = db.query(Device).filter(Device.inventory_status != "Retired")
    total_devices = operational_devices.count()
    online_devices = operational_devices.filter(Device.network_status == "Online").count()
    offline_devices = operational_devices.filter(Device.network_status == "Offline").count()

    unknown_devices = total_devices - (
    online_devices + offline_devices
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
        offline=offline_devices,
        unknown=unknown_devices,
    ),
        tickets=TicketStats(
            open=open_tickets,
            in_progress=in_progress_tickets,
            closed=closed_tickets,
        ),
        network=NetworkStats(
            last_scan=str(last_scan) if last_scan else None,
        ),
    )
