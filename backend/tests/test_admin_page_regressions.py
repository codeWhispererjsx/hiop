"""Regression contracts for admin pages that previously returned HTTP 500."""
from app.api.v1 import active_directory
from app.models.active_directory import ActiveDirectoryMatchCandidate
from app.services.settings_service import _bool


def test_settings_boolean_normalizer_is_idempotent():
    assert _bool(True) is True
    assert _bool(False) is False
    assert _bool("true") is True
    assert _bool("false") is False


def test_active_directory_overview_model_is_imported():
    assert active_directory.ActiveDirectoryMatchCandidate is ActiveDirectoryMatchCandidate
