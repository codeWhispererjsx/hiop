from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1.account_security import _hash
from app.core.rate_limit import OperationRateLimiter
from app.models.alert import AlertRule
from app.models.audit_log import AuditLog
from app.models.hierarchy import Organization
from app.models.saas_security import AccountToken, DataLifecycleRequest, SecurityAccessEvent, UserInvitation


def test_saas_models_are_tenant_owned_and_retained():
    assert AuditLog.organization_id is not None and AuditLog.property_id is not None
    assert AuditLog.retention_until is not None and AuditLog.archived_at is not None and AuditLog.legal_hold is not None
    assert SecurityAccessEvent.organization_id is not None and SecurityAccessEvent.property_id is not None
    assert DataLifecycleRequest.organization_id is not None and UserInvitation.organization_id is not None
    assert Organization.legal_hold is not None and Organization.offboarding_status is not None


def test_account_tokens_are_stored_as_hashes():
    assert _hash("one-time-secret") != "one-time-secret"
    assert len(_hash("one-time-secret")) == 64
    assert AccountToken.token_hash.property.columns[0].unique


def test_tenant_alert_rule_scope_replaces_global_uniqueness():
    constraints={item.name for item in AlertRule.__table__.constraints if item.name}
    assert "uq_alert_rule_tenant_scope" in constraints
    assert AlertRule.organization_id is not None and AlertRule.property_id is not None


def test_global_rate_limiter_rejects_bursts_with_retry_after():
    limiter=OperationRateLimiter(limit=1,window_seconds=60)
    limiter.check("tenant:user")
    with pytest.raises(HTTPException) as error:limiter.check("tenant:user")
    assert error.value.status_code==429 and "Retry-After" in error.value.headers


def test_api_wide_isolation_is_central_and_provider_controls_are_explicit():
    root=Path(__file__).parents[1]/"app"
    middleware=(root/"core"/"saas_middleware.py").read_text(encoding="utf-8")
    assert "Organization access denied" in middleware
    assert "Property access denied" in middleware
    assert "SecurityAccessEvent" in middleware
    assert "require_entitlement" in middleware
    administration=(root/"api"/"v1"/"saas_administration.py").read_text(encoding="utf-8")
    for requirement in ("legal_hold","ERASE {row.organization_id}","DOMAIN_VERIFICATION_STARTED","AUDIT_ARCHIVED"):
        assert requirement in administration


def test_migration_is_additive_and_preserves_existing_operational_records():
    migration=Path(__file__).parents[1]/"alembic"/"versions"/"saas1a2b3c4d5_saas_security_hardening.py"
    upgrade=migration.read_text(encoding="utf-8").split("def upgrade():",1)[1].split("def downgrade():",1)[0]
    assert "drop_table" not in upgrade
    assert "UPDATE users SET email_verified_at" in upgrade
    assert "security_access_events" in upgrade and "data_lifecycle_requests" in upgrade
