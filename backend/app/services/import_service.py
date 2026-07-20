from collections.abc import Iterable, Mapping
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.inventory_import import ImportSession
from app.repositories.import_repository import ImportedDeviceRepository, ImportSessionRepository


class ImportService:
    """Reserved orchestration boundary for future inventory import phases."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.sessions = ImportSessionRepository(db)
        self.devices = ImportedDeviceRepository(db)

    def create_import_session(self, *, filename: str, original_filename: str, import_type: str, file_format: str, uploaded_by: str | None) -> ImportSession:
        raise NotImplementedError("Import session creation is deferred to Epic 2B")

    def validate_import_file(self, session_id: UUID) -> None:
        raise NotImplementedError("File validation is deferred to Epic 2B")

    def store_import_rows(self, session_id: UUID, rows: Iterable[Mapping[str, Any]]) -> None:
        raise NotImplementedError("Import row storage is deferred to Epic 2B")

    def process_import(self, session_id: UUID) -> None:
        raise NotImplementedError("Import processing is deferred to Epic 2B")

    def finalize_import(self, session_id: UUID) -> None:
        raise NotImplementedError("Import finalization is deferred to Epic 2B")
