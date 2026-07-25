"""Secure configuration APIs for the non-live SNMP foundation."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.models.snmp import (
    SNMPCredential, SNMPDeviceProfile, SNMPDiscoveryCandidate, SNMPInterface,
    SNMPInterfaceChange, SNMPMatchCandidate, SNMPMetric, SNMPOIDDefinition,
    SNMPPollingConfiguration, SNMPPollRun, SNMPStateChange, SNMPTarget,
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
    SNMPTargetTestRequest, SNMPManualPollRequest, SNMPManualPollResponse,
    SNMPCollectionRequest, SNMPCandidateAction, SNMPCandidateLinkRequest,
    SNMPCandidateOnboardRequest, SNMPCandidateEnrichRequest, SNMPMatchRead,
    SNMPInterfaceChangeRead,
    SNMPStateChangeRead,
)
from app.services.audit_service import create_audit_log
from app.services.snmp_credential_service import SNMPCredentialService
from app.services.snmp_target_service import SNMPTargetService
from app.services.snmp_polling_service import SNMPPollingService
from app.services.snmp_operational_service import SNMPOperationalService
from app.models.device import Device
from app.core.rate_limit import (
    snmp_cancel_limiter, snmp_identity_limiter, snmp_manual_poll_limiter,
    snmp_target_test_limiter,
)
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


def _rate_key(request: Request, actor, operation: str, object_id: UUID):
    client = request.client.host if request.client else "unknown"
    return f"{operation}:{actor.id}:{object_id}:{client}"


@router.post("/targets/{target_id}/test")
def test_target(target_id: UUID, payload: SNMPTargetTestRequest, request: Request, db: Session = Depends(get_db), actor=Depends(admin_only)):
    snmp_target_test_limiter.check(_rate_key(request, actor, "test", target_id))
    target = _get(db, SNMPTarget, target_id, "SNMP target")
    return SNMPTargetService(db).test_target(
        target, actor, include_optional_identity=payload.include_optional_identity,
        temporary_timeout=payload.temporary_timeout_seconds,
    )


@router.get("/targets/{target_id}/system-identity")
def system_identity(target_id: UUID, request: Request, db: Session = Depends(get_db), actor=Depends(admin_only)):
    snmp_identity_limiter.check(_rate_key(request, actor, "identity", target_id))
    target = _get(db, SNMPTarget, target_id, "SNMP target")
    result = SNMPTargetService(db).test_target(target, actor, include_optional_identity=True)
    return {
        "target_id": target_id, "identity": result["identity"],
        "detected_version": result["detected_version"],
        "timestamp": result["tested_at"], "warnings": result["warnings"],
        "profile_suggestion_id": target.detected_profile_id,
    }


@router.post("/targets/{target_id}/poll", response_model=SNMPManualPollResponse)
def manual_poll(target_id: UUID, payload: SNMPManualPollRequest, request: Request, db: Session = Depends(get_db), actor=Depends(admin_only)):
    snmp_manual_poll_limiter.check(_rate_key(request, actor, "poll", target_id))
    _get(db, SNMPTarget, target_id, "SNMP target")
    service = SNMPPollingService(db)
    run = service.create_poll_run(target_id, actor, payload.poll_type)
    run = service.execute_poll(run.id, actor)
    return SNMPManualPollResponse(
        poll_run_id=run.id, accepted_poll_type=run.poll_type, status=run.status,
        warnings=[run.error_summary] if run.error_summary else [],
    )


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
def poll_runs(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), target_id: UUID | None = None, status: str | None = None, poll_type: str | None = None, trigger_type: str | None = None, start_date: datetime | None = None, end_date: datetime | None = None, db: Session = Depends(get_db), _=Depends(read_only)):
    if start_date and end_date and start_date > end_date: raise HTTPException(400, "Start date must precede end date.")
    result = _read_page(SNMPPollRunRepository(db), SNMPPollRunRead, page, page_size, {"target_id": target_id, "status": status, "poll_type": poll_type, "trigger_type": trigger_type})
    if start_date: result["items"] = [row for row in result["items"] if row.started_at >= start_date]
    if end_date: result["items"] = [row for row in result["items"] if row.started_at <= end_date]
    return result


@router.get("/poll-runs/{run_id}", response_model=SNMPPollRunRead)
def poll_run_detail(run_id: UUID, db: Session = Depends(get_db), _=Depends(read_only)):
    return _get(db, SNMPPollRun, run_id, "SNMP poll run")


@router.post("/poll-runs/{run_id}/cancel", response_model=SNMPPollRunRead)
def cancel_poll(run_id: UUID, request: Request, db: Session = Depends(get_db), actor=Depends(admin_only)):
    snmp_cancel_limiter.check(_rate_key(request, actor, "cancel", run_id))
    run = _get(db, SNMPPollRun, run_id, "SNMP poll run")
    return SNMPPollingService(db).cancel_poll(run, actor)


@router.get("/poll-runs/{run_id}/results")
def poll_results(run_id: UUID, page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), _=Depends(read_only)):
    _get(db, SNMPPollRun, run_id, "SNMP poll run")
    return _read_page(SNMPMetricRepository(db), SNMPMetricRead, page, page_size, {"poll_run_id": run_id})


@router.get("/metrics")
def metrics(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), target_id: UUID | None = None, metric_key: str | None = None, db: Session = Depends(get_db), _=Depends(read_only)):
    return _read_page(SNMPMetricRepository(db), SNMPMetricRead, page, page_size, {"target_id": target_id, "metric_key": metric_key})


@router.get("/interfaces")
def interfaces(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), target_id: UUID | None = None, db: Session = Depends(get_db), _=Depends(read_only)):
    return _read_page(SNMPInterfaceRepository(db), SNMPInterfaceRead, page, page_size, {"target_id": target_id})


@router.get("/candidates")
def candidates(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), target_id: UUID | None = None, review_status: str | None = None, db: Session = Depends(get_db), _=Depends(read_only)):
    return _read_page(SNMPDiscoveryCandidateRepository(db), SNMPCandidateRead, page, page_size, {"target_id": target_id, "review_status": review_status})


@router.post("/targets/{target_id}/collect")
def collect(target_id: UUID, payload: SNMPCollectionRequest, request: Request, db: Session = Depends(get_db), actor=Depends(admin_only)):
    """Execute one bounded, approved collection plan; no scheduler is involved."""
    snmp_manual_poll_limiter.check(_rate_key(request, actor, "collect", target_id))
    _get(db, SNMPTarget, target_id, "SNMP target")
    mapping = {
        "availability": "availability", "system": "system",
        "interface_inventory": "interfaces_preview",
        "interface_performance": "custom_profile",
        "device_performance": "custom_profile",
        "all_profile_metrics": "custom_profile",
    }
    # A manual request is intentionally a single run. Duplicate execution types collapse.
    poll_types = list(dict.fromkeys(mapping[group] for group in payload.groups))
    service = SNMPPollingService(db)
    run = service.create_poll_run(target_id, actor, poll_types[0] if len(poll_types) == 1 else "composite")
    run = service.execute_collection(run.id, actor, payload.groups)
    return {"poll_run_id": run.id, "accepted_groups": payload.groups, "status": run.status,
            "warnings": [run.error_summary] if run.error_summary else []}


@router.get("/candidates/{candidate_id}", response_model=SNMPCandidateRead)
def candidate_detail(candidate_id: UUID, db: Session = Depends(get_db), _=Depends(read_only)):
    return _get(db, SNMPDiscoveryCandidate, candidate_id, "SNMP candidate")


@router.post("/candidates/{candidate_id}/match")
def match_candidate(candidate_id: UUID, db: Session = Depends(get_db), actor=Depends(admin_only)):
    candidate = _get(db, SNMPDiscoveryCandidate, candidate_id, "SNMP candidate")
    rows = SNMPOperationalService(db).generate_matches(candidate, actor)
    return {"items": [SNMPMatchRead.model_validate(row) for row in rows], "total": len(rows)}


@router.get("/candidates/{candidate_id}/matches")
def candidate_matches(candidate_id: UUID, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), _=Depends(read_only)):
    _get(db, SNMPDiscoveryCandidate, candidate_id, "SNMP candidate")
    query = db.query(SNMPMatchCandidate).filter_by(snmp_candidate_id=candidate_id).order_by(SNMPMatchCandidate.match_score.desc())
    total = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [SNMPMatchRead.model_validate(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/candidates/{candidate_id}/onboarding-plan")
def onboarding_plan(candidate_id: UUID, db: Session = Depends(get_db), _=Depends(read_only)):
    candidate = _get(db, SNMPDiscoveryCandidate, candidate_id, "SNMP candidate")
    target = _get(db, SNMPTarget, candidate.target_id, "SNMP target")
    suggestions = {"hostname": candidate.sys_name, "brand": candidate.vendor_guess,
                   "device_type": candidate.device_type_guess, "ip_address": target.ip_address,
                   "location": candidate.sys_location}
    required = ["asset_tag", "hostname", "device_type", "brand", "model", "serial_number",
                "department", "location", "ip_address", "mac_address"]
    return {"candidate_id": candidate.id, "candidate_updated_at": candidate.updated_at,
            "suggestions": suggestions, "required_fields": required,
            "missing_required_fields": [key for key in required if not suggestions.get(key)],
            "automatic_creation": False}


@router.post("/candidates/{candidate_id}/approve")
def approve_candidate(candidate_id: UUID, payload: SNMPCandidateOnboardRequest, db: Session = Depends(get_db), actor=Depends(admin_only)):
    candidate = _get(db, SNMPDiscoveryCandidate, candidate_id, "SNMP candidate")
    device = SNMPOperationalService(db).onboard(candidate, payload.device, actor, payload.expected_updated_at)
    return {"candidate_id": candidate.id, "device_id": device.id, "status": "approved"}


@router.post("/candidates/{candidate_id}/link")
def link_candidate(candidate_id: UUID, payload: SNMPCandidateLinkRequest, db: Session = Depends(get_db), actor=Depends(admin_only)):
    candidate = _get(db, SNMPDiscoveryCandidate, candidate_id, "SNMP candidate")
    device = _get(db, Device, payload.device_id, "Device")
    link = SNMPOperationalService(db).link(candidate, device, actor, payload.expected_updated_at)
    return {"candidate_id": candidate.id, "device_id": device.id, "link_id": link.id, "status": "approved"}


@router.post("/candidates/{candidate_id}/enrich")
def enrich_candidate(candidate_id: UUID, payload: SNMPCandidateEnrichRequest, db: Session = Depends(get_db), actor=Depends(admin_only)):
    candidate = _get(db, SNMPDiscoveryCandidate, candidate_id, "SNMP candidate")
    device = _get(db, Device, payload.device_id, "Device")
    return SNMPOperationalService(db).enrich(candidate, device, payload.fields, actor, overwrite=payload.overwrite, expected_updated_at=payload.expected_updated_at)


def _candidate_review(candidate_id, status, db, actor):
    return SNMPOperationalService(db).review(_get(db, SNMPDiscoveryCandidate, candidate_id, "SNMP candidate"), status, actor)


@router.post("/candidates/{candidate_id}/ignore", response_model=SNMPCandidateRead)
def ignore_candidate(candidate_id: UUID, payload: SNMPCandidateAction, db: Session = Depends(get_db), actor=Depends(admin_only)):
    return _candidate_review(candidate_id, "ignored", db, actor)


@router.post("/candidates/{candidate_id}/reject", response_model=SNMPCandidateRead)
def reject_candidate(candidate_id: UUID, payload: SNMPCandidateAction, db: Session = Depends(get_db), actor=Depends(admin_only)):
    return _candidate_review(candidate_id, "rejected", db, actor)


@router.post("/candidates/{candidate_id}/restore", response_model=SNMPCandidateRead)
def restore_candidate(candidate_id: UUID, payload: SNMPCandidateAction, db: Session = Depends(get_db), actor=Depends(admin_only)):
    return _candidate_review(candidate_id, "pending", db, actor)


@router.get("/targets/{target_id}/interfaces")
def target_interfaces(target_id: UUID, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
                      search: str | None = None, admin_status: str | None = None, oper_status: str | None = None,
                      missing: bool | None = None, down_only: bool = False, db: Session = Depends(get_db), _=Depends(read_only)):
    _get(db, SNMPTarget, target_id, "SNMP target")
    query = db.query(SNMPInterface).filter_by(target_id=target_id)
    if search: query = query.filter(SNMPInterface.name.ilike(f"%{search[:100]}%"))
    if admin_status: query = query.filter_by(admin_status=admin_status)
    if oper_status: query = query.filter_by(operational_status=oper_status)
    if missing is not None: query = query.filter_by(is_missing=missing)
    if down_only: query = query.filter(SNMPInterface.operational_status != "1")
    total = query.count(); rows = query.order_by(SNMPInterface.interface_index).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [SNMPInterfaceRead.model_validate(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/interfaces/{interface_id}", response_model=SNMPInterfaceRead)
def interface_detail(interface_id: UUID, db: Session = Depends(get_db), _=Depends(read_only)):
    return _get(db, SNMPInterface, interface_id, "SNMP interface")


@router.get("/interfaces/{interface_id}/changes")
def interface_changes(interface_id: UUID, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), _=Depends(read_only)):
    _get(db, SNMPInterface, interface_id, "SNMP interface")
    query = db.query(SNMPInterfaceChange).filter_by(interface_id=interface_id)
    total = query.count(); rows = query.order_by(SNMPInterfaceChange.detected_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [SNMPInterfaceChangeRead.model_validate(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/interfaces/{interface_id}/metrics")
def interface_metrics(interface_id: UUID, metric_key: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), _=Depends(read_only)):
    interface = _get(db, SNMPInterface, interface_id, "SNMP interface")
    filters = {"target_id": interface.target_id, "interface_index": interface.interface_index, "metric_key": metric_key}
    return _read_page(SNMPMetricRepository(db), SNMPMetricRead, page, page_size, filters)


@router.get("/targets/{target_id}/metrics")
def target_metrics(target_id: UUID, metric_key: str | None = None, quality: str | None = None,
                   page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), _=Depends(read_only)):
    _get(db, SNMPTarget, target_id, "SNMP target")
    return _read_page(SNMPMetricRepository(db), SNMPMetricRead, page, page_size, {"target_id": target_id, "metric_key": metric_key, "quality": quality})


@router.get("/targets/{target_id}/metric-summary")
def metric_summary(target_id: UUID, metric_key: str, db: Session = Depends(get_db), _=Depends(read_only)):
    _get(db, SNMPTarget, target_id, "SNMP target")
    query = db.query(
        func.min(SNMPMetric.value_numeric), func.max(SNMPMetric.value_numeric),
        func.avg(SNMPMetric.value_numeric), func.count(SNMPMetric.id),
    ).filter(SNMPMetric.target_id == target_id, SNMPMetric.metric_key == metric_key, SNMPMetric.value_numeric.isnot(None))
    minimum, maximum, average, count = query.one()
    latest = db.query(SNMPMetric).filter_by(target_id=target_id, metric_key=metric_key).order_by(SNMPMetric.observed_at.desc()).first()
    return {"metric_key": metric_key, "latest": SNMPMetricRead.model_validate(latest) if latest else None,
            "minimum": minimum, "maximum": maximum, "average": average, "sample_count": count}


@router.get("/retention/preview")
def retention_preview(db: Session = Depends(get_db), _=Depends(admin_only)):
    return SNMPOperationalService(db).retention_preview(settings.snmp_metric_retention_days, settings.snmp_poll_run_retention_days)


@router.post("/retention/cleanup")
def retention_cleanup(db: Session = Depends(get_db), actor=Depends(admin_only)):
    return SNMPOperationalService(db).cleanup(actor, settings.snmp_metric_retention_days, settings.snmp_poll_run_retention_days)


@router.get("/state-changes")
def state_changes(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
                  target_id: UUID | None = None, interface_id: UUID | None = None,
                  state_type: str | None = None, severity: str | None = None,
                  start_date: datetime | None = None, end_date: datetime | None = None,
                  db: Session = Depends(get_db), _=Depends(read_only)):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(400, "Start date must precede end date.")
    query = db.query(SNMPStateChange)
    if target_id: query = query.filter_by(target_id=target_id)
    if interface_id: query = query.filter_by(interface_id=interface_id)
    if state_type: query = query.filter_by(state_type=state_type)
    if severity: query = query.filter_by(severity_hint=severity)
    if start_date: query = query.filter(SNMPStateChange.detected_at >= start_date)
    if end_date: query = query.filter(SNMPStateChange.detected_at <= end_date)
    total = query.count()
    rows = query.order_by(SNMPStateChange.detected_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [SNMPStateChangeRead.model_validate(row) for row in rows],
            "total": total, "page": page, "page_size": page_size}
