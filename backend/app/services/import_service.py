import csv
import io
import logging
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.imports.columns import detect_mapping, validate_mapping
from app.imports.parsers import ImportFileError, ParsedFile, detect_format, parse_file
from app.models.inventory_import import ImportedDevice, ImportSession, ImportSessionStatus, ImportValidationStatus
from app.models.user import User
from app.repositories.import_repository import ImportedDeviceRepository, ImportSessionRepository
from app.services.audit_service import create_audit_log
from app.services.import_validation import validate_row
from app.services.settings_service import read_import_settings


logger = logging.getLogger(__name__)
STORAGE_ROOT = Path(tempfile.gettempdir()) / "hiop-imports"


class ImportNotFoundError(ValueError): pass
class ImportConflictError(ValueError): pass
class ImportValidationError(ValueError): pass


def _csv_safe(value: Any) -> str:
    text = str(value) if value is not None else ""
    return f"'{text}" if text.startswith(("=", "+", "-", "@")) else text


class ImportService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.sessions = ImportSessionRepository(db)
        self.devices = ImportedDeviceRepository(db)

    def _settings(self) -> dict[str, Any]:
        return read_import_settings(self.db)

    def _session(self, session_id: UUID) -> ImportSession:
        session = self.sessions.get(session_id)
        if not session:
            raise ImportNotFoundError("Import session not found")
        return session

    def _path(self, session: ImportSession) -> Path:
        return STORAGE_ROOT / session.filename

    def _remove_file(self, session: ImportSession) -> None:
        try:
            self._path(session).unlink(missing_ok=True)
        except OSError:
            logger.warning("Temporary import file cleanup failed session=%s", session.id)

    def create_import_session(self, *, original_filename: str, content_type: str | None, content: bytes, uploader: User) -> tuple[ImportSession, dict]:
        config = self._settings()
        if not content:
            raise ImportValidationError("The uploaded file is empty")
        if len(content) > config["maximum_import_file_size"]:
            raise ImportValidationError("The uploaded file exceeds the configured size limit")
        display_name = Path(original_filename or "").name
        if not display_name or display_name in {".", ".."}:
            raise ImportValidationError("A valid filename is required")
        try:
            file_format = detect_format(display_name, content_type, content[:8192])
        except ImportFileError as exc:
            raise ImportValidationError(str(exc)) from exc
        if file_format not in config["supported_formats"]:
            raise ImportValidationError("File format is disabled by configuration")
        STORAGE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        safe_name = f"{uuid4().hex}.{file_format}"
        path = STORAGE_ROOT / safe_name
        path.write_bytes(content)
        try:
            parsed = parse_file(path, file_format, config)
            mapping = detect_mapping(parsed.headers)
            session = ImportSession(
                filename=safe_name, original_filename=display_name[:255], import_type="device_inventory",
                file_format=file_format, uploaded_by=uploader.id, selected_worksheet=parsed.selected_worksheet,
                mapping_metadata={**mapping, "mapping": mapping["suggested_mapping"], "worksheet_names": parsed.worksheet_names},
            )
            self.sessions.add(session)
            self.db.flush()
            create_audit_log(self.db, uploader.username, "IMPORT_FILE_UPLOADED", "ImportSession", str(session.id), f"Uploaded {file_format.upper()} inventory file {session.original_filename}")
            self.db.commit(); self.db.refresh(session)
            return session, self._preview(parsed, config)
        except Exception:
            path.unlink(missing_ok=True)
            self.db.rollback()
            raise

    def _preview(self, parsed: ParsedFile, config: dict) -> dict:
        detection = detect_mapping(parsed.headers)
        preview_rows = []
        usable_mapping = not detection["ambiguous_mappings"] and not detection["missing_required_columns"]
        if usable_mapping:
            mapping = validate_mapping(parsed.headers, detection["suggested_mapping"])
        for number, raw, parser_warnings in parsed.rows[:config["preview_rows"]]:
            normalized, errors, warnings = validate_row(raw, mapping) if usable_mapping else ({}, [], [])
            preview_rows.append({"source_row_number": number, "raw_data": raw, "normalized_data": normalized, "errors": errors, "warnings": warnings + parser_warnings})
        return {
            "detected_file_type": parsed.file_format, "worksheet_names": parsed.worksheet_names,
            "selected_worksheet": parsed.selected_worksheet, "detected_headers": parsed.headers,
            **detection,
            "rows": preview_rows,
            "validation_summary": {"previewed": min(len(parsed.rows), config["preview_rows"]), "total_rows": len(parsed.rows)},
            "warning_summary": {"parser_warnings": sum(len(item[2]) for item in parsed.rows[:config["preview_rows"]])},
        }

    def columns(self, session_id: UUID, worksheet: str | None = None) -> dict:
        session = self._session(session_id)
        if worksheet and worksheet != session.selected_worksheet:
            worksheets = session.mapping_metadata.get("worksheet_names", [])
            if worksheet not in worksheets:
                raise ImportValidationError("Selected worksheet does not exist")
            parsed = parse_file(self._path(session), session.file_format, self._settings(), worksheet)
            return {**detect_mapping(parsed.headers), "worksheet_names": worksheets, "selected_worksheet": worksheet, "preview": self._preview(parsed, self._settings())}
        result = dict(session.mapping_metadata)
        if session.status == ImportSessionStatus.UPLOADED and self._path(session).exists():
            parsed = parse_file(self._path(session), session.file_format, self._settings(), session.selected_worksheet)
            result["preview"] = self._preview(parsed, self._settings())
        return result

    def list_sessions(self, *, search: str | None, status: str | None, page: int, page_size: int) -> dict:
        items, total = self.sessions.page(search=search, status=status, offset=(page - 1) * page_size, limit=page_size)
        counts = self.devices.validation_counts([item.id for item in items])
        for item in items: item._validation_summary = counts.get(item.id, {})
        return {"items": items, "total": total, "page": page, "page_size": page_size, "pages": max(1, (total + page_size - 1) // page_size)}

    def save_mapping(self, session_id: UUID, mapping: dict[str, str | None], worksheet: str | None, actor: User) -> dict:
        session = self._session(session_id)
        if session.status != ImportSessionStatus.UPLOADED:
            raise ImportConflictError("Mapping can only be changed before validation")
        worksheets = session.mapping_metadata.get("worksheet_names", [])
        if worksheet is not None and worksheet not in worksheets:
            raise ImportValidationError("Selected worksheet does not exist")
        headers = list(session.mapping_metadata.get("headers", []))
        if worksheet and worksheet != session.selected_worksheet:
            parsed = parse_file(self._path(session), session.file_format, self._settings(), worksheet)
            headers = parsed.headers
        cleaned = validate_mapping(headers, mapping)
        detection = detect_mapping(headers)
        session.mapping_metadata = {**session.mapping_metadata, **detection, "mapping": cleaned, "ambiguous_mappings": {}, "missing_required_columns": []}
        session.selected_worksheet = worksheet or session.selected_worksheet
        create_audit_log(self.db, actor.username, "IMPORT_MAPPING_CHANGED", "ImportSession", str(session.id), "Updated inventory import column mapping")
        self.db.commit(); self.db.refresh(session)
        return session.mapping_metadata

    @staticmethod
    def _duplicate_key(normalized: dict[str, Any]) -> list[tuple[str, Any]]:
        keys = []
        if normalized.get("mac_address"): keys.append(("mac_address", normalized["mac_address"]))
        if normalized.get("asset_tag"): keys.append(("asset_tag", normalized["asset_tag"].lower()))
        if normalized.get("serial_number"): keys.append(("serial_number", normalized["serial_number"].lower()))
        if normalized.get("ip_address") and normalized.get("hostname"): keys.append(("ip_hostname", (normalized["ip_address"], normalized["hostname"])))
        keys.append(("exact_row", tuple((field, normalized.get(field)) for field in sorted(normalized))))
        return keys

    def process_import(self, session_id: UUID, actor: User) -> ImportSession:
        session = self._session(session_id)
        if session.status in {ImportSessionStatus.VALIDATING, ImportSessionStatus.PROCESSING}:
            raise ImportConflictError("Import session is already processing")
        if session.status != ImportSessionStatus.UPLOADED:
            raise ImportConflictError("Only uploaded sessions can be validated")
        mapping = validate_mapping(list(session.mapping_metadata.get("headers", [])), session.mapping_metadata.get("mapping", {}))
        config = self._settings()
        session.status = ImportSessionStatus.VALIDATING
        session.processing_started_at = datetime.now(timezone.utc)
        create_audit_log(self.db, actor.username, "IMPORT_VALIDATION_STARTED", "ImportSession", str(session.id), "Started inventory import validation")
        self.db.commit()
        try:
            parsed = parse_file(self._path(session), session.file_format, config, session.selected_worksheet)
            session.status = ImportSessionStatus.PROCESSING
            session.total_rows = len(parsed.rows)
            self.devices.delete_for_session(session.id)
            self.db.commit()
            seen: dict[tuple[str, Any], int] = {}
            counts = Counter()
            batch_size = max(1, config["import_batch_size"])
            for index, (source_row, raw, parser_warnings) in enumerate(parsed.rows, start=1):
                normalized, errors, warnings = validate_row(raw, mapping)
                warnings.extend(parser_warnings)
                related = None
                duplicate_field = None
                for key in self._duplicate_key(normalized):
                    if key in seen:
                        duplicate_field, related = key[0], seen[key]
                        break
                for key in self._duplicate_key(normalized):
                    seen.setdefault(key, source_row)
                if related is not None:
                    warnings.append({"field": duplicate_field, "code": "duplicate_in_file", "message": f"Duplicates source row {related}", "related_row_number": related})
                status = ImportValidationStatus.INVALID if errors else ImportValidationStatus.DUPLICATE if related is not None else ImportValidationStatus.WARNING if warnings else ImportValidationStatus.VALID
                device = ImportedDevice(import_session_id=session.id, source_row_number=source_row, raw_data=raw, normalized_data=normalized, errors=errors, warnings=warnings, validation_status=status, **normalized)
                self.devices.add(device)
                counts[status.value] += 1
                session.processed_rows = index
                if index % batch_size == 0:
                    self.db.commit()
            session.successful_rows = counts["valid"] + counts["warning"]
            session.failed_rows = counts["invalid"]
            session.duplicate_rows = counts["duplicate"]
            session.skipped_rows = 0
            session.processing_completed_at = datetime.now(timezone.utc)
            session.status = ImportSessionStatus.PARTIAL if session.failed_rows or session.duplicate_rows else ImportSessionStatus.COMPLETED
            session.error_summary = f"{session.failed_rows} invalid row(s), {session.duplicate_rows} duplicate row(s)" if session.status == ImportSessionStatus.PARTIAL else None
            create_audit_log(self.db, actor.username, "IMPORT_VALIDATION_COMPLETED", "ImportSession", str(session.id), f"Validated {session.total_rows} rows; {session.failed_rows} invalid; {session.duplicate_rows} duplicate")
            self.db.commit(); self.db.refresh(session)
            self._remove_file(session)
            return session
        except Exception as exc:
            self.db.rollback()
            session = self._session(session_id)
            session.status = ImportSessionStatus.FAILED
            session.processing_completed_at = datetime.now(timezone.utc)
            session.error_summary = "Import validation failed"
            create_audit_log(self.db, actor.username, "IMPORT_VALIDATION_FAILED", "ImportSession", str(session.id), "Inventory import validation failed")
            self.db.commit(); self._remove_file(session)
            if isinstance(exc, (ImportFileError, ImportValidationError, ImportConflictError)):
                raise ImportValidationError(str(exc)) from exc
            logger.exception("Import validation failed session=%s", session_id)
            raise ImportValidationError("Import validation failed") from exc

    def rows(self, session_id: UUID, **filters) -> dict:
        self._session(session_id)
        page, page_size = filters.pop("page"), filters.pop("page_size")
        error_code = filters.pop("error_code", None)
        if error_code:
            items, _ = self.devices.page_for_session(session_id, offset=0, limit=self._settings()["maximum_rows"], **filters)
            items = [item for item in items if any(issue.get("code") == error_code for issue in item.errors + item.warnings)]
            total = len(items)
            items = items[(page - 1) * page_size:page * page_size]
            return {"items": items, "total": total, "page": page, "page_size": page_size, "pages": max(1, (total + page_size - 1) // page_size)}
        items, total = self.devices.page_for_session(session_id, offset=(page - 1) * page_size, limit=page_size, **filters)
        return {"items": items, "total": total, "page": page, "page_size": page_size, "pages": max(1, (total + page_size - 1) // page_size)}

    def errors(self, session_id: UUID) -> dict:
        self._session(session_id)
        rows, _ = self.devices.page_for_session(session_id, offset=0, limit=self._settings()["maximum_rows"])
        grouped = Counter()
        entries = []
        for row in rows:
            for severity, issues in (("error", row.errors), ("warning", row.warnings)):
                for issue in issues:
                    grouped[(severity, issue.get("code", "unknown"))] += 1
                    entries.append({"source_row_number": row.source_row_number, "severity": severity, **issue})
        return {"summary": [{"severity": key[0], "code": key[1], "count": count} for key, count in grouped.items()], "items": entries}

    def export_errors(self, session_id: UUID) -> tuple[str, str]:
        report = self.errors(session_id)
        output = io.StringIO(newline="")
        writer = csv.writer(output); writer.writerow(["Source Row", "Severity", "Field", "Code", "Message", "Original Value"])
        for item in report["items"]:
            writer.writerow([_csv_safe(item.get(key)) for key in ("source_row_number", "severity", "field", "code", "message", "original_value")])
        return "\ufeff" + output.getvalue(), f"hiop-import-{session_id}-validation-errors.csv"

    def cancel(self, session_id: UUID, actor: User) -> ImportSession:
        session = self._session(session_id)
        if session.status in {ImportSessionStatus.VALIDATING, ImportSessionStatus.PROCESSING}:
            raise ImportConflictError("An active import cannot be cancelled")
        if session.status != ImportSessionStatus.UPLOADED:
            raise ImportConflictError("Only an unprocessed import can be cancelled")
        session.status = ImportSessionStatus.CANCELLED
        session.processing_completed_at = datetime.now(timezone.utc)
        session.error_summary = "Cancelled by administrator"
        create_audit_log(self.db, actor.username, "IMPORT_CANCELLED", "ImportSession", str(session.id), "Cancelled unprocessed inventory import")
        self.db.commit(); self.db.refresh(session); self._remove_file(session)
        return session
