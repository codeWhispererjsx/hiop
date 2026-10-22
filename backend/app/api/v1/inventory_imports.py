from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.core.tenant import organization_context, property_context
from app.models.hierarchy import Building, Department, Floor, NetworkZone, Property, Room
from app.models.inventory_import import ImportedDevice, ImportSession
from app.models.user import User
from app.schemas.inventory_import import (
    CandidateResolutionRequest,
    FinalDispositionRequest,
    FinalizeRequest,
    ImportMappingRequest,
    ImportSessionPage,
    ImportSessionResponse,
    ImportUploadResponse,
    ImportedDevicePage,
    ImportedDeviceResponse,
    LocationReviewRequest,
    MatchCandidatePage,
    MatchCandidateResponse,
    RollbackRequest,
)
from app.services.import_finalization_service import (
    FinalizationConflictError,
    FinalizationNotFoundError,
    FinalizationValidationError,
    ImportFinalizationService,
)
from app.services.import_matching_service import (
    ImportMatchingService,
    MatchingConflictError,
    MatchingNotFoundError,
    MatchingValidationError,
)
from app.services.import_service import (
    MAX_IMPORT_FILE_SIZE,
    ImportConflictError,
    ImportNotFoundError,
    ImportService,
    ImportValidationError,
)

router = APIRouter(prefix="/imports", tags=["Inventory imports"])
reader = require_roles(["platformadmin", "admin"])
administrator = require_roles(["admin"])


def _session(
    db: Session,
    session_id: UUID,
    organization_id: UUID,
    property_id: UUID | None,
) -> ImportSession:
    session = db.get(ImportSession, session_id)
    if not session or session.mapping_metadata.get("tenant_organization_id") != str(organization_id):
        raise HTTPException(404, "Import session not found")
    raw_property_id = session.mapping_metadata.get("tenant_property_id")
    try:
        session_property_id = UUID(raw_property_id) if raw_property_id else None
    except ValueError as error:
        raise HTTPException(404, "Import session not found") from error
    if property_id is not None and session_property_id != property_id:
        raise HTTPException(404, "Import session not found")
    db.info["organization_id"] = organization_id
    db.info["property_id"] = property_id or session_property_id
    return session


def _translate_import_error(error: Exception) -> None:
    if isinstance(error, ImportNotFoundError):
        raise HTTPException(404, str(error)) from error
    if isinstance(error, ImportConflictError):
        raise HTTPException(409, str(error)) from error
    if isinstance(error, ImportValidationError):
        raise HTTPException(422, str(error)) from error
    raise error


def _translate_matching_error(error: Exception) -> None:
    if isinstance(error, MatchingNotFoundError):
        raise HTTPException(404, str(error)) from error
    if isinstance(error, MatchingConflictError):
        raise HTTPException(409, str(error)) from error
    if isinstance(error, MatchingValidationError):
        raise HTTPException(422, str(error)) from error
    raise error


def _translate_finalization_error(error: Exception) -> None:
    if isinstance(error, FinalizationNotFoundError):
        raise HTTPException(404, str(error)) from error
    if isinstance(error, FinalizationConflictError):
        raise HTTPException(409, str(error)) from error
    if isinstance(error, FinalizationValidationError):
        raise HTTPException(422, str(error)) from error
    raise error


@router.get("", response_model=ImportSessionPage)
def list_imports(
    search: str | None = Query(default=None, max_length=180),
    status: str | None = Query(default=None, max_length=32),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    _actor: User = Depends(reader),
    organization_id: UUID = Depends(organization_context),
    property_id: UUID | None = Depends(property_context),
):
    query = (
        db.query(ImportSession)
        .filter(ImportSession.mapping_metadata["tenant_organization_id"].as_string() == str(organization_id))
        .order_by(ImportSession.uploaded_at.desc())
    )
    if property_id:
        query = query.filter(ImportSession.mapping_metadata["tenant_property_id"].as_string() == str(property_id))
    if search:
        query = query.filter(ImportSession.original_filename.ilike(f"%{search.strip()}%"))
    if status:
        query = query.filter(ImportSession.status == status)
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    counts = ImportService(db).devices.validation_counts([item.id for item in items])
    for item in items:
        item._validation_summary = counts.get(item.id, {})
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


@router.post("/device-inventory/upload", response_model=ImportUploadResponse, status_code=201)
async def upload_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    actor: User = Depends(administrator),
    organization_id: UUID = Depends(organization_context),
    property_id: UUID | None = Depends(property_context),
):
    if property_id is None:
        raise HTTPException(400, "Select a property before uploading inventory so imported devices cannot become unassigned")
    content = await file.read(MAX_IMPORT_FILE_SIZE + 1)
    if len(content) > MAX_IMPORT_FILE_SIZE:
        raise HTTPException(413, "The uploaded file exceeds the configured size limit")
    try:
        session, preview = ImportService(db).create_import_session(
            original_filename=file.filename or "",
            content_type=file.content_type,
            content=content,
            uploader=actor,
            organization_id=organization_id,
            property_id=property_id,
        )
        return {"session": session, "preview": preview}
    except (ImportConflictError, ImportNotFoundError, ImportValidationError) as error:
        _translate_import_error(error)
    finally:
        await file.close()


@router.get("/{session_id}", response_model=ImportSessionResponse)
def get_import(
    session_id: UUID,
    db: Session = Depends(get_db),
    _actor: User = Depends(reader),
    organization_id: UUID = Depends(organization_context),
    property_id: UUID | None = Depends(property_context),
):
    return _session(db, session_id, organization_id, property_id)


@router.get("/{session_id}/columns")
def columns(
    session_id: UUID,
    worksheet: str | None = Query(default=None, max_length=255),
    db: Session = Depends(get_db),
    _actor: User = Depends(reader),
    organization_id: UUID = Depends(organization_context),
    property_id: UUID | None = Depends(property_context),
):
    _session(db, session_id, organization_id, property_id)
    try:
        return ImportService(db).columns(session_id, worksheet)
    except (ImportConflictError, ImportNotFoundError, ImportValidationError) as error:
        _translate_import_error(error)


@router.post("/{session_id}/mapping")
def save_mapping(
    session_id: UUID,
    payload: ImportMappingRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(administrator),
    organization_id: UUID = Depends(organization_context),
    property_id: UUID | None = Depends(property_context),
):
    _session(db, session_id, organization_id, property_id)
    try:
        return ImportService(db).save_mapping(session_id, payload.mapping, payload.worksheet, actor)
    except (ImportConflictError, ImportNotFoundError, ImportValidationError) as error:
        _translate_import_error(error)


@router.post("/{session_id}/validate", response_model=ImportSessionResponse)
def validate_import(
    session_id: UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(administrator),
    organization_id: UUID = Depends(organization_context),
    property_id: UUID | None = Depends(property_context),
):
    _session(db, session_id, organization_id, property_id)
    try:
        return ImportService(db).process_import(session_id, actor)
    except (ImportConflictError, ImportNotFoundError, ImportValidationError) as error:
        _translate_import_error(error)


@router.get("/{session_id}/rows", response_model=ImportedDevicePage)
def rows(
    session_id: UUID,
    validation_status: str | None = Query(default=None, max_length=24),
    search: str | None = Query(default=None, max_length=180),
    source_row_number: int | None = Query(default=None, ge=1),
    error_code: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    _actor: User = Depends(reader),
    organization_id: UUID = Depends(organization_context),
    property_id: UUID | None = Depends(property_context),
):
    _session(db, session_id, organization_id, property_id)
    try:
        return ImportService(db).rows(
            session_id,
            status=validation_status,
            search=search,
            source_row_number=source_row_number,
            error_code=error_code,
            page=page,
            page_size=page_size,
        )
    except (ImportConflictError, ImportNotFoundError, ImportValidationError) as error:
        _translate_import_error(error)


@router.get("/{session_id}/rows/{row_id}", response_model=ImportedDeviceResponse)
def get_row(
    session_id: UUID,
    row_id: UUID,
    db: Session = Depends(get_db),
    _actor: User = Depends(reader),
    organization_id: UUID = Depends(organization_context),
    property_id: UUID | None = Depends(property_context),
):
    _session(db, session_id, organization_id, property_id)
    row = db.query(ImportedDevice).filter_by(id=row_id, import_session_id=session_id).first()
    if not row:
        raise HTTPException(404, "Imported row not found")
    return row


@router.get("/{session_id}/errors")
def errors(
    session_id: UUID,
    db: Session = Depends(get_db),
    _actor: User = Depends(reader),
    organization_id: UUID = Depends(organization_context),
    property_id: UUID | None = Depends(property_context),
):
    _session(db, session_id, organization_id, property_id)
    return ImportService(db).errors(session_id)


@router.get("/{session_id}/errors/export")
def export_errors(
    session_id: UUID,
    db: Session = Depends(get_db),
    _actor: User = Depends(reader),
    organization_id: UUID = Depends(organization_context),
    property_id: UUID | None = Depends(property_context),
):
    _session(db, session_id, organization_id, property_id)
    content, filename = ImportService(db).export_errors(session_id)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{session_id}/cancel", response_model=ImportSessionResponse)
def cancel_import(
    session_id: UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(administrator),
    organization_id: UUID = Depends(organization_context),
    property_id: UUID | None = Depends(property_context),
):
    _session(db, session_id, organization_id, property_id)
    try:
        return ImportService(db).cancel(session_id, actor)
    except (ImportConflictError, ImportNotFoundError, ImportValidationError) as error:
        _translate_import_error(error)


def _run_matching(session_id: UUID, db: Session, actor: User, organization_id: UUID, property_id: UUID | None, recompute: bool):
    _session(db, session_id, organization_id, property_id)
    try:
        return ImportMatchingService(db).run(session_id, actor, recompute=recompute)
    except (MatchingConflictError, MatchingNotFoundError, MatchingValidationError) as error:
        _translate_matching_error(error)


@router.post("/{session_id}/match")
def run_matching(
    session_id: UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(administrator),
    organization_id: UUID = Depends(organization_context),
    property_id: UUID | None = Depends(property_context),
):
    return _run_matching(session_id, db, actor, organization_id, property_id, False)


@router.post("/{session_id}/matches/recompute")
def recompute_matching(
    session_id: UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(administrator),
    organization_id: UUID = Depends(organization_context),
    property_id: UUID | None = Depends(property_context),
):
    return _run_matching(session_id, db, actor, organization_id, property_id, True)


@router.get("/{session_id}/matches", response_model=MatchCandidatePage)
def matches(
    session_id: UUID,
    level: str | None = None,
    status: str | None = None,
    action: str | None = None,
    minimum_score: int = Query(default=0, ge=0, le=100),
    has_conflicts: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    _actor: User = Depends(reader),
    organization_id: UUID = Depends(organization_context),
    property_id: UUID | None = Depends(property_context),
):
    _session(db, session_id, organization_id, property_id)
    try:
        return ImportMatchingService(db).matches(
            session_id,
            level=level,
            status=status,
            action=action,
            minimum_score=minimum_score,
            has_conflicts=has_conflicts,
            page=page,
            page_size=page_size,
        )
    except (MatchingConflictError, MatchingNotFoundError, MatchingValidationError) as error:
        _translate_matching_error(error)


@router.get("/{session_id}/rows/{row_id}/matches", response_model=list[MatchCandidateResponse])
def row_matches(
    session_id: UUID,
    row_id: UUID,
    db: Session = Depends(get_db),
    _actor: User = Depends(reader),
    organization_id: UUID = Depends(organization_context),
    property_id: UUID | None = Depends(property_context),
):
    _session(db, session_id, organization_id, property_id)
    try:
        return ImportMatchingService(db).row_matches(session_id, row_id)
    except (MatchingConflictError, MatchingNotFoundError, MatchingValidationError) as error:
        _translate_matching_error(error)


@router.get("/{session_id}/rows/{row_id}/merge-plan")
def merge_plan(
    session_id: UUID,
    row_id: UUID,
    candidate_id: UUID | None = None,
    db: Session = Depends(get_db),
    _actor: User = Depends(reader),
    organization_id: UUID = Depends(organization_context),
    property_id: UUID | None = Depends(property_context),
):
    _session(db, session_id, organization_id, property_id)
    try:
        return ImportMatchingService(db).merge_plan(session_id, row_id, candidate_id)
    except (MatchingConflictError, MatchingNotFoundError, MatchingValidationError) as error:
        _translate_matching_error(error)


def _resolve_match(session_id: UUID, row_id: UUID, payload: CandidateResolutionRequest, db: Session, actor: User, organization_id: UUID, property_id: UUID | None, accept: bool):
    _session(db, session_id, organization_id, property_id)
    try:
        return ImportMatchingService(db).resolve_candidate(session_id, row_id, payload.candidate_id, actor, accept=accept)
    except (MatchingConflictError, MatchingNotFoundError, MatchingValidationError) as error:
        _translate_matching_error(error)


@router.post("/{session_id}/rows/{row_id}/accept-match", response_model=MatchCandidateResponse)
def accept_match(
    session_id: UUID, row_id: UUID, payload: CandidateResolutionRequest,
    db: Session = Depends(get_db), actor: User = Depends(administrator),
    organization_id: UUID = Depends(organization_context), property_id: UUID | None = Depends(property_context),
):
    return _resolve_match(session_id, row_id, payload, db, actor, organization_id, property_id, True)


@router.post("/{session_id}/rows/{row_id}/reject-match", response_model=MatchCandidateResponse)
def reject_match(
    session_id: UUID, row_id: UUID, payload: CandidateResolutionRequest,
    db: Session = Depends(get_db), actor: User = Depends(administrator),
    organization_id: UUID = Depends(organization_context), property_id: UUID | None = Depends(property_context),
):
    return _resolve_match(session_id, row_id, payload, db, actor, organization_id, property_id, False)


def _resolve_row(session_id: UUID, row_id: UUID, db: Session, actor: User, organization_id: UUID, property_id: UUID | None, create_new: bool):
    _session(db, session_id, organization_id, property_id)
    try:
        service = ImportMatchingService(db)
        return service.mark_create_new(session_id, row_id, actor) if create_new else service.mark_skip(session_id, row_id, actor)
    except (MatchingConflictError, MatchingNotFoundError, MatchingValidationError) as error:
        _translate_matching_error(error)


@router.post("/{session_id}/rows/{row_id}/mark-create-new", response_model=ImportedDeviceResponse)
def create_new_row(
    session_id: UUID, row_id: UUID, db: Session = Depends(get_db),
    actor: User = Depends(administrator), organization_id: UUID = Depends(organization_context),
    property_id: UUID | None = Depends(property_context),
):
    return _resolve_row(session_id, row_id, db, actor, organization_id, property_id, True)


@router.post("/{session_id}/rows/{row_id}/mark-skip", response_model=ImportedDeviceResponse)
def skip_row(
    session_id: UUID, row_id: UUID, db: Session = Depends(get_db),
    actor: User = Depends(administrator), organization_id: UUID = Depends(organization_context),
    property_id: UUID | None = Depends(property_context),
):
    return _resolve_row(session_id, row_id, db, actor, organization_id, property_id, False)


@router.get("/{session_id}/locations")
def locations(
    session_id: UUID, db: Session = Depends(get_db), _actor: User = Depends(reader),
    organization_id: UUID = Depends(organization_context), property_id: UUID | None = Depends(property_context),
):
    _session(db, session_id, organization_id, property_id)
    try:
        return ImportMatchingService(db).locations_for_session(session_id)
    except (MatchingConflictError, MatchingNotFoundError, MatchingValidationError) as error:
        _translate_matching_error(error)


@router.get("/{session_id}/rows/{row_id}/location-suggestion")
def location_for_row(
    session_id: UUID, row_id: UUID, db: Session = Depends(get_db), _actor: User = Depends(reader),
    organization_id: UUID = Depends(organization_context), property_id: UUID | None = Depends(property_context),
):
    _session(db, session_id, organization_id, property_id)
    try:
        return ImportMatchingService(db).location_for_row(session_id, row_id)
    except (MatchingConflictError, MatchingNotFoundError, MatchingValidationError) as error:
        _translate_matching_error(error)


@router.post("/{session_id}/rows/{row_id}/location-suggestion")
def review_location(
    session_id: UUID, row_id: UUID, payload: LocationReviewRequest,
    db: Session = Depends(get_db), actor: User = Depends(administrator),
    organization_id: UUID = Depends(organization_context), property_id: UUID | None = Depends(property_context),
):
    _session(db, session_id, organization_id, property_id)
    if payload.action == "override":
        allowed_properties = select(Property.id).where(Property.organization_id == organization_id)
        if property_id is not None:
            allowed_properties = allowed_properties.where(Property.id == property_id)
        models = {
            Department: payload.department_id,
            Building: payload.building_id,
            Floor: payload.floor_id,
            Room: payload.room_id,
            NetworkZone: payload.network_zone_id,
        }
        for model, identifier in models.items():
            query = select(model.id).where(model.id == identifier, model.is_active.is_(True))
            if model in (Department, Building, NetworkZone):
                query = query.where(model.property_id.in_(allowed_properties))
            elif model is Floor:
                query = query.where(Floor.organization_id == organization_id)
                if property_id is not None:
                    query = query.join(Building, Floor.building_id == Building.id).where(Building.property_id == property_id)
            else:
                query = query.where(Room.organization_id == organization_id)
                if property_id is not None:
                    query = query.join(Floor, Room.floor_id == Floor.id).join(Building, Floor.building_id == Building.id).where(Building.property_id == property_id)
            if identifier and not db.scalar(query):
                raise HTTPException(422, "Location override must use active records in the selected organization and property")
    try:
        return ImportMatchingService(db).review_location(
            session_id,
            row_id,
            actor,
            payload.action,
            {
                "department_id": payload.department_id,
                "building_id": payload.building_id,
                "floor_id": payload.floor_id,
                "room_id": payload.room_id,
                "network_zone_id": payload.network_zone_id,
            },
        )
    except (MatchingConflictError, MatchingNotFoundError, MatchingValidationError) as error:
        _translate_matching_error(error)


@router.post("/{session_id}/rows/{row_id}/disposition", response_model=ImportedDeviceResponse)
def set_disposition(
    session_id: UUID, row_id: UUID, payload: FinalDispositionRequest,
    db: Session = Depends(get_db), actor: User = Depends(administrator),
    organization_id: UUID = Depends(organization_context), property_id: UUID | None = Depends(property_context),
):
    _session(db, session_id, organization_id, property_id)
    try:
        return ImportFinalizationService(db).set_disposition(
            session_id, row_id, payload.disposition,
            payload.approved_fields, payload.approved_overwrites, actor,
        )
    except (FinalizationConflictError, FinalizationNotFoundError, FinalizationValidationError) as error:
        _translate_finalization_error(error)


@router.get("/{session_id}/readiness")
def readiness(
    session_id: UUID, db: Session = Depends(get_db), _actor: User = Depends(reader),
    organization_id: UUID = Depends(organization_context), property_id: UUID | None = Depends(property_context),
):
    _session(db, session_id, organization_id, property_id)
    try:
        return ImportFinalizationService(db).readiness(session_id)
    except (FinalizationConflictError, FinalizationNotFoundError, FinalizationValidationError) as error:
        _translate_finalization_error(error)


@router.get("/{session_id}/execution-plan")
def execution_plan(
    session_id: UUID, persist: bool = False,
    db: Session = Depends(get_db), actor: User = Depends(reader),
    organization_id: UUID = Depends(organization_context), property_id: UUID | None = Depends(property_context),
):
    _session(db, session_id, organization_id, property_id)
    try:
        return ImportFinalizationService(db).execution_plan(session_id, actor if persist else None)
    except (FinalizationConflictError, FinalizationNotFoundError, FinalizationValidationError) as error:
        _translate_finalization_error(error)


@router.post("/{session_id}/finalize")
def finalize(
    session_id: UUID, payload: FinalizeRequest,
    db: Session = Depends(get_db), actor: User = Depends(administrator),
    organization_id: UUID = Depends(organization_context), property_id: UUID | None = Depends(property_context),
):
    _session(db, session_id, organization_id, property_id)
    try:
        return ImportFinalizationService(db).finalize(
            session_id,
            actor,
            plan_version=payload.plan_version,
            idempotency_key=payload.idempotency_key,
            confirmed=payload.confirm_inventory_mutation and payload.confirm_rollback_limits,
        )
    except (FinalizationConflictError, FinalizationNotFoundError, FinalizationValidationError) as error:
        _translate_finalization_error(error)


@router.get("/{session_id}/results")
def results(
    session_id: UUID, page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db), _actor: User = Depends(reader),
    organization_id: UUID = Depends(organization_context), property_id: UUID | None = Depends(property_context),
):
    _session(db, session_id, organization_id, property_id)
    return ImportFinalizationService(db).results(session_id, page=page, page_size=page_size)


@router.get("/{session_id}/rollback-preview")
def rollback_preview(
    session_id: UUID, db: Session = Depends(get_db), _actor: User = Depends(reader),
    organization_id: UUID = Depends(organization_context), property_id: UUID | None = Depends(property_context),
):
    _session(db, session_id, organization_id, property_id)
    try:
        return ImportFinalizationService(db).rollback_preview(session_id)
    except (FinalizationConflictError, FinalizationNotFoundError, FinalizationValidationError) as error:
        _translate_finalization_error(error)


@router.post("/{session_id}/rollback")
def rollback(
    session_id: UUID, _payload: RollbackRequest,
    db: Session = Depends(get_db), actor: User = Depends(administrator),
    organization_id: UUID = Depends(organization_context), property_id: UUID | None = Depends(property_context),
):
    _session(db, session_id, organization_id, property_id)
    try:
        return ImportFinalizationService(db).rollback(session_id, actor)
    except (FinalizationConflictError, FinalizationNotFoundError, FinalizationValidationError) as error:
        _translate_finalization_error(error)


@router.post("/{session_id}/retry-failed")
def retry_failed(
    session_id: UUID, db: Session = Depends(get_db), actor: User = Depends(administrator),
    organization_id: UUID = Depends(organization_context), property_id: UUID | None = Depends(property_context),
):
    _session(db, session_id, organization_id, property_id)
    try:
        return ImportFinalizationService(db).retry_failed(session_id, actor)
    except (FinalizationConflictError, FinalizationNotFoundError, FinalizationValidationError) as error:
        _translate_finalization_error(error)
