from collections.abc import Sequence
from datetime import datetime, time, timezone
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.discovered_device import DiscoveredDevice, DiscoveryRun
from app.models.device import Device


class DiscoveryRepository:
    """Persistence operations for discovered-device records; no business rules."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, device: DiscoveredDevice) -> DiscoveredDevice:
        self.db.add(device)
        return device

    def get(self, device_id: UUID) -> DiscoveredDevice | None:
        return self.db.get(DiscoveredDevice, device_id)

    def list(self, *, offset: int = 0, limit: int = 100) -> Sequence[DiscoveredDevice]:
        statement = select(DiscoveredDevice).order_by(DiscoveredDevice.last_seen_at.desc()).offset(offset).limit(limit)
        return self.db.scalars(statement).all()

    def page(
        self,
        *,
        search: str | None = None,
        status: str | None = None,
        review_status: str | None = None,
        sort_by: str = "last_seen_at",
        sort_order: str = "desc",
        offset: int = 0,
        limit: int = 25,
    ) -> tuple[Sequence[DiscoveredDevice], int]:
        filters = []
        if search and search.strip():
            term = f"%{search.strip()}%"
            filters.append(or_(
                DiscoveredDevice.ip_address.ilike(term),
                DiscoveredDevice.mac_address.ilike(term),
                DiscoveredDevice.hostname.ilike(term),
                DiscoveredDevice.vendor.ilike(term),
                DiscoveredDevice.device_type_guess.ilike(term),
            ))
        if status:
            filters.append(DiscoveredDevice.status == status)
        if review_status:
            filters.append(DiscoveredDevice.review_status == review_status)
        total = self.db.scalar(select(func.count(DiscoveredDevice.id)).where(*filters)) or 0
        sort_columns = {
            "hostname": DiscoveredDevice.hostname,
            "ip_address": DiscoveredDevice.ip_address,
            "mac_address": DiscoveredDevice.mac_address,
            "vendor": DiscoveredDevice.vendor,
            "confidence_score": DiscoveredDevice.confidence_score,
            "status": DiscoveredDevice.status,
            "review_status": DiscoveredDevice.review_status,
            "times_seen": DiscoveredDevice.times_seen,
            "first_seen_at": DiscoveredDevice.first_seen_at,
            "last_seen_at": DiscoveredDevice.last_seen_at,
        }
        sort_column = sort_columns.get(sort_by, DiscoveredDevice.last_seen_at)
        order = sort_column.asc().nulls_last() if sort_order == "asc" else sort_column.desc().nulls_last()
        statement = (
            select(DiscoveredDevice)
            .where(*filters)
            .order_by(order, DiscoveredDevice.id)
            .offset(offset)
            .limit(limit)
        )
        return self.db.scalars(statement).all(), total

    def find_by_mac(self, mac_address: str) -> DiscoveredDevice | None:
        statement = select(DiscoveredDevice).where(func.lower(DiscoveredDevice.mac_address) == mac_address.lower())
        return self.db.scalar(statement)

    def find_by_approved_device(self, device_id: UUID) -> DiscoveredDevice | None:
        return self.db.scalar(select(DiscoveredDevice).where(DiscoveredDevice.approved_device_id == device_id))

    def find_by_ip_hostname(self, ip_address: str, hostname: str) -> DiscoveredDevice | None:
        statement = select(DiscoveredDevice).where(
            DiscoveredDevice.ip_address == ip_address,
            func.lower(DiscoveredDevice.hostname) == hostname.lower(),
        )
        return self.db.scalar(statement)

    def find_by_ip(self, ip_address: str) -> DiscoveredDevice | None:
        statement = (
            select(DiscoveredDevice)
            .where(DiscoveredDevice.ip_address == ip_address)
            .order_by(DiscoveredDevice.last_seen_at.desc())
            .limit(1)
        )
        return self.db.scalar(statement)

    def find_inventory_by_mac(self, mac_address: str) -> Device | None:
        return self.db.scalar(select(Device).where(func.lower(Device.mac_address) == mac_address.lower()))

    def find_inventory_by_ip_hostname(self, ip_address: str, hostname: str) -> Device | None:
        statement = select(Device).where(
            Device.ip_address == ip_address,
            func.lower(Device.hostname) == hostname.lower(),
        )
        return self.db.scalar(statement)

    def find_inventory_by_ip(self, ip_address: str) -> Device | None:
        return self.db.scalar(select(Device).where(Device.ip_address == ip_address).limit(1))

    def statistics(self) -> dict[str, int]:
        today = datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)
        row = self.db.execute(
            select(
                func.count(DiscoveredDevice.id),
                func.count(DiscoveredDevice.id).filter(DiscoveredDevice.status == "online"),
                func.count(DiscoveredDevice.id).filter(DiscoveredDevice.status == "offline"),
                func.count(DiscoveredDevice.id).filter(DiscoveredDevice.status == "unknown"),
                func.count(DiscoveredDevice.id).filter(DiscoveredDevice.review_status == "pending"),
                func.count(DiscoveredDevice.id).filter(DiscoveredDevice.review_status == "approved"),
                func.count(DiscoveredDevice.id).filter(DiscoveredDevice.review_status == "ignored"),
                func.count(DiscoveredDevice.id).filter(DiscoveredDevice.review_status == "rejected"),
                func.count(DiscoveredDevice.id).filter(DiscoveredDevice.approved_device_id.is_not(None)),
                func.count(DiscoveredDevice.id).filter(DiscoveredDevice.first_seen_at >= today),
            )
        ).one()
        return {
            "total_devices": row[0],
            "online": row[1],
            "offline": row[2],
            "unknown": row[3],
            "pending_review": row[4],
            "approved": row[5],
            "ignored": row[6],
            "rejected": row[7],
            "matched_inventory": row[8],
            "new_today": row[9],
        }

    def delete(self, device: DiscoveredDevice) -> None:
        self.db.delete(device)


class DiscoveryRunRepository:
    """Persistence operations for discovery-run records; no orchestration."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, run: DiscoveryRun) -> DiscoveryRun:
        self.db.add(run)
        return run

    def get(self, run_id: UUID) -> DiscoveryRun | None:
        return self.db.get(DiscoveryRun, run_id)

    def list(self, *, offset: int = 0, limit: int = 100) -> Sequence[DiscoveryRun]:
        statement = select(DiscoveryRun).order_by(DiscoveryRun.started_at.desc()).offset(offset).limit(limit)
        return self.db.scalars(statement).all()

    def latest(self) -> DiscoveryRun | None:
        return self.db.scalar(select(DiscoveryRun).order_by(DiscoveryRun.started_at.desc()).limit(1))

    def count(self) -> int:
        return self.db.scalar(select(func.count(DiscoveryRun.id))) or 0

    def delete(self, run: DiscoveryRun) -> None:
        self.db.delete(run)
