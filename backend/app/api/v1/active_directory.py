from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.core.rate_limit import ad_connection_test_limiter
from app.models.user import User
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
)
from app.services.active_directory_service import (
    ActiveDirectoryConnectionService,
    ActiveDirectorySyncConfigService,
)

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
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(read_only),
):
    repo = ActiveDirectorySyncRunRepository(db)
    runs, total = repo.page(connection_id=connection_id, status=status, offset=offset, limit=limit)
    return PaginatedADSyncRuns(
        items=[ActiveDirectorySyncRunRead.model_validate(run) for run in runs],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/objects", response_model=PaginatedADObjects)
def list_directory_objects(
    connection_id: str | None = Query(None),
    object_type: str | None = Query(None),
    sync_status: str | None = Query(None),
    review_status: str | None = Query(None),
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
        search=search,
        offset=offset,
        limit=limit,
    )
    return PaginatedADObjects(
        items=[ActiveDirectoryObjectRead.model_validate(obj) for obj in objects],
        total=total,
        offset=offset,
        limit=limit,
    )


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
