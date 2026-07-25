"""Secure configuration APIs for the non-live SNMP foundation."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.models.snmp import (
    SNMPCredential, SNMPDeviceProfile, SNMPDiscoveryCandidate, SNMPInterface,
    SNMPMetric, SNMPOIDDefinition, SNMPPollingConfiguration, SNMPPollRun,
    SNMPTarget,
)
from app.repositories.snmp_repository import (
    SNMPCredentialRepository, SNMPDeviceProfileRepository,
    SNMPDiscoveryCandidateRepository, SNMPInterfaceRepository,
    SNMPMetricRepository, SNMPOIDDefinitionRepository,
    SNMPPollRunRepository, SNMPTargetRepository,
)
from app.schemas.snmp import (
    SNMPCandidateRead, SNMPCredentialCreate, SNMPCredentialRead,
    SNMPCredentialSecretUpdate, SNMPCredentialUpdate, SNMPInterfaceRead,
    SNMPMetricRead, SNMPOIDCreate, SNMPOIDRead, SNMPOIDUpdate,
    SNMPPollingConfigurationRead, SNMPPollingConfigurationWrite,
    SNMPPollRunRead, SNMPProfileCreate, SNMPProfileRead, SNMPProfileUpdate,
    SNMPTargetCreate, SNMPTargetRead, SNMPTargetUpdate,
)
from app.services.audit_service import create_audit_log
from app.services.snmp_credential_service import SNMPCredentialService
from app.services.snmp_target_service import SNMPTargetService
from app.core.config import settings

router = APIRouter(prefix="/snmp", tags=["SNMP"])
admin_only = require_roles(["admin"])
read_only = require_roles(["admin", "technician"])


def _get(db, model, object_id: UUID, label: str):
    row = db.get(model, object_id)
    if not row:
        raise HTTPException(404, f"{label} was not found.")
    return row


def _page(repo, page, page_size, filters=None):
    items, total = repo.list(page=page, page_size=page_size, filters=filters)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def _credential_read(row):
    return SNMPCredentialRead(
        id=row.id, name=row.name, version=row.version, username=row.username,
        authentication_protocol=row.authentication_protocol,
        privacy_protocol=row.privacy_protocol, security_level=row.security_level,
        context_name=row.context_name, enabled=row.enabled, description=row.description,
        has_community=bool(row.community_encrypted),
        has_authentication_secret=bool(row.authentication_secret_encrypted),
        has_privacy_secret=bool(row.privacy_secret_encrypted),
        created_by=row.created_by, updated_by=row.updated_by,
        created_at=row.created_at, updated_at=row.updated_at,
    )


@router.get("/credentials")
def list_credentials(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), enabled: bool | None = None, db: Session = Depends(get_db), _=Depends(read_only)):
    result = _page(SNMPCredentialRepository(db), page, page_size, {"enabled": enabled})
    result["items"] = [_credential_read(row) for row in result["items"]]
    return result


@router.post("/credentials", response_model=SNMPCredentialRead, status_code=201)
def create_credential(payload: SNMPCredentialCreate, db: Session = Depends(get_db), actor=Depends(admin_only)):
    return _credential_read(SNMPCredentialService(db).create_credential(payload, actor))


@router.get("/credentials/{credential_id}", response_model=SNMPCredentialRead)
def get_credential(credential_id: UUID, db: Session = Depends(get_db), _=Depends(read_only)):
    return _credential_read(_get(db, SNMPCredential, credential_id, "SNMP credential"))


@router.patch("/credentials/{credential_id}", response_model=SNMPCredentialRead)
def update_credential(credential_id: UUID, payload: SNMPCredentialUpdate, db: Session = Depends(get_db), actor=Depends(admin_only)):
    row = _get(db, SNMPCredential, credential_id, "SNMP credential")
    return _credential_read(SNMPCredentialService(db).update_credential(row, payload, actor))


@router.post("/credentials/{credential_id}/secret", response_model=SNMPCredentialRead)
def rotate_credential(credential_id: UUID, payload: SNMPCredentialSecretUpdate, db: Session = Depends(get_db), actor=Depends(admin_only)):
    row = _get(db, SNMPCredential, credential_id, "SNMP credential")
    return _credential_read(SNMPCredentialService(db).rotate_secret(row, payload, actor))


@router.post("/credentials/{credential_id}/disable", response_model=SNMPCredentialRead)
def disable_credential(credential_id: UUID, db: Session = Depends(get_db), actor=Depends(admin_only)):
    row = _get(db, SNMPCredential, credential_id, "SNMP credential")
    return _credential_read(SNMPCredentialService(db).disable_credential(row, actor))


@router.get("/targets")
def list_targets(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), enabled: bool | None = None, db: Session = Depends(get_db), _=Depends(read_only)):
    result = _page(SNMPTargetRepository(db), page, page_size, {"enabled": enabled})
    result["items"] = [SNMPTargetRead.model_validate(row) for row in result["items"]]
    return result


@router.post("/targets", response_model=SNMPTargetRead, status_code=201)
def create_target(payload: SNMPTargetCreate, db: Session = Depends(get_db), actor=Depends(admin_only)):
    return SNMPTargetService(db).create_target(payload, actor)


@router.get("/targets/{target_id}", response_model=SNMPTargetRead)
def get_target(target_id: UUID, db: Session = Depends(get_db), _=Depends(read_only)):
    return _get(db, SNMPTarget, target_id, "SNMP target")


@router.patch("/targets/{target_id}", response_model=SNMPTargetRead)
def update_target(target_id: UUID, payload: SNMPTargetUpdate, db: Session = Depends(get_db), actor=Depends(admin_only)):
    return SNMPTargetService(db).update_target(_get(db, SNMPTarget, target_id, "SNMP target"), payload, actor)


@router.post("/targets/{target_id}/disable", response_model=SNMPTargetRead)
def disable_target(target_id: UUID, db: Session = Depends(get_db), actor=Depends(admin_only)):
    return SNMPTargetService(db).disable_target(_get(db, SNMPTarget, target_id, "SNMP target"), actor)


@router.get("/profiles")
def list_profiles(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), _=Depends(read_only)):
    result = _page(SNMPDeviceProfileRepository(db), page, page_size)
    result["items"] = [SNMPProfileRead.model_validate(row) for row in result["items"]]
    return result


@router.post("/profiles", response_model=SNMPProfileRead, status_code=201)
def create_profile(payload: SNMPProfileCreate, db: Session = Depends(get_db), actor=Depends(admin_only)):
    row = SNMPDeviceProfile(**payload.model_dump(mode="json"))
    db.add(row)
    create_audit_log(db, actor.username, "SNMP_PROFILE_CREATED", "SNMPDeviceProfile", str(row.id), f"Created SNMP device profile '{row.name}'.")
    db.commit(); db.refresh(row)
    return row


@router.get("/profiles/{profile_id}", response_model=SNMPProfileRead)
def get_profile(profile_id: UUID, db: Session = Depends(get_db), _=Depends(read_only)):
    return _get(db, SNMPDeviceProfile, profile_id, "SNMP profile")


@router.patch("/profiles/{profile_id}", response_model=SNMPProfileRead)
def update_profile(profile_id: UUID, payload: SNMPProfileUpdate, db: Session = Depends(get_db), actor=Depends(admin_only)):
    row = _get(db, SNMPDeviceProfile, profile_id, "SNMP profile")
    for key, value in payload.model_dump(exclude_unset=True).items(): setattr(row, key, value)
    create_audit_log(db, actor.username, "SNMP_PROFILE_UPDATED", "SNMPDeviceProfile", str(row.id), f"Updated SNMP device profile '{row.name}'.")
    db.commit(); db.refresh(row)
    return row


@router.get("/oids")
def list_oids(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), profile_id: UUID | None = None, db: Session = Depends(get_db), _=Depends(read_only)):
    result = _page(SNMPOIDDefinitionRepository(db), page, page_size, {"profile_id": profile_id})
    result["items"] = [SNMPOIDRead.model_validate(row) for row in result["items"]]
    return result


@router.post("/oids", response_model=SNMPOIDRead, status_code=201)
def create_oid(payload: SNMPOIDCreate, db: Session = Depends(get_db), actor=Depends(admin_only)):
    if payload.profile_id: _get(db, SNMPDeviceProfile, payload.profile_id, "SNMP profile")
    row = SNMPOIDDefinition(**payload.model_dump(mode="json"))
    db.add(row)
    create_audit_log(db, actor.username, "SNMP_OID_CREATED", "SNMPOIDDefinition", str(row.id), f"Created SNMP OID definition '{row.name}'.")
    db.commit(); db.refresh(row)
    return row


@router.get("/oids/{oid_id}", response_model=SNMPOIDRead)
def get_oid(oid_id: UUID, db: Session = Depends(get_db), _=Depends(read_only)):
    return _get(db, SNMPOIDDefinition, oid_id, "SNMP OID definition")


@router.patch("/oids/{oid_id}", response_model=SNMPOIDRead)
def update_oid(oid_id: UUID, payload: SNMPOIDUpdate, db: Session = Depends(get_db), actor=Depends(admin_only)):
    row = _get(db, SNMPOIDDefinition, oid_id, "SNMP OID definition")
    for key, value in payload.model_dump(exclude_unset=True).items(): setattr(row, key, value)
    create_audit_log(db, actor.username, "SNMP_OID_UPDATED", "SNMPOIDDefinition", str(row.id), f"Updated SNMP OID definition '{row.name}'.")
    db.commit(); db.refresh(row)
    return row


@router.get("/targets/{target_id}/polling-config", response_model=SNMPPollingConfigurationRead)
def get_polling_config(target_id: UUID, db: Session = Depends(get_db), _=Depends(read_only)):
    _get(db, SNMPTarget, target_id, "SNMP target")
    row = db.query(SNMPPollingConfiguration).filter_by(target_id=target_id).first()
    if not row: raise HTTPException(404, "SNMP polling configuration was not found.")
    return row


@router.put("/targets/{target_id}/polling-config", response_model=SNMPPollingConfigurationRead)
def put_polling_config(target_id: UUID, payload: SNMPPollingConfigurationWrite, db: Session = Depends(get_db), actor=Depends(admin_only)):
    _get(db, SNMPTarget, target_id, "SNMP target")
    if payload.profile_id: _get(db, SNMPDeviceProfile, payload.profile_id, "SNMP profile")
    if not settings.snmp_minimum_polling_interval_seconds <= payload.polling_interval_seconds <= settings.snmp_maximum_polling_interval_seconds:
        raise HTTPException(400, "SNMP polling interval is outside configured bounds.")
    if payload.max_oids_per_poll > settings.snmp_maximum_oids_per_request:
        raise HTTPException(400, "SNMP polling OID limit exceeds configured maximum.")
    if payload.max_interfaces > settings.snmp_maximum_interfaces:
        raise HTTPException(400, "SNMP interface limit exceeds configured maximum.")
    row = db.query(SNMPPollingConfiguration).filter_by(target_id=target_id).first()
    if not row:
        row = SNMPPollingConfiguration(target_id=target_id)
        db.add(row)
    for key, value in payload.model_dump().items(): setattr(row, key, value)
    create_audit_log(db, actor.username, "SNMP_POLLING_CONFIG_UPDATED", "SNMPTarget", str(target_id), "Updated inactive SNMP polling configuration.")
    db.commit(); db.refresh(row)
    return row


def _read_page(repository, schema, page, page_size, filters=None):
    result = _page(repository, page, page_size, filters)
    result["items"] = [schema.model_validate(row) for row in result["items"]]
    return result


@router.get("/poll-runs")
def poll_runs(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), target_id: UUID | None = None, status: str | None = None, db: Session = Depends(get_db), _=Depends(read_only)):
    return _read_page(SNMPPollRunRepository(db), SNMPPollRunRead, page, page_size, {"target_id": target_id, "status": status})


@router.get("/metrics")
def metrics(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), target_id: UUID | None = None, metric_key: str | None = None, db: Session = Depends(get_db), _=Depends(read_only)):
    return _read_page(SNMPMetricRepository(db), SNMPMetricRead, page, page_size, {"target_id": target_id, "metric_key": metric_key})


@router.get("/interfaces")
def interfaces(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), target_id: UUID | None = None, db: Session = Depends(get_db), _=Depends(read_only)):
    return _read_page(SNMPInterfaceRepository(db), SNMPInterfaceRead, page, page_size, {"target_id": target_id})


@router.get("/candidates")
def candidates(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), target_id: UUID | None = None, review_status: str | None = None, db: Session = Depends(get_db), _=Depends(read_only)):
    return _read_page(SNMPDiscoveryCandidateRepository(db), SNMPCandidateRead, page, page_size, {"target_id": target_id, "review_status": review_status})
