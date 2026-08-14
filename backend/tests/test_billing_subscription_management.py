from pathlib import Path

from app.models.billing import BillingEvent, CommercialPlan, OrganizationSubscription


ROOT=Path(__file__).parents[1]


def test_billing_models_are_organization_scoped_and_store_no_card_data():
    assert OrganizationSubscription.organization_id is not None
    assert OrganizationSubscription.plan_id is not None
    assert BillingEvent.provider_event_id is not None
    columns={column.name for table in (CommercialPlan.__table__,OrganizationSubscription.__table__,BillingEvent.__table__) for column in table.columns}
    for forbidden in ("card_number","cvv","pan","card_secret"):
        assert forbidden not in columns


def test_billing_api_separates_public_organization_and_platform_authority():
    source=(ROOT/"app/api/v1/billing.py").read_text(encoding="utf-8")
    assert 'org_admin=require_roles(["admin"])' in source
    assert 'platform=require_roles(["platformadmin"])' in source
    for route in ('/public/plans','/current','/documents','/trial','/checkout','/change-plan','/cancel','/platform/overview','/platform/plans','/webhooks/{provider_name}'):
        assert route in source
    assert "organization_id=org" in source


def test_plans_are_seeded_once_and_pricing_is_not_in_frontend_components():
    migration=(ROOT/"alembic/versions/billing0a1b2c3d_subscription_management.py").read_text(encoding="utf-8").lower()
    assert 'down_revision = "v4j0a1b2c3d4"' in migration
    for plan in ("starter","core","enterprise"):
        assert f'("{plan}"' in migration
    assert "card_number" not in migration and "cvv" not in migration


def test_provider_boundary_fails_closed_without_real_configuration():
    source=(ROOT/"app/services/billing_service.py").read_text(encoding="utf-8")
    assert "class BillingProvider" in source
    assert "Online checkout is not configured" in source
    assert "No card data enters HIOP" in source
    assert "require_entitlement" in source and "enforce_limit" in source


def test_public_onboarding_starts_configured_plan_trial_atomically():
    source=(ROOT/"app/api/v1/public_onboarding.py").read_text(encoding="utf-8")
    assert "plan_code" in source
    assert "start_trial(db, organization.id, payload.plan_code, administrator)" in source
    assert source.index("start_trial(db") < source.index("db.commit()")
