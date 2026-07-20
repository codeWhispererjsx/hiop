from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.security import require_roles
from app.models.user import User
from app.schemas.inventory_import import ImportedDevicePage, ImportMappingRequest, ImportSessionResponse, ImportUploadResponse
from app.services.import_service import ImportConflictError, ImportNotFoundError, ImportService, ImportValidationError


router = APIRouter(prefix="/imports", tags=["Inventory Imports"])
admin = require_roles(["admin"])
reader = require_roles(["admin", "technician"])


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, ImportNotFoundError): return HTTPException(404, str(exc))
    if isinstance(exc, ImportConflictError): return HTTPException(409, str(exc))
    if isinstance(exc, ImportValidationError): return HTTPException(422, str(exc))
    if isinstance(exc, ValueError): return HTTPException(400, str(exc))
    return HTTPException(500, "Import operation failed")


@router.post("/device-inventory/upload", response_model=ImportUploadResponse, status_code=201)
async def upload_device_inventory(file: UploadFile = File(...), db: Session = Depends(get_db), actor: User = Depends(admin)):
    try:
        service = ImportService(db)
        maximum = service._settings()["maximum_import_file_size"]
        content = await file.read(maximum + 1)
        session, preview = service.create_import_session(original_filename=file.filename or "", content_type=file.content_type, content=content, uploader=actor)
        return {"session": session, "preview": preview}
    except Exception as exc:
        raise _error(exc) from exc
    finally:
        await file.close()


@router.get("/{session_id}", response_model=ImportSessionResponse)
def get_import_session(session_id: UUID, db: Session = Depends(get_db), _: User = Depends(reader)):
    try: return ImportService(db)._session(session_id)
    except Exception as exc: raise _error(exc) from exc


@router.get("/{session_id}/columns")
def get_import_columns(session_id: UUID, worksheet: str | None = Query(None, max_length=255), db: Session = Depends(get_db), _: User = Depends(reader)):
    try: return ImportService(db).columns(session_id, worksheet)
    except Exception as exc: raise _error(exc) from exc


@router.post("/{session_id}/mapping")
def save_import_mapping(session_id: UUID, payload: ImportMappingRequest, db: Session = Depends(get_db), actor: User = Depends(admin)):
    try: return ImportService(db).save_mapping(session_id, payload.mapping, payload.worksheet, actor)
    except Exception as exc: raise _error(exc) from exc


@router.post("/{session_id}/validate", response_model=ImportSessionResponse)
def validate_import(session_id: UUID, db: Session = Depends(get_db), actor: User = Depends(admin)):
    try: return ImportService(db).process_import(session_id, actor)
    except Exception as exc: raise _error(exc) from exc


@router.get("/{session_id}/rows", response_model=ImportedDevicePage)
def import_rows(session_id: UUID, validation_status: str | None = Query(None, pattern="^(pending|valid|warning|duplicate|invalid)$"), search: str | None = Query(None, max_length=200), source_row_number: int | None = Query(None, ge=1), error_code: str | None = Query(None, max_length=80), page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), db: Session = Depends(get_db), _: User = Depends(reader)):
    try: return ImportService(db).rows(session_id, status=validation_status, search=search, source_row_number=source_row_number, error_code=error_code, page=page, page_size=page_size)
    except Exception as exc: raise _error(exc) from exc


@router.get("/{session_id}/errors")
def import_errors(session_id: UUID, db: Session = Depends(get_db), _: User = Depends(reader)):
    try: return ImportService(db).errors(session_id)
    except Exception as exc: raise _error(exc) from exc


@router.get("/{session_id}/errors/export")
def export_import_errors(session_id: UUID, db: Session = Depends(get_db), _: User = Depends(reader)):
    try:
        content, filename = ImportService(db).export_errors(session_id)
        return StreamingResponse(iter([content]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    except Exception as exc: raise _error(exc) from exc


@router.post("/{session_id}/cancel", response_model=ImportSessionResponse)
def cancel_import(session_id: UUID, db: Session = Depends(get_db), actor: User = Depends(admin)):
    try: return ImportService(db).cancel(session_id, actor)
    except Exception as exc: raise _error(exc) from exc
