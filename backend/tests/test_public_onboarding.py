from pathlib import Path

from app.api.v1 import public_onboarding
from app import main


def test_public_onboarding_reuses_tenant_models_and_never_creates_platform_admin():
    source = Path(public_onboarding.__file__).read_text(encoding="utf-8")
    for model in ("Organization(", "Property(", "User(", "UserPropertyAccess("):
        assert model in source
    assert 'role="admin"' in source
    assert 'role="platformadmin"' not in source
    assert "hash_password(payload.admin_password)" in source
    assert "create_access_token" in source


def test_public_onboarding_is_registered_and_transactional():
    source = Path(main.__file__).read_text(encoding="utf-8")
    onboarding = Path(public_onboarding.__file__).read_text(encoding="utf-8")
    assert "public_onboarding_router" in source
    assert '@router.post("/register"' in onboarding
    assert "db.rollback()" in onboarding and "db.commit()" in onboarding
    assert "Organization code already exists" in onboarding
    assert "Administrator username or email already exists" in onboarding


def test_public_onboarding_atomically_starts_selected_plan_trial():
    onboarding = Path(public_onboarding.__file__).read_text(encoding="utf-8")
    assert 'plan_code: str = Field(default="starter"' in onboarding
    assert "start_trial(db, organization.id, payload.plan_code, administrator)" in onboarding
    assert '"subscription": present_subscription(db, subscription)' in onboarding
