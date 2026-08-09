from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.models.discovered_device import ReviewStatus
from app.services.v1_v2_reconciliation_service import V1V2ReconciliationService,normalized_hostname,normalized_mac


def device(**changes):
    values={"id":uuid4(),"hostname":"heloshaposbqt01","ip_address":"10.50.21.45","mac_address":"AA:BB:CC:DD:EE:FF","department":"Banquet","location":"Ballroom","device_type":"Point of Sale","inventory_status":"Active","status":"Active","asset_tag":"HIOP-001","serial_number":"SER-001","created_at":datetime.now(timezone.utc),"updated_at":datetime.now(timezone.utc)}
    values.update(changes);return SimpleNamespace(**values)


def discovery(**changes):
    values={"id":uuid4(),"hostname":"heloshaposbqt01","ip_address":"10.50.21.60","mac_address":"AA-BB-CC-DD-EE-FF","approved_device_id":None,"review_status":ReviewStatus.PENDING,"reviewed_by":None,"reviewed_at":None}
    values.update(changes);return SimpleNamespace(**values)


def test_normalizers_make_identity_comparisons_deterministic():
    assert normalized_mac("AA-BB-CC-DD-EE-FF")=="aabbccddeeff"
    assert normalized_hostname("HELOSHAPOSBQT01.adlosha.local.")=="heloshaposbqt01"


def test_same_mac_new_ip_targets_existing_v1_device():
    existing=device();match,reason,ambiguous=V1V2ReconciliationService.match_inventory(discovery(),[existing])
    assert match is existing and reason=="mac_address" and not ambiguous


def test_same_hostname_new_ip_targets_existing_v1_device():
    existing=device(mac_address=None);match,reason,ambiguous=V1V2ReconciliationService.match_inventory(discovery(mac_address=None),[existing])
    assert match is existing and reason=="hostname" and not ambiguous


def test_ip_alone_requires_review_and_is_never_automatically_linked():
    existing=device(mac_address=None,hostname="legacy-pos");match,reason,ambiguous=V1V2ReconciliationService.match_inventory(discovery(mac_address=None,hostname=None,ip_address=existing.ip_address),[existing])
    assert match is None and reason=="ip_supporting_only" and ambiguous


def test_ambiguous_hostname_requires_review():
    rows=[device(),device(id=uuid4(),mac_address=None)]
    match,reason,ambiguous=V1V2ReconciliationService.match_inventory(discovery(mac_address=None),rows)
    assert match is None and reason=="hostname" and ambiguous


def test_unknown_device_remains_unmatched():
    match,_,ambiguous=V1V2ReconciliationService.match_inventory(discovery(mac_address=None,hostname=None,ip_address="10.50.99.99"),[device()])
    assert match is None and not ambiguous


def test_duplicate_report_distinguishes_strong_and_review_identifiers():
    first=device();second=device(id=uuid4(),serial_number="SER-002")
    candidates=V1V2ReconciliationService.duplicate_candidates([first,second])
    assert {row["identifier"] for row in candidates}=={"mac_address","hostname","ip_address"}
    assert next(row for row in candidates if row["identifier"]=="mac_address")["confidence"]=="strong"
    assert all(row["action"]=="requires_review" for row in candidates)


def test_link_preserves_uuid_and_all_authoritative_manual_inventory_values():
    existing=device();before=V1V2ReconciliationService._snapshot(existing);row=discovery();actor=SimpleNamespace(id="admin-1")
    V1V2ReconciliationService.apply_link(row,existing,actor,datetime(2026,8,9,tzinfo=timezone.utc))
    assert row.approved_device_id==existing.id and row.review_status==ReviewStatus.APPROVED
    assert V1V2ReconciliationService._snapshot(existing)==before
    assert before["department"]=="Banquet" and before["location"]=="Ballroom"


def test_repeated_link_is_idempotent_and_does_not_create_a_device():
    existing=device();row=discovery();actor=SimpleNamespace(id="admin-1")
    V1V2ReconciliationService.apply_link(row,existing,actor);first=row.approved_device_id
    V1V2ReconciliationService.apply_link(row,existing,actor)
    assert row.approved_device_id==first==existing.id


def test_service_contract_contains_no_destructive_inventory_operation():
    source=Path(__file__).parents[1].joinpath("app/services/v1_v2_reconciliation_service.py").read_text(encoding="utf-8")
    for forbidden in ("db.delete(","DELETE FROM devices","TRUNCATE","Device("):
        assert forbidden not in source


def test_reconciliation_api_is_admin_protected_and_exposed():
    from app.main import app
    paths=app.openapi()["paths"]
    assert "/api/v1/discovery-intelligence/reconciliation/report" in paths
    assert "/api/v1/discovery-intelligence/reconciliation/run" in paths
    assert "security" in paths["/api/v1/discovery-intelligence/reconciliation/run"]["post"]
