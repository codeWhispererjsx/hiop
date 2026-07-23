from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.models.inventory_import import ImportedDevice, ImportSession


class ImportSessionRepository:
    """Persistence operations for import sessions; no workflow rules."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, session: ImportSession) -> ImportSession:
        self.db.add(session)
        return session

    def get(self, session_id: UUID) -> ImportSession | None:
        return self.db.get(ImportSession, session_id)

    def list(self, *, offset: int = 0, limit: int = 100) -> Sequence[ImportSession]:
        statement = select(ImportSession).order_by(ImportSession.uploaded_at.desc()).offset(offset).limit(limit)
        return self.db.scalars(statement).all()

    def count(self) -> int:
        return self.db.scalar(select(func.count(ImportSession.id))) or 0

    def page(self, *, search: str | None = None, status: str | None = None, offset: int = 0, limit: int = 25):
        filters = []
        if search: filters.append(ImportSession.original_filename.ilike(f"%{search.strip()}%"))
        if status: filters.append(ImportSession.status == status)
        total = self.db.scalar(select(func.count(ImportSession.id)).where(*filters)) or 0
        statement = select(ImportSession).where(*filters).order_by(ImportSession.uploaded_at.desc()).offset(offset).limit(limit)
        return self.db.scalars(statement).all(), total


class ImportedDeviceRepository:
    """Persistence operations for staged imported devices; no matching rules."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, device: ImportedDevice) -> ImportedDevice:
        self.db.add(device)
        return device

    def add_all(self, devices: Sequence[ImportedDevice]) -> Sequence[ImportedDevice]:
        self.db.add_all(devices)
        return devices

    def get(self, device_id: UUID) -> ImportedDevice | None:
        return self.db.get(ImportedDevice, device_id)

    def list_for_session(self, session_id: UUID, *, offset: int = 0, limit: int = 100) -> Sequence[ImportedDevice]:
        statement = (
            select(ImportedDevice)
            .where(ImportedDevice.import_session_id == session_id)
            .order_by(ImportedDevice.imported_at, ImportedDevice.id)
            .offset(offset)
            .limit(limit)
        )
        return self.db.scalars(statement).all()

    def count_for_session(self, session_id: UUID) -> int:
        statement = select(func.count(ImportedDevice.id)).where(ImportedDevice.import_session_id == session_id)
        return self.db.scalar(statement) or 0

    def validation_counts(self, session_ids: Sequence[UUID]) -> dict[UUID, dict[str, int]]:
        if not session_ids: return {}
        rows = self.db.execute(select(ImportedDevice.import_session_id, ImportedDevice.validation_status, func.count(ImportedDevice.id)).where(ImportedDevice.import_session_id.in_(session_ids)).group_by(ImportedDevice.import_session_id, ImportedDevice.validation_status)).all()
        result: dict[UUID, dict[str, int]] = {}
        for session_id, status, count in rows: result.setdefault(session_id, {})[status.value] = count
        return result

    def page_for_session(self, session_id: UUID, *, status: str | None = None, search: str | None = None, source_row_number: int | None = None, offset: int = 0, limit: int = 25):
        filters = [ImportedDevice.import_session_id == session_id]
        if status:
            filters.append(ImportedDevice.validation_status == status)
        if source_row_number is not None:
            filters.append(ImportedDevice.source_row_number == source_row_number)
        if search:
            term = f"%{search.strip()}%"
            filters.append(or_(ImportedDevice.asset_tag.ilike(term), ImportedDevice.hostname.ilike(term), ImportedDevice.ip_address.ilike(term), ImportedDevice.mac_address.ilike(term), ImportedDevice.serial_number.ilike(term)))
        total = self.db.scalar(select(func.count(ImportedDevice.id)).where(*filters)) or 0
        statement = select(ImportedDevice).where(*filters).order_by(ImportedDevice.source_row_number).offset(offset).limit(limit)
        return self.db.scalars(statement).all(), total

    def delete_for_session(self, session_id: UUID) -> None:
        self.db.execute(delete(ImportedDevice).where(ImportedDevice.import_session_id == session_id))
