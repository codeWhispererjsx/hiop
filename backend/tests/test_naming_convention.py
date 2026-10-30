from datetime import date

import pytest
from fastapi import HTTPException

from app.schemas.settings import NamingConventionSettings
from app.services import asset_intelligence_service
from app.services.naming_convention_service import render_asset_number


def test_custom_template_extracts_variables_and_renders_padding():
    settings = NamingConventionSettings(
        template="{COMPANY}-{FLOOR}-{DEPT}-{TYPE}-{NUM:02}",
        separator="-",
    )

    assert settings.variables == ["COMPANY", "FLOOR", "DEPT", "TYPE", "NUM:02"]
    assert render_asset_number(
        settings.template,
        {"COMPANY": "LCH", "FLOOR": "03", "DEPT": "ACC", "TYPE": "DT"},
        5,
    ) == "LCH-03-ACC-DT-05"


def test_no_separator_template_concatenates_values():
    settings = NamingConventionSettings(
        template="{COMPANY}{DEPT}{NUM:02}",
        separator="",
    )

    assert settings.variables == ["COMPANY", "DEPT", "NUM:02"]
    assert render_asset_number(
        settings.template,
        {"COMPANY": "LCH", "DEPT": "ACC"},
        5,
    ) == "LCHACC05"


@pytest.mark.parametrize(
    "template",
    (
        "{COMPANY}-{UNKNOWN}-{NUM}",
        "{COMPANY}-{NUM",
        "{COMPANY}-{DEPT}",
        "{COMPANY}-{NUM:07}",
        "{COMPANY} {NUM}",
    ),
)
def test_invalid_templates_are_rejected(template):
    with pytest.raises(ValueError):
        NamingConventionSettings(template=template)


def test_render_requires_values_used_by_template():
    with pytest.raises(ValueError, match="A value is required for \\{FLOOR\\}"):
        render_asset_number("{COMPANY}-{FLOOR}-{NUM}", {"COMPANY": "LCH"}, 1)


def test_default_convention_keeps_existing_company_prefix_style():
    settings = NamingConventionSettings()
    assert render_asset_number(settings.template, {"COMPANY": "HIOP"}, 123) == "HIOP-000123"


def test_asset_number_generation_uses_organization_template_and_live_values(monkeypatch):
    class FakeDatabase:
        info = {}

        def scalar(self, _statement):
            return "HIOP-000042"

        def query(self, _model):
            raise AssertionError("The configured naming convention should be read through the shared helper.")

        def get(self, model, _identifier):
            if model.__name__ == "Organization":
                return type("OrganizationValue", (), {"code": "BANK"})()
            return None

    monkeypatch.setattr(asset_intelligence_service, "_next_number", lambda _db: "HIOP-000042")
    monkeypatch.setattr(
        asset_intelligence_service,
        "read_naming_convention",
        lambda _db: {"template": "{COMPANY}-{DEPT}-{TYPE}-{YEAR}-{NUM:03}"},
    )

    generated = asset_intelligence_service.generate_asset_number(
        FakeDatabase(),
        "organization-id",
        {"department_name": "Finance", "device_type": "Laptop", "username": "admin"},
    )

    assert generated == f"BANK-FINANCE-LAPTOP-{date.today().year}-042"


def test_asset_number_generation_reports_missing_required_hierarchy(monkeypatch):
    class FakeDatabase:
        info = {}

        def get(self, _model, _identifier):
            return None

        def query(self, _model):
            raise AssertionError("The configured naming convention should be read through the shared helper.")

    monkeypatch.setattr(asset_intelligence_service, "_next_number", lambda _db: "HIOP-000001")
    monkeypatch.setattr(
        asset_intelligence_service,
        "read_naming_convention",
        lambda _db: {"template": "{FLOOR}-{NUM}"},
    )

    with pytest.raises(HTTPException, match="A value is required for \\{FLOOR\\}"):
        asset_intelligence_service.generate_asset_number(
            FakeDatabase(),
            "organization-id",
            {},
        )
