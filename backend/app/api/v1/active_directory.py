from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.core.rate_limit import ad_connection_test_limiter
from app.models.user import User
from app.models.active_directory import (
    ActiveDirectoryObject,
    ActiveDirectoryObjectChange,
    ActiveDirectorySyncError,
    ActiveDirectorySyncRun,
    ActiveDirectoryConnection,
    ActiveDirectoryDepartmentMapping,
    ActiveDirectoryOUMapping,
    ActiveDirectoryGroupRoleMapping,
    ActiveDirectoryReconciliationResult,
)
from app.models.hierarchy import Building, Department, Floor, NetworkZone, Room
from app.repositories.active_directory_repository import (
    ActiveDirectoryConnectionRepository,
    ActiveDirectoryMatchCandidateRepository,
    ActiveDirectoryObjectRepository,
    ActiveDirectorySyncRunRepository,
)
from app.schemas.active_directory import (
    ActiveDirectoryConnectionCreate,
    ActiveDirectoryConnectionRead,
    ActiveDirectoryConnectionUpdate,
    ActiveDirectoryConnectionTestResponse,
    ActiveDirectoryRootDseResponse,
    DirectoryPreviewResponse,
    ActiveDirectoryMatchCandidateRead,
    ActiveDirectoryObjectRead,
    ActiveDirectorySecretUpdate,
    ActiveDirectorySyncConfigurationRead,
    ActiveDirectorySyncConfigurationUpdate,
    ActiveDirectorySyncRunRead,
    PaginatedADConnections,
    PaginatedADMatchCandidates,
    PaginatedADObjects,
    PaginatedADSyncRuns,
    ActiveDirectorySyncRequest,
    ActiveDirectorySyncAccepted,
    ActiveDirectorySyncSummary,
    PaginatedADSyncErrors,
    PaginatedADObjectChanges,
    ActiveDirectoryMatchRequest,
    ActiveDirectoryCandidateReview,
    ActiveDirectoryResolveRequest,
    ActiveDirectoryBulkReviewRequest,
    ActiveDirectoryDepartmentMappingWrite,
    ActiveDirectoryOUMappingWrite,
    ActiveDirectoryGroupRoleMappingWrite,
    ActiveDirectoryMappingRead,
    ActiveDirectoryReconciliationResultRead,
)
from app.services.active_directory_service import (
    ActiveDirectoryConnectionService,
    ActiveDirectorySyncConfigService,
)
from app.services.active_directory_sync_service import ActiveDirectorySynchronizationService
from app.services.active_directory_matching_service import ActiveDirectoryMatchingService
from app.services.active_directory_reconciliation_service import ActiveDirectoryReconciliationService
from app.services.audit_service import create_audit_log

router = APIRouter(prefix="/active-directory", tags=["Active Directory"])

admin_only = require_roles(["admin"])
read_only = require_roles(["admin", "technician"])


def _to_connection_read(conn) -> ActiveDirectoryConnectionRead:
    return ActiveDirectoryConnectionRead(
        id=conn.id,
        name=conn.name,
        domain_name=conn.domain_name,
        server_host=conn.server_host,
        server_port=conn.server_port,
        use_ssl=conn.use_ssl,
        use_start_tls=conn.use_start_tls,
        base_dn=conn.base_dn,
        user_search_base=conn.user_search_base,
        computer_search_base=conn.computer_search_base,
        group_search_base=conn.group_search_base,
        bind_username=conn.bind_username,
        has_bind_secret=bool(conn.encrypted_bind_secret),
        authentication_method=conn.authentication_method,
        connection_timeout_seconds=conn.connection_timeout_seconds,
        page_size=conn.page_size,
        enabled=conn.enabled,
        verify_tls=conn.verify_tls,
        ca_certificate_reference=conn.ca_certificate_reference,
        last_tested_at=conn.last_tested_at,
        last_test_status=conn.last_test_status,
        last_test_message=conn.last_test_message,
        last_successful_bind_at=conn.last_successful_bind_at,
        last_failure_at=conn.last_failure_at,
        failure_count=conn.failure_count,
        certificate_expiry=conn.certificate_expiry,
        server_reported_domain=conn.server_reported_domain,
        created_by=conn.created_by,
        updated_by=conn.updated_by,
        created_at=conn.created_at,
        updated_at=conn.updated_at,
    )


@router.get("/connections", response_model=PaginatedADConnections)
def list_connections(
    search: str | None = Query(None),
    enabled_only: bool | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(read_only),
):
    repo = ActiveDirectoryConnectionRepository(db)
    connections, total = repo.page(search=search, enabled_only=enabled_only, offset=offset, limit=limit)
    return PaginatedADConnections(
        items=[_to_connection_read(conn) for conn in connections],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("/connections", response_model=ActiveDirectoryConnectionRead, status_code=status.HTTP_201_CREATED)
def create_connection(
    payload: ActiveDirectoryConnectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    service = ActiveDirectoryConnectionService(db)
    connection = service.create_connection(payload, current_user)
    return _to_connection_read(connection)


@router.get("/connections/{id}", response_model=ActiveDirectoryConnectionRead)
def get_connection(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(read_only),
):
    service = ActiveDirectoryConnectionService(db)
    connection = service.repo.get(id)
    if not connection:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Active Directory connection '{id}' not found.")
    return _to_connection_read(connection)


@router.patch("/connections/{id}", response_model=ActiveDirectoryConnectionRead)
def update_connection(
    id: str,
    payload: ActiveDirectoryConnectionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    service = ActiveDirectoryConnectionService(db)
    connection = service.update_connection(id, payload, current_user)
    return _to_connection_read(connection)


@router.post("/connections/{id}/secret", response_model=ActiveDirectoryConnectionRead)
def rotate_secret(
    id: str,
    payload: ActiveDirectorySecretUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    service = ActiveDirectoryConnectionService(db)
    connection = service.rotate_secret(id, payload.bind_secret, current_user)
    return _to_connection_read(connection)


@router.post("/connections/{id}/disable", response_model=ActiveDirectoryConnectionRead)
def disable_connection(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    service = ActiveDirectoryConnectionService(db)
    connection = service.disable_connection(id, current_user)
    return _to_connection_read(connection)


@router.post("/connections/{id}/test", response_model=ActiveDirectoryConnectionTestResponse)
def test_connection(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    ad_connection_test_limiter.check(f"{current_user.id}:{id}")
    service = ActiveDirectoryConnectionService(db)
    result = service.test_connection(id, current_user)
    return result


@router.get("/connections/{id}/root-dse", response_model=ActiveDirectoryRootDseResponse)
def root_dse(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    return ActiveDirectoryConnectionService(db).root_dse(id, current_user)


@router.get("/connections/{id}/preview/users", response_model=DirectoryPreviewResponse)
def preview_users(
    id: str,
    limit: int = Query(25, ge=1, le=100),
    search: str | None = Query(None, min_length=1, max_length=64),
    enabled: bool | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    return ActiveDirectoryConnectionService(db).preview(
        id, "users", current_user, limit=limit, search_term=search, enabled=enabled
    )


@router.get("/connections/{id}/preview/computers", response_model=DirectoryPreviewResponse)
def preview_computers(
    id: str,
    limit: int = Query(25, ge=1, le=100),
    search: str | None = Query(None, min_length=1, max_length=64),
    enabled: bool | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    return ActiveDirectoryConnectionService(db).preview(
        id, "computers", current_user, limit=limit, search_term=search, enabled=enabled
    )


@router.get("/connections/{id}/preview/groups", response_model=DirectoryPreviewResponse)
def preview_groups(
    id: str,
    limit: int = Query(25, ge=1, le=100),
    search: str | None = Query(None, min_length=1, max_length=64),
    include_members: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    return ActiveDirectoryConnectionService(db).preview(
        id, "groups", current_user, limit=limit, search_term=search,
        include_members=include_members,
    )


@router.get("/connections/{id}/sync-config", response_model=ActiveDirectorySyncConfigurationRead)
def get_sync_config(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(read_only),
):
    service = ActiveDirectorySyncConfigService(db)
    config = service.get_sync_config(id)
    return ActiveDirectorySyncConfigurationRead.model_validate(config)


@router.put("/connections/{id}/sync-config", response_model=ActiveDirectorySyncConfigurationRead)
def update_sync_config(
    id: str,
    payload: ActiveDirectorySyncConfigurationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    service = ActiveDirectorySyncConfigService(db)
    config = service.update_sync_config(id, payload, current_user)
    return ActiveDirectorySyncConfigurationRead.model_validate(config)


@router.get("/sync-runs", response_model=PaginatedADSyncRuns)
def list_sync_runs(
    connection_id: str | None = Query(None),
    status: str | None = Query(None),
    sync_mode: str | None = Query(None, pattern="^(full|incremental)$"),
    dry_run: bool | None = Query(None),
    trigger_type: str | None = Query(None),
    started_from: datetime | None = Query(None),
    started_to: datetime | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(read_only),
):
    repo = ActiveDirectorySyncRunRepository(db)
    runs, total = repo.page(
        connection_id=connection_id, status=status, sync_mode=sync_mode, dry_run=dry_run,
        trigger_type=trigger_type, started_from=started_from, started_to=started_to,
        offset=offset, limit=limit,
    )
    return PaginatedADSyncRuns(
        items=[ActiveDirectorySyncRunRead.model_validate(run) for run in runs],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("/connections/{id}/sync", response_model=ActiveDirectorySyncAccepted)
def start_sync(
    id: str,
    payload: ActiveDirectorySyncRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    run = ActiveDirectorySynchronizationService(db).start(
        id, current_user, sync_mode=payload.sync_mode, dry_run=payload.dry_run,
        object_types=list(payload.object_types) if payload.object_types else None,
        limit=payload.limit,
    )
    return ActiveDirectorySyncAccepted(
        sync_run_id=run.id,
        status=run.status,
        accepted_configuration={
            "sync_mode": run.sync_mode, "dry_run": run.dry_run,
            "object_types": run.object_types, "limit": (run.progress or {}).get("limit"),
        },
        warnings=["Synchronization executes inline in this deployment; progress remains resumable from the run record."],
    )


@router.get("/sync-runs/{id}", response_model=ActiveDirectorySyncRunRead)
def get_sync_run(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(read_only),
):
    run = db.get(ActiveDirectorySyncRun, id)
    if not run:
        raise HTTPException(status_code=404, detail="Synchronization run was not found.")
    return ActiveDirectorySyncRunRead.model_validate(run)


@router.post("/sync-runs/{id}/cancel", response_model=ActiveDirectorySyncRunRead)
def cancel_sync_run(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    return ActiveDirectorySynchronizationService(db).cancel(id, current_user)


@router.get("/sync-runs/{id}/errors", response_model=PaginatedADSyncErrors)
def sync_run_errors(
    id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    if not db.get(ActiveDirectorySyncRun, id):
        raise HTTPException(status_code=404, detail="Synchronization run was not found.")
    total = db.scalar(select(func.count(ActiveDirectorySyncError.id)).where(
        ActiveDirectorySyncError.sync_run_id == id
    )) or 0
    items = db.scalars(select(ActiveDirectorySyncError).where(
        ActiveDirectorySyncError.sync_run_id == id
    ).order_by(ActiveDirectorySyncError.created_at.desc()).offset(offset).limit(limit)).all()
    return PaginatedADSyncErrors(items=items, total=total, offset=offset, limit=limit)


@router.get("/sync-runs/{id}/summary", response_model=ActiveDirectorySyncSummary)
def sync_run_summary(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(read_only),
):
    run = db.get(ActiveDirectorySyncRun, id)
    if not run:
        raise HTTPException(status_code=404, detail="Synchronization run was not found.")
    return ActiveDirectorySyncSummary(
        sync_run_id=run.id, status=run.status, sync_mode=run.sync_mode, dry_run=run.dry_run,
        counts={
            "users": run.users_seen, "computers": run.computers_seen, "groups": run.groups_seen,
            "created": run.created_objects, "updated": run.updated_objects,
            "unchanged": run.unchanged_objects, "missing": run.missing_objects,
            "restored": run.restored_objects, "errors": run.errors_count,
            "conflicts": run.conflicts,
        },
        per_object_type=run.per_type_status, duration_ms=run.duration_ms,
        checkpoint_before=run.checkpoint_before, checkpoint_after=run.checkpoint_after,
    )


@router.get("/sync-runs/{id}/dry-run-results")
def dry_run_results(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    run = db.get(ActiveDirectorySyncRun, id)
    if not run:
        raise HTTPException(status_code=404, detail="Synchronization run was not found.")
    if not run.dry_run:
        raise HTTPException(status_code=409, detail="This was not a dry-run synchronization.")
    return {"sync_run_id": run.id, "simulation": True, "projected": run.dry_run_results}


@router.get("/objects", response_model=PaginatedADObjects)
def list_directory_objects(
    connection_id: str | None = Query(None),
    object_type: str | None = Query(None),
    sync_status: str | None = Query(None),
    review_status: str | None = Query(None),
    enabled: bool | None = Query(None),
    organizational_unit: str | None = Query(None, max_length=512),
    department: str | None = Query(None, max_length=255),
    missing: bool | None = Query(None),
    search: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(read_only),
):
    repo = ActiveDirectoryObjectRepository(db)
    objects, total = repo.page(
        connection_id=connection_id,
        object_type=object_type,
        sync_status=sync_status,
        review_status=review_status,
        enabled=enabled,
        organizational_unit=organizational_unit,
        department=department,
        missing=missing,
        search=search,
        offset=offset,
        limit=limit,
    )
    return PaginatedADObjects(
        items=[
            ActiveDirectoryObjectRead.model_validate(obj).model_copy(update={
                "raw_attributes": {} if current_user.role != "admin" else obj.raw_attributes,
                "email": None if current_user.role != "admin" else obj.email,
            })
            for obj in objects
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/objects/{id}", response_model=ActiveDirectoryObjectRead)
def get_directory_object(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(read_only),
):
    obj = db.get(ActiveDirectoryObject, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Directory object was not found.")
    result = ActiveDirectoryObjectRead.model_validate(obj)
    if current_user.role != "admin":
        result = result.model_copy(update={"raw_attributes": {}, "email": None})
    return result


@router.get("/objects/{id}/changes", response_model=PaginatedADObjectChanges)
def object_changes(
    id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    if not db.get(ActiveDirectoryObject, id):
        raise HTTPException(status_code=404, detail="Directory object was not found.")
    total = db.scalar(select(func.count(ActiveDirectoryObjectChange.id)).where(
        ActiveDirectoryObjectChange.directory_object_id == id
    )) or 0
    items = db.scalars(select(ActiveDirectoryObjectChange).where(
        ActiveDirectoryObjectChange.directory_object_id == id
    ).order_by(ActiveDirectoryObjectChange.detected_at.desc()).offset(offset).limit(limit)).all()
    return PaginatedADObjectChanges(items=items, total=total, offset=offset, limit=limit)


@router.post("/connections/{id}/match")
def run_directory_matching(
    id: str,
    payload: ActiveDirectoryMatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    return ActiveDirectoryMatchingService(db).run(
        id, current_user, object_types=payload.object_types,
        recompute=payload.recompute, dry_run=payload.dry_run, limit=payload.limit,
    )


@router.get("/objects/{id}/matches", response_model=list[ActiveDirectoryMatchCandidateRead])
def object_matches(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(read_only),
):
    return ActiveDirectoryMatchingService(db).candidates_for_object(id)


@router.get("/objects/{id}/reconciliation-plan")
def reconciliation_plan(
    id: str,
    candidate_id: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(read_only),
):
    return ActiveDirectoryReconciliationService(db).plan(id, candidate_id)


@router.post("/objects/{id}/accept-match", response_model=ActiveDirectoryMatchCandidateRead)
def accept_directory_match(
    id: str,
    payload: ActiveDirectoryCandidateReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    return ActiveDirectoryReconciliationService(db).review_candidate(
        id, payload.candidate_id, current_user, accept=True
    )


@router.post("/objects/{id}/reject-match", response_model=ActiveDirectoryMatchCandidateRead)
def reject_directory_match(
    id: str,
    payload: ActiveDirectoryCandidateReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    return ActiveDirectoryReconciliationService(db).review_candidate(
        id, payload.candidate_id, current_user, accept=False
    )


@router.post("/objects/{id}/mark-create", response_model=ActiveDirectoryReconciliationResultRead)
def mark_directory_create(
    id: str,
    payload: ActiveDirectoryResolveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    if payload.action not in {"create_new_user", "create_new_device"}:
        raise HTTPException(422, "Mark-create requires a create disposition.")
    return _resolve_directory_object(id, payload, db, current_user)


@router.post("/objects/{id}/ignore", response_model=ActiveDirectoryReconciliationResultRead)
def ignore_directory_object(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    return ActiveDirectoryReconciliationService(db).resolve(
        id, current_user, action="ignore", candidate_id=None, approved_fields=[],
        device_payload=None, role=None, active=None, confirm=True,
    )


def _resolve_directory_object(id, payload, db, current_user):
    return ActiveDirectoryReconciliationService(db).resolve(
        id, current_user, action=payload.action, candidate_id=payload.candidate_id,
        approved_fields=payload.approved_fields, device_payload=payload.device,
        role=payload.role, active=payload.active, confirm=payload.confirm,
        confirm_privileged_role=payload.confirm_privileged_role,
    )


@router.post("/objects/{id}/resolve", response_model=ActiveDirectoryReconciliationResultRead)
def resolve_directory_object(
    id: str,
    payload: ActiveDirectoryResolveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    return _resolve_directory_object(id, payload, db, current_user)


@router.post("/bulk-review")
def bulk_directory_review(
    payload: ActiveDirectoryBulkReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    return ActiveDirectoryReconciliationService(db).bulk(
        payload.object_ids, current_user, action=payload.action, confirm=payload.confirm
    )


@router.get("/objects/{id}/reconciliation-results", response_model=list[ActiveDirectoryReconciliationResultRead])
def reconciliation_results(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    if not db.get(ActiveDirectoryObject, id):
        raise HTTPException(404, "Directory object was not found.")
    return db.scalars(select(ActiveDirectoryReconciliationResult).where(
        ActiveDirectoryReconciliationResult.directory_object_id == id
    ).order_by(ActiveDirectoryReconciliationResult.reviewed_at.desc()).limit(100)).all()


def _mapping_model(kind: str):
    models = {
        "departments": ActiveDirectoryDepartmentMapping,
        "ous": ActiveDirectoryOUMapping,
        "roles": ActiveDirectoryGroupRoleMapping,
    }
    if kind not in models:
        raise HTTPException(404, "Mapping type was not found.")
    return models[kind]


@router.get("/connections/{id}/mappings/{kind}", response_model=list[ActiveDirectoryMappingRead])
def list_ad_mappings(
    id: str, kind: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(read_only),
):
    if not db.get(ActiveDirectoryConnection, id):
        raise HTTPException(404, "Active Directory connection was not found.")
    model = _mapping_model(kind)
    return db.scalars(select(model).where(model.connection_id == id).order_by(
        model.priority, model.created_at
    )).all()


@router.post("/connections/{id}/mappings/departments", response_model=ActiveDirectoryMappingRead)
def create_department_mapping(
    id: str, payload: ActiveDirectoryDepartmentMappingWrite,
    db: Session = Depends(get_db), current_user: User = Depends(admin_only),
):
    if not db.get(ActiveDirectoryConnection, id) or not db.get(Department, payload.department_id):
        raise HTTPException(404, "Connection or department was not found.")
    row = ActiveDirectoryDepartmentMapping(
        connection_id=id, created_by=current_user.id, updated_by=current_user.id, **payload.model_dump()
    )
    db.add(row)
    create_audit_log(db, current_user.username, "AD_DEPARTMENT_MAPPING_CREATED",
                     "ActiveDirectoryDepartmentMapping", row.id, "Created reviewed AD department mapping.")
    db.commit(); db.refresh(row); return row


@router.post("/connections/{id}/mappings/ous", response_model=ActiveDirectoryMappingRead)
def create_ou_mapping(
    id: str, payload: ActiveDirectoryOUMappingWrite,
    db: Session = Depends(get_db), current_user: User = Depends(admin_only),
):
    if not db.get(ActiveDirectoryConnection, id):
        raise HTTPException(404, "Active Directory connection was not found.")
    checks = ((Department, payload.department_id), (Building, payload.building_id),
              (Floor, payload.floor_id), (Room, payload.room_id), (NetworkZone, payload.network_zone_id))
    if any(value and not db.get(model, value) for model, value in checks):
        raise HTTPException(422, "One or more hierarchy mapping targets are invalid.")
    row = ActiveDirectoryOUMapping(
        connection_id=id, created_by=current_user.id, updated_by=current_user.id, **payload.model_dump()
    )
    db.add(row)
    create_audit_log(db, current_user.username, "AD_OU_MAPPING_CREATED",
                     "ActiveDirectoryOUMapping", row.id, "Created ordered non-executable AD OU mapping.")
    db.commit(); db.refresh(row); return row


@router.post("/connections/{id}/mappings/roles", response_model=ActiveDirectoryMappingRead)
def create_role_mapping(
    id: str, payload: ActiveDirectoryGroupRoleMappingWrite,
    db: Session = Depends(get_db), current_user: User = Depends(admin_only),
):
    if not db.get(ActiveDirectoryConnection, id):
        raise HTTPException(404, "Active Directory connection was not found.")
    if payload.target_role == "admin" and not payload.requires_confirmation:
        raise HTTPException(422, "Admin mappings must require explicit confirmation.")
    row = ActiveDirectoryGroupRoleMapping(
        connection_id=id, created_by=current_user.id, updated_by=current_user.id, **payload.model_dump()
    )
    db.add(row)
    create_audit_log(db, current_user.username, "AD_GROUP_ROLE_MAPPING_CREATED",
                     "ActiveDirectoryGroupRoleMapping", row.id, "Created reviewed AD group-role suggestion mapping.")
    db.commit(); db.refresh(row); return row


@router.delete("/connections/{id}/mappings/{kind}/{mapping_id}")
def delete_ad_mapping(
    id: str, kind: str, mapping_id: str,
    db: Session = Depends(get_db), current_user: User = Depends(admin_only),
):
    model = _mapping_model(kind)
    row = db.get(model, mapping_id)
    if not row or row.connection_id != id:
        raise HTTPException(404, "Mapping rule was not found for this connection.")
    db.delete(row)
    create_audit_log(db, current_user.username, "AD_MAPPING_REMOVED",
                     model.__name__, mapping_id, "Removed an explicit Active Directory mapping rule.")
    db.commit()
    return {"message": "Mapping rule removed.", "id": mapping_id}


@router.get("/matches", response_model=PaginatedADMatchCandidates)
def list_match_candidates(
    directory_object_id: str | None = Query(None),
    candidate_type: str | None = Query(None),
    match_status: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(read_only),
):
    repo = ActiveDirectoryMatchCandidateRepository(db)
    candidates, total = repo.page(
        directory_object_id=directory_object_id,
        candidate_type=candidate_type,
        match_status=match_status,
        offset=offset,
        limit=limit,
    )
    return PaginatedADMatchCandidates(
        items=[ActiveDirectoryMatchCandidateRead.model_validate(c) for c in candidates],
        total=total,
        offset=offset,
        limit=limit,
    )
