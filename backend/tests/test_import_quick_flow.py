from types import SimpleNamespace
from uuid import uuid4

from app.models.inventory_import import ImportCandidateType, ImportValidationStatus
from app.models.device import Device
from app.models.hierarchy import Department
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


def test_quick_import_skips_exact_managed_asset_matches_instead_of_creating_duplicates(monkeypatch):
    session_id, row_id, organization_id, property_id = uuid4(), uuid4(), uuid4(), uuid4()
    row = SimpleNamespace(
        id=row_id,
        hostname="host-01",
        validation_status=ImportValidationStatus.VALID,
    )
    db = SimpleNamespace(
        get=lambda *_args: None,
        info={"organization_id": organization_id},
        scalar=lambda _query: uuid4(),
    )
    service = ImportMatchingService(db)
    service._session = lambda _: SimpleNamespace(
        mapping_metadata={"tenant_property_id": str(property_id)}
    )
    service.repository.rows_to_match = lambda _: [row]
    service.repository.candidates_for_row = lambda *_args: []
    dispositions = []
    monkeypatch.setattr(
        ImportFinalizationService,
        "set_disposition",
        lambda _self, _session_id, row_id, disposition, *_args: dispositions.append(
            (row_id, disposition)
        ),
    )

    service.prepare_quick_import(session_id, SimpleNamespace())

    assert dispositions == [(row_id, "skip")]


def test_import_plan_resolves_a_unique_exact_department_name():
    department = SimpleNamespace(id=uuid4(), name="Front Office")
    db = SimpleNamespace(
        info={"organization_id": uuid4(), "property_id": uuid4()},
        scalars=lambda _query: SimpleNamespace(all=lambda: [department]),
        get=lambda *_args: None,
    )
    service = ImportFinalizationService(db)
    service._location = lambda _row: None
    row = SimpleNamespace(
        id=uuid4(),
        import_session_id=uuid4(),
        source_row_number=2,
        final_disposition="create_asset",
        resolution_action=None,
        department_name=" front office ",
        room_name=None,
        asset_tag=None,
        hostname="FO-PC-01",
        device_type="Windows Computer",
        brand=None,
        vendor=None,
        model=None,
        serial_number=None,
        inventory_status=None,
        ip_address=None,
        mac_address=None,
        notes=None,
        normalized_data={},
        linked_device_id=None,
        linked_discovery_id=None,
        approved_changes=None,
        resolved_by=None,
        resolved_at=None,
    )

    plan = service._plan_row(row)

    assert plan["hierarchy"]["department_id"] == str(department.id)
    assert plan["values"]["department"] == department.name


def test_reviewed_import_creates_missing_department_and_audit_record(monkeypatch):
    organization_id = uuid4()
    created = []
    audit = []

    class Database:
        info = {"property_id": uuid4()}

        def scalars(self, _query):
            return SimpleNamespace(all=lambda: [])

        def add(self, row):
            created.append(row)

        def flush(self):
            created[-1].id = uuid4()

    monkeypatch.setattr(
        "app.services.import_finalization_service.create_audit_log",
        lambda *args: audit.append(args),
    )
    service = ImportFinalizationService(Database())
    actor = SimpleNamespace(username="import-admin")

    department = service._ensure_import_department(
        "  Front Office  ", organization_id, uuid4(), actor
    )

    assert isinstance(department, Department)
    assert department.name == "Front Office"
    assert department.organization_id == organization_id
    assert department.is_active is True
    assert created == [department]
    assert audit[0][2] == "IMPORT_DEPARTMENT_CREATED"


def test_reviewed_import_does_not_create_a_blank_department():
    class Database:
        info = {}

    service = ImportFinalizationService(Database())

    assert service._ensure_import_department("  ", uuid4(), None, SimpleNamespace(username="admin")) is None
