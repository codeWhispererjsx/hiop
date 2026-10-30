import pytest
from pydantic import ValidationError

from app.schemas.settings import GeneralSettings, PublicSettings
from app.services import settings_service


def general(**overrides):
    values = {
        "application_name": "HIOP",
        "short_name": "HIOP",
        "timezone": "Africa/Lagos",
        "date_format": "DD/MM/YYYY",
        "time_format": "24-hour",
        "default_page_size": 25,
        "default_landing_page": "/dashboard",
    }
    values.update(overrides)
    return GeneralSettings(**values)


@pytest.mark.parametrize("page", ["/discovery-intelligence", "/incidents", "/discovery", "/tickets"])
def test_landing_page_accepts_real_routes_and_previously_saved_values(page):
    assert general(default_landing_page=page).default_landing_page == page


def test_landing_page_rejects_unknown_routes():
    with pytest.raises(ValidationError):
        general(default_landing_page="/somewhere-else")


def test_public_settings_include_the_landing_page(monkeypatch):
    values = dict(settings_service.DEFAULTS)
    values["general.default_landing_page"] = "/alerts"
    monkeypatch.setattr(settings_service, "_all", lambda _db: values)

    result = PublicSettings(**settings_service.read_public(None))

    assert result.default_landing_page == "/alerts"
