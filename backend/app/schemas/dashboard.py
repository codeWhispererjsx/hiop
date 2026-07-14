from pydantic import BaseModel


class DeviceStats(BaseModel):
    total: int
    online: int
    offline: int
    unknown: int


class TicketStats(BaseModel):
    open: int
    in_progress: int
    closed: int


class NetworkStats(BaseModel):
    last_scan: str | None


class DashboardResponse(BaseModel):
    devices: DeviceStats
    tickets: TicketStats
    network: NetworkStats