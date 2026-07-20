from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.discovered_device import DiscoveredDevice, DiscoveryRun


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
        return self.db.scalars(select(DiscoveredDevice).offset(offset).limit(limit)).all()

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

    def delete(self, run: DiscoveryRun) -> None:
        self.db.delete(run)
