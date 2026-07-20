from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.imports.matching import score_records, select_hostname_rule, select_subnet_rule
from app.models.hierarchy import Building, Department, Floor, NetworkZone, Room
from app.models.discovered_device import DiscoveredDevice
from app.models.inventory_import import (
    ImportCandidateType,
    ImportLocationSuggestion,
    ImportMatchCandidate,
    ImportMatchStatus,
    ImportRecommendedAction,
    ImportSessionStatus,
    ImportedDevice,
    LocationSuggestionStatus,
)
from app.models.user import User
from app.repositories.import_matching_repository import ImportMatchingRepository
from app.repositories.import_repository import ImportSessionRepository, ImportedDeviceRepository
from app.services.audit_service import create_audit_log
from app.services.settings_service import read_import_settings
from app.websocket.connection_manager import manager


class MatchingNotFoundError(ValueError): pass
class MatchingConflictError(ValueError): pass
class MatchingValidationError(ValueError): pass


class ImportMatchingService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.sessions = ImportSessionRepository(db)
        self.rows = ImportedDeviceRepository(db)
        self.repository = ImportMatchingRepository(db)

    def _session(self, session_id: UUID):
        session = self.sessions.get(session_id)
        if not session: raise MatchingNotFoundError("Import session not found")
        return session

    def _row(self, session_id: UUID, row_id: UUID) -> ImportedDevice:
        row = self.rows.get(row_id)
        if not row or row.import_session_id != session_id: raise MatchingNotFoundError("Imported row not found")
        return row

    @staticmethod
    def _event(event: str, session_id: UUID, **safe: Any) -> None:
        manager.broadcast_from_thread({"type": event, "session_id": str(session_id), **safe})

    def _candidate(self, session_id: UUID, row_id: UUID, candidate_id: UUID) -> ImportMatchCandidate:
        candidate = self.repository.get_candidate(candidate_id)
        if not candidate or candidate.import_session_id != session_id or candidate.imported_device_id != row_id:
            raise MatchingNotFoundError("Match candidate not found")
        return candidate

    def _location_suggestion(self, row: ImportedDevice, settings: dict[str, Any], best_target: Any | None = None) -> ImportLocationSuggestion | None:
        evidence, conflicts = [], []
        selected: dict[str, UUID | None] = {key: None for key in ("department_id", "building_id", "floor_id", "room_id", "network_zone_id")}
        hierarchy = (("department_name", Department, "department_id"), ("building_name", Building, "building_id"), ("floor_name", Floor, "floor_id"), ("room_name", Room, "room_id"), ("network_zone", NetworkZone, "network_zone_id"))
        for source_field, model, target_field in hierarchy:
            value = getattr(row, source_field)
            if not value: continue
            aliases = settings.get("hierarchy_aliases", {})
            lookup = aliases.get(source_field, {}).get(value.lower(), value)
            matches = self.db.scalars(select(model).where(model.is_active.is_(True), func.lower(model.name) == lookup.lower()).limit(2)).all()
            if len(matches) == 1:
                selected[target_field] = matches[0].id
                evidence.append({"field": source_field, "source": "exact_hierarchy", "value": value, "confidence": 95})
            elif len(matches) > 1:
                conflicts.append({"field": source_field, "code": "ambiguous_hierarchy", "candidate_count": len(matches)})
            elif settings["fuzzy_matching_enabled"]:
                candidates = self.db.scalars(select(model).where(model.is_active.is_(True), model.name.ilike(f"{lookup[:3]}%")).limit(10)).all() if len(lookup) >= 3 else []
                ranked = sorted(((round(SequenceMatcher(None, lookup.lower(), item.name.lower()).ratio() * 100), item) for item in candidates), reverse=True, key=lambda pair: pair[0])
                threshold = settings["fuzzy_similarity_threshold"]
                if ranked and ranked[0][0] >= threshold and (len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= 5):
                    selected[target_field] = ranked[0][1].id
                    evidence.append({"field": source_field, "source": "fuzzy_hierarchy", "similarity": ranked[0][0], "confidence": 70})
                elif ranked and ranked[0][0] >= threshold:
                    conflicts.append({"field": source_field, "code": "ambiguous_hierarchy", "candidate_count": len(ranked)})
        if best_target is not None:
            for field in ("department_id", "room_id", "network_zone_id"):
                value = getattr(best_target, field, None)
                if value and selected[field] is None: selected[field] = value
            source = "inventory_match" if hasattr(best_target, "asset_tag") and not hasattr(best_target, "discovery_method") else "discovery_match"
            if any(selected.values()): evidence.append({"field": "matched_record", "source": source, "confidence": 80})
        if row.ip_address and settings["subnet_mapping_enabled"]:
            try:
                rule = select_subnet_rule(row.ip_address, settings.get("subnet_mapping_rules", []))
                if rule:
                    for field in selected:
                        if rule.get(field): selected[field] = UUID(rule[field])
                    evidence.append({"field": "ip_address", "source": "subnet_rule", "rule": rule.get("name", rule["cidr"]), "confidence": 85})
            except (ValueError, TypeError):
                conflicts.append({"field": "ip_address", "code": "invalid_subnet_rule"})
        if row.hostname and settings["hostname_rule_mapping_enabled"]:
            rule = select_hostname_rule(row.hostname, settings.get("hostname_mapping_rules", []))
            if rule:
                for field in selected:
                    if rule.get(field) and selected[field] is None: selected[field] = UUID(rule[field])
                evidence.append({"field": "hostname", "source": "hostname_rule", "rule": rule.get("name", rule["pattern"]), "confidence": 75})
        if not evidence and not conflicts: return None
        confidence = max((item["confidence"] for item in evidence), default=0)
        existing = self.repository.suggestion_for_row(row.id)
        suggestion = existing or ImportLocationSuggestion(imported_device_id=row.id, confidence_score=confidence)
        for field, value in selected.items(): setattr(suggestion, field, value)
        suggestion.confidence_score, suggestion.evidence, suggestion.conflicts = confidence, evidence, conflicts
        suggestion.status = LocationSuggestionStatus.PENDING
        if not existing: self.db.add(suggestion)
        return suggestion

    def run(self, session_id: UUID, actor: User, *, recompute: bool = False) -> dict[str, Any]:
        session = self._session(session_id)
        if session.matching_state == "running": raise MatchingConflictError("Matching is already running")
        if session.status not in {ImportSessionStatus.COMPLETED, ImportSessionStatus.PARTIAL}:
            raise MatchingValidationError("Import session must be validated before matching")
        session.matching_state = "running"
        action = "IMPORT_MATCHING_RECOMPUTED" if recompute else "IMPORT_MATCHING_STARTED"
        create_audit_log(self.db, actor.username, action, "ImportSession", str(session.id), "Started staged inventory matching")
        self.db.commit()
        self._event("import_matching_started", session_id)
        settings = read_import_settings(self.db)
        counts = Counter({key: 0 for key in ("exact", "strong", "probable", "weak", "unmatched", "conflicts", "resolved", "suggested_new_devices", "suggested_locations")})
        rows = self.repository.rows_to_match(session_id)
        try:
            batch_size = settings["candidate_recomputation_batch_size"]
            indexed_rows = list(enumerate(rows, start=1))
            for batch_start in range(0, len(indexed_rows), batch_size):
                batch = indexed_rows[batch_start:batch_start + batch_size]
                pools_by_row = self.repository.batch_candidate_pools([row for _, row in batch], limit=max(1000, batch_size * settings["maximum_candidates_per_row"] * 3))
                for index, row in batch:
                    if row.resolution_action:
                        counts["resolved"] += 1
                        counts["suggested_new_devices"] += int(row.resolution_action == "create_new")
                        continue
                    scored = []
                    inventory_pool, discovery_pool, staged_pool = pools_by_row.get(row.id, ([], [], []))
                    pools = (
                        (ImportCandidateType.INVENTORY_DEVICE, inventory_pool),
                        (ImportCandidateType.DISCOVERED_DEVICE, discovery_pool),
                        (ImportCandidateType.IMPORTED_DEVICE, staged_pool),
                    )
                    seen = self.repository.reviewed_target_keys(row.id)
                    for candidate_type, candidates in pools:
                        for target in candidates:
                            key = (candidate_type.value, target.id)
                            if key in seen: continue
                            seen.add(key)
                            result = score_records(row, target, settings)
                            if result["level"] == "none": continue
                            scored.append((result["score"], candidate_type, target, result))
                    scored.sort(key=lambda item: (-item[0], item[1].value, str(item[2].id)))
                    models = []
                    for _, candidate_type, target, result in scored[:settings["maximum_candidates_per_row"]]:
                        kwargs = {"candidate_device_id": None, "candidate_discovery_id": None, "candidate_imported_device_id": None}
                        target_key = {ImportCandidateType.INVENTORY_DEVICE: "candidate_device_id", ImportCandidateType.DISCOVERED_DEVICE: "candidate_discovery_id", ImportCandidateType.IMPORTED_DEVICE: "candidate_imported_device_id"}[candidate_type]
                        kwargs[target_key] = target.id
                        models.append(ImportMatchCandidate(import_session_id=session_id, imported_device_id=row.id, candidate_type=candidate_type, match_score=result["score"], match_level=result["level"], evidence=result["evidence"], conflicting_fields=result["conflicts"], matching_fields=result["matching_fields"], recommended_action=result["recommended_action"], **kwargs))
                    self.repository.replace_candidates(row.id, models)
                    if scored:
                        best = scored[0][3]
                        counts[best["level"]] += 1
                        if best["conflicts"]: counts["conflicts"] += 1
                    else: counts["unmatched"] += 1
                    best_target = scored[0][2] if scored else None
                    if settings["auto_suggestion_enabled"] and self._location_suggestion(row, settings, best_target): counts["suggested_locations"] += 1
                    if index % batch_size == 0:
                        self.db.commit()
                        self._event("import_matching_progress", session_id, processed=index, total=len(rows))
            counts["total_valid_rows"] = len(rows)
            session = self._session(session_id)
            session.matching_state = "completed"
            session.matched_rows = len(rows) - counts["unmatched"]
            session.match_summary = dict(counts)
            create_audit_log(self.db, actor.username, "IMPORT_MATCHING_COMPLETED", "ImportSession", str(session.id), f"Matched {session.matched_rows} of {len(rows)} staged rows")
            self.db.commit()
            self._event("import_matching_completed", session_id, summary=dict(counts))
            return dict(counts)
        except Exception:
            self.db.rollback()
            session = self._session(session_id)
            session.matching_state = "failed"
            self.db.commit()
            raise

    def matches(self, session_id: UUID, **filters) -> dict[str, Any]:
        self._session(session_id)
        page, page_size = filters.pop("page"), filters.pop("page_size")
        items, total = self.repository.page_candidates(session_id, offset=(page - 1) * page_size, limit=page_size, **filters)
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def row_matches(self, session_id: UUID, row_id: UUID):
        self._row(session_id, row_id)
        return self.repository.candidates_for_row(session_id, row_id)

    def merge_plan(self, session_id: UUID, row_id: UUID, candidate_id: UUID | None = None, actor: User | None = None) -> dict[str, Any]:
        row = self._row(session_id, row_id)
        candidates = self.repository.candidates_for_row(session_id, row_id)
        candidate = self._candidate(session_id, row_id, candidate_id) if candidate_id else next((item for item in candidates if item.candidate_device_id), None)
        if not candidate or not candidate.candidate_device_id: raise MatchingValidationError("An inventory candidate is required for a merge plan")
        device = self.db.get(__import__("app.models.device", fromlist=["Device"]).Device, candidate.candidate_device_id)
        fields = ("asset_tag", "hostname", "ip_address", "mac_address", "serial_number", "brand", "model", "inventory_status")
        updates, preserved, conflicts = [], [], []
        for field in fields:
            imported, current = getattr(row, field, None), getattr(device, field, None)
            if imported and not current: updates.append({"field": field, "value": imported})
            elif current and not imported: preserved.append({"field": field, "value": current})
            elif imported and current and str(imported).lower() != str(current).lower(): conflicts.append({"field": field, "imported": imported, "inventory": current})
        plan = {"imported_device_id": row.id, "inventory_device_id": device.id, "matching_fields": candidate.matching_fields, "conflicts": conflicts, "fields_to_enrich": updates, "fields_preserved": preserved, "discovery_device_id": row.linked_discovery_id, "audit_required": True, "destructive": False}
        if actor:
            create_audit_log(self.db, actor.username, "IMPORT_MERGE_PLAN_REVIEWED", "ImportedDevice", str(row.id), "Reviewed a non-destructive import merge plan")
            self.db.commit()
        return plan

    def resolve_candidate(self, session_id: UUID, row_id: UUID, candidate_id: UUID, actor: User, *, accept: bool) -> ImportMatchCandidate:
        row = self._row(session_id, row_id)
        candidate = self._candidate(session_id, row_id, candidate_id)
        if candidate.match_status != ImportMatchStatus.PENDING: raise MatchingConflictError("Candidate has already been reviewed")
        if accept and row.resolution_action: raise MatchingConflictError("Imported row already has a resolution")
        candidate.match_status = ImportMatchStatus.ACCEPTED if accept else ImportMatchStatus.REJECTED
        candidate.reviewed_by, candidate.reviewed_at = actor.id, datetime.now(timezone.utc)
        if accept:
            row.resolution_action = "linked"
            row.linked_device_id = candidate.candidate_device_id
            row.linked_discovery_id = candidate.candidate_discovery_id
            if candidate.candidate_discovery_id:
                discovery = self.db.get(DiscoveredDevice, candidate.candidate_discovery_id)
                if discovery and discovery.approved_device_id: row.linked_device_id = discovery.approved_device_id
            row.resolved_by, row.resolved_at = actor.id, candidate.reviewed_at
            for other in self.repository.candidates_for_row(session_id, row_id):
                if other.id != candidate.id and other.match_status == ImportMatchStatus.PENDING: other.match_status = ImportMatchStatus.IGNORED
        create_audit_log(self.db, actor.username, "IMPORT_CANDIDATE_ACCEPTED" if accept else "IMPORT_CANDIDATE_REJECTED", "ImportMatchCandidate", str(candidate.id), "Reviewed an import match candidate")
        self.db.commit(); self.db.refresh(candidate)
        self._event("import_match_resolved", session_id, row_id=str(row_id), accepted=accept)
        return candidate

    def mark_create_new(self, session_id: UUID, row_id: UUID, actor: User) -> ImportedDevice:
        row = self._row(session_id, row_id)
        if row.resolution_action: raise MatchingConflictError("Imported row already has a resolution")
        row.resolution_action, row.resolved_by, row.resolved_at = "create_new", actor.id, datetime.now(timezone.utc)
        create_audit_log(self.db, actor.username, "IMPORT_ROW_CREATE_NEW", "ImportedDevice", str(row.id), "Marked staged row for later inventory creation")
        self.db.commit(); self.db.refresh(row)
        self._event("import_match_resolved", session_id, row_id=str(row_id), action="create_new")
        return row

    def review_location(self, session_id: UUID, row_id: UUID, actor: User, action: str, overrides: dict[str, UUID | None]) -> ImportLocationSuggestion:
        self._row(session_id, row_id)
        suggestion = self.repository.suggestion_for_row(row_id)
        if not suggestion: raise MatchingNotFoundError("Location suggestion not found")
        if action not in {"accept", "reject", "override"}: raise MatchingValidationError("Invalid location action")
        if action == "override":
            if not any(overrides.values()): raise MatchingValidationError("An override must select at least one hierarchy value")
            models = {"department_id": Department, "building_id": Building, "floor_id": Floor, "room_id": Room, "network_zone_id": NetworkZone}
            for field, value in overrides.items():
                if value and not self.db.scalar(select(models[field].id).where(models[field].id == value, models[field].is_active.is_(True))):
                    raise MatchingValidationError(f"Selected {field.removesuffix('_id').replace('_', ' ')} does not exist")
                setattr(suggestion, field, value)
        suggestion.status = {"accept": LocationSuggestionStatus.ACCEPTED, "reject": LocationSuggestionStatus.REJECTED, "override": LocationSuggestionStatus.OVERRIDDEN}[action]
        suggestion.reviewed_by, suggestion.reviewed_at = actor.id, datetime.now(timezone.utc)
        create_audit_log(self.db, actor.username, f"IMPORT_LOCATION_{action.upper()}", "ImportLocationSuggestion", str(suggestion.id), f"Location suggestion {action}ed")
        self.db.commit(); self.db.refresh(suggestion)
        self._event("import_location_suggestion_updated", session_id, row_id=str(row_id), status=suggestion.status.value)
        return suggestion
