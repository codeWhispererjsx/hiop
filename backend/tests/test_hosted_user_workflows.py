from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.hierarchy import Organization, Property
from app.models.user import User
from app.models.billing import CommercialPlan, OrganizationSubscription
from app.models.audit_log import AuditLog
from app.models.system_setting import SystemSetting, OrganizationSetting
from app.services.billing_service import require_entitlement, enforce_limit, require_billable
from app.services.audit_service import export_csv
from app.services.settings_service import save_group, _all
from app.schemas.settings import GeneralSettings
from app.core.tenant import organization_context


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    for model in (Organization, Property, User, CommercialPlan, OrganizationSubscription, AuditLog, SystemSetting, OrganizationSetting):
        model.__table__.create(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def org(db, **kwargs):
    row = Organization(name="Test organisation", code=str(uuid4()), **kwargs)
    db.add(row)
    db.commit()
    return row


def test_exempt_org_without_subscription_keeps_access_but_cannot_checkout(db):
    row = org(db, billing_exempt=True)
    assert require_entitlement(db, row.id, "discovery") is None
    assert enforce_limit(db, row.id, "devices", 10000) is None
    with pytest.raises(HTTPException) as exc:
        require_billable(db, row.id)
    assert exc.value.status_code == 409


def test_owner_suspension_wins_over_billing_exemption(db):
    row = org(db, billing_exempt=True, access_override="suspended")
    with pytest.raises(HTTPException) as exc:
        require_entitlement(db, row.id, "discovery")
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException):
        organization_context(db, SimpleNamespace(role="admin", organization_id=row.id), None)


def test_keep_active_does_not_change_payment_record(db):
    row = org(db, access_override="keep_active")
    assert require_entitlement(db, row.id, "discovery") is None
    assert db.query(OrganizationSubscription).count() == 0


def test_unpaid_organisation_without_override_still_denied(db):
    row = org(db)
    with pytest.raises(HTTPException) as exc:
        require_entitlement(db, row.id, "discovery")
    assert exc.value.status_code == 402


def test_audit_export_scopes_organisation_property_and_escapes_formulas(db):
    first, second = org(db), org(db)
    prop = Property(name="One", organization_id=first.id)
    db.add(prop)
    db.flush()
    for owner, property_id, description in [(first.id, prop.id, "=SUM(1,2)"), (first.id, None, "outside-property"), (second.id, None, "other-organisation")]:
        db.add(AuditLog(actor="System", action="TEST", entity_type="Device", entity_id="test", description=description, organization_id=owner, property_id=property_id))
    db.commit()
    content, _ = export_csv(db, organization_id=first.id, property_id=prop.id)
    assert "'=SUM(1,2)" in content
    assert "other-organisation" not in content and "outside-property" not in content


def test_settings_are_isolated_and_platform_branding_is_fixed(db):
    first, second = org(db), org(db)
    values = dict(application_name="Changed app", short_name="OTHER", timezone="Africa/Lagos", date_format="DD/MM/YYYY", time_format="24-hour", default_page_size=25, default_landing_page="/dashboard")
    db.info["organization_id"] = first.id
    save_group(db, "general", GeneralSettings(**values))
    db.commit()
    assert _all(db)["general.short_name"] == "HIOP"
    assert db.query(SystemSetting).count() == 0
    db.info["organization_id"] = second.id
    assert db.query(OrganizationSetting).filter_by(organization_id=second.id).count() == 0


def test_invalid_time_zone_is_rejected():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        GeneralSettings(application_name="HIOP", short_name="HIOP", timezone="MadeUp/City", date_format="DD/MM/YYYY", time_format="24-hour", default_page_size=25, default_landing_page="/dashboard")


def test_failed_invitation_rolls_back_and_returns_actionable_error(monkeypatch):
    from app.api.v1 import account_security as api
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter_by.return_value.first.return_value = None
    monkeypatch.setattr(api, "enforce_limit", lambda *a: None)
    monkeypatch.setattr(api, "_safe_delivery", lambda *a: "failed")
    actor = SimpleNamespace(id="owner", username="owner", organization_id=uuid4())
    with pytest.raises(HTTPException) as exc:
        api.invite(api.InviteRequest(email="invitee@example.com", role="admin"), db, actor)
    assert exc.value.status_code == 503
    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_cancelled_agent_job_cannot_be_resurrected():
    from app.api.v1.local_agents import update_job, JobUpdate
    task = SimpleNamespace(payload="{}", status="cancelled")
    db = MagicMock()
    db.query.return_value.filter_by.return_value.with_for_update.return_value.first.return_value = task
    agent = SimpleNamespace(id=uuid4(), organization_id=uuid4(), property_id=uuid4())
    result = update_job(uuid4(), JobUpdate(status="completed"), db, agent)
    assert result["status"] == "cancelled"
    db.commit.assert_not_called()
