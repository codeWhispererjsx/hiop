from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.discovered_device import DiscoveredDevice
from app.models.inventory_import import ImportLocationSuggestion, ImportMatchCandidate, ImportedDevice


class ImportMatchingRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def rows_to_match(self, session_id: UUID) -> Sequence[ImportedDevice]:
        return self.db.scalars(select(ImportedDevice).where(ImportedDevice.import_session_id == session_id, ImportedDevice.validation_status.in_(("valid", "warning", "duplicate"))).order_by(ImportedDevice.source_row_number)).all()

    def inventory_candidates(self, row: ImportedDevice, limit: int = 50) -> Sequence[Device]:
        filters = []
        for field in ("mac_address", "asset_tag", "serial_number", "hostname", "ip_address"):
            value = getattr(row, field, None)
            if value: filters.append(func.lower(getattr(Device, field)) == value.lower())
        if row.hostname and len(row.hostname) >= 3: filters.append(Device.hostname.ilike(f"{row.hostname[:6]}%"))
        if not filters: return []
        return self.db.scalars(select(Device).where(or_(*filters)).limit(limit)).all()

    def discovery_candidates(self, row: ImportedDevice, limit: int = 50) -> Sequence[DiscoveredDevice]:
        filters = []
        for field in ("mac_address", "hostname", "ip_address"):
            value = getattr(row, field, None)
            if value: filters.append(func.lower(getattr(DiscoveredDevice, field)) == value.lower())
        if row.hostname and len(row.hostname) >= 3: filters.append(DiscoveredDevice.hostname.ilike(f"{row.hostname[:6]}%"))
        if not filters: return []
        return self.db.scalars(select(DiscoveredDevice).where(or_(*filters)).limit(limit)).all()

    @staticmethod
    def _batch_filters(model, rows: Sequence[ImportedDevice], fields: tuple[str, ...]):
        filters = []
        for field in fields:
            values = {str(getattr(row, field)).lower() for row in rows if getattr(row, field, None)}
            if values: filters.append(func.lower(getattr(model, field)).in_(values))
        prefixes = {row.hostname[:6].lower() for row in rows if row.hostname and len(row.hostname) >= 3}
        filters.extend(model.hostname.ilike(f"{prefix}%") for prefix in prefixes)
        return filters

    def batch_candidate_pools(self, rows: Sequence[ImportedDevice], limit: int = 1000):
        if not rows: return {}
        inventory_filters = self._batch_filters(Device, rows, ("mac_address", "asset_tag", "serial_number", "hostname", "ip_address"))
        discovery_filters = self._batch_filters(DiscoveredDevice, rows, ("mac_address", "hostname", "ip_address"))
        staged_filters = self._batch_filters(ImportedDevice, rows, ("mac_address", "asset_tag", "serial_number", "hostname", "ip_address"))
        inventory = self.db.scalars(select(Device).where(or_(*inventory_filters)).limit(limit)).all() if inventory_filters else []
        discovery = self.db.scalars(select(DiscoveredDevice).where(or_(*discovery_filters)).limit(limit)).all() if discovery_filters else []
        staged = self.db.scalars(select(ImportedDevice).where(ImportedDevice.import_session_id == rows[0].import_session_id, or_(*staged_filters)).limit(limit)).all() if staged_filters else []

        def relevant(row, target, fields):
            return any(getattr(row, field, None) and getattr(target, field, None) and str(getattr(row, field)).lower() == str(getattr(target, field)).lower() for field in fields) or bool(row.hostname and getattr(target, "hostname", None) and target.hostname.lower().startswith(row.hostname[:6].lower()))

        return {
            row.id: (
                [item for item in inventory if relevant(row, item, ("mac_address", "asset_tag", "serial_number", "hostname", "ip_address"))][:50],
                [item for item in discovery if relevant(row, item, ("mac_address", "hostname", "ip_address"))][:50],
                [item for item in staged if item.id != row.id and relevant(row, item, ("mac_address", "asset_tag", "serial_number", "hostname", "ip_address"))][:50],
            ) for row in rows
        }

    def staged_candidates(self, row: ImportedDevice, limit: int = 50) -> Sequence[ImportedDevice]:
        filters = []
        for field in ("mac_address", "asset_tag", "serial_number", "hostname", "ip_address"):
            value = getattr(row, field, None)
            if value: filters.append(func.lower(getattr(ImportedDevice, field)) == value.lower())
        if row.hostname and len(row.hostname) >= 3: filters.append(ImportedDevice.hostname.ilike(f"{row.hostname[:6]}%"))
        if not filters: return []
        return self.db.scalars(select(ImportedDevice).where(ImportedDevice.import_session_id == row.import_session_id, ImportedDevice.id != row.id, or_(*filters)).limit(limit)).all()

    def replace_candidates(self, row_id: UUID, candidates: Sequence[ImportMatchCandidate]) -> None:
        self.db.execute(delete(ImportMatchCandidate).where(ImportMatchCandidate.imported_device_id == row_id, ImportMatchCandidate.match_status == "pending"))
        self.db.add_all(candidates)

    def get_candidate(self, candidate_id: UUID) -> ImportMatchCandidate | None:
        return self.db.get(ImportMatchCandidate, candidate_id)

    def candidates_for_row(self, session_id: UUID, row_id: UUID) -> Sequence[ImportMatchCandidate]:
        return self.db.scalars(select(ImportMatchCandidate).where(ImportMatchCandidate.import_session_id == session_id, ImportMatchCandidate.imported_device_id == row_id).order_by(ImportMatchCandidate.match_score.desc(), ImportMatchCandidate.created_at)).all()

    def reviewed_target_keys(self, row_id: UUID) -> set[tuple[str, UUID]]:
        candidates = self.db.scalars(select(ImportMatchCandidate).where(ImportMatchCandidate.imported_device_id == row_id, ImportMatchCandidate.match_status != "pending")).all()
        result = set()
        for item in candidates:
            target = item.candidate_device_id or item.candidate_discovery_id or item.candidate_imported_device_id
            if target: result.add((item.candidate_type.value, target))
        return result

    def page_candidates(self, session_id: UUID, *, level=None, status=None, action=None, minimum_score=0, has_conflicts=None, offset=0, limit=25):
        filters = [ImportMatchCandidate.import_session_id == session_id, ImportMatchCandidate.match_score >= minimum_score]
        if level: filters.append(ImportMatchCandidate.match_level == level)
        if status: filters.append(ImportMatchCandidate.match_status == status)
        if action: filters.append(ImportMatchCandidate.recommended_action == action)
        if has_conflicts is True: filters.append(func.jsonb_array_length(ImportMatchCandidate.conflicting_fields) > 0)
        if has_conflicts is False: filters.append(func.jsonb_array_length(ImportMatchCandidate.conflicting_fields) == 0)
        total = self.db.scalar(select(func.count(ImportMatchCandidate.id)).where(*filters)) or 0
        rows = self.db.scalars(select(ImportMatchCandidate).where(*filters).order_by(ImportMatchCandidate.match_score.desc()).offset(offset).limit(limit)).all()
        return rows, total

    def suggestion_for_row(self, row_id: UUID) -> ImportLocationSuggestion | None:
        return self.db.scalar(select(ImportLocationSuggestion).where(ImportLocationSuggestion.imported_device_id == row_id))
