from types import SimpleNamespace
from uuid import uuid4

from app.models.inventory_import import ImportCandidateType, ImportValidationStatus
from app.models.device import Device
from app.imports.matching import score_records
from app.services.import_finalization_service import ImportFinalizationService
from app.services.import_matching_service import ImportMatchingService


def test_exact_hostname_remains_a_candidate_when_score_thresholds_are_customized():
    settings = {
        "conflict_penalty": 25,
        "fuzzy_matching_enabled": False,
        "exact_match_threshold": 100,
        "strong_match_threshold": 95,
        "probable_match_threshold": 90,
        "weak_match_threshold": 85,
    }

    result = score_records(
        SimpleNamespace(hostname="host-01"),
        SimpleNamespace(hostname="HOST-01"),
        settings,
    )

    assert result["level"] == "weak"
    assert result["matching_fields"] == ["hostname"]


def test_quick_import_links_only_unambiguous_exact_hostname_and_stages_new_hosts(monkeypatch):
    session_id = uuid4()
    existing_row = SimpleNamespace(
        id=uuid4(), hostname="host-01", validation_status=ImportValidationStatus.VALID
    )
    new_row = SimpleNamespace(
        id=uuid4(), hostname="host-02", validation_status=ImportValidationStatus.VALID
    )
    conflict_row = SimpleNamespace(
        id=uuid4(), hostname="host-03", validation_status=ImportValidationStatus.VALID
    )
    duplicate_row = SimpleNamespace(
        id=uuid4(), hostname="host-04", validation_status=ImportValidationStatus.DUPLICATE
    )
    target_id = uuid4()
    exact_candidate = SimpleNamespace(
        id=uuid4(),
        candidate_device_id=target_id,
        candidate_type=ImportCandidateType.INVENTORY_DEVICE,
        matching_fields=["hostname"],
        conflicting_fields=[],
    )
    conflicting_candidate = SimpleNamespace(
        id=uuid4(),
        candidate_device_id=uuid4(),
        candidate_type=ImportCandidateType.INVENTORY_DEVICE,
        matching_fields=["hostname"],
        conflicting_fields=[{"field": "mac_address"}],
    )
    rows = [existing_row, new_row, conflict_row, duplicate_row]
    candidates = {
        existing_row.id: [exact_candidate],
        new_row.id: [],
        conflict_row.id: [conflicting_candidate],
        duplicate_row.id: [],
    }
    db = SimpleNamespace(get=lambda model, identifier: SimpleNamespace(hostname="host-01") if model is Device and identifier == target_id else None)
    service = ImportMatchingService(db)
    service._session = lambda _: SimpleNamespace()
    service.repository.rows_to_match = lambda _: rows
    service.repository.candidates_for_row = lambda _session_id, row_id: candidates[row_id]
    accepted = []
    service.resolve_candidate = lambda _session_id, row_id, candidate_id, _actor, *, accept: accepted.append(
        (row_id, candidate_id, accept)
    )
    dispositions = []
    monkeypatch.setattr(
        ImportFinalizationService,
        "set_disposition",
        lambda _self, _session_id, row_id, disposition, *_args: dispositions.append(
            (row_id, disposition)
        ),
    )

    service.prepare_quick_import(session_id, SimpleNamespace())

    assert accepted == [(existing_row.id, exact_candidate.id, True)]
    assert (new_row.id, "create_asset") in dispositions
    assert (duplicate_row.id, "skip") in dispositions
    assert not any(row_id == conflict_row.id for row_id, _ in dispositions)
