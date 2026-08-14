from pathlib import Path

from app.api.v1 import reporting


def test_v4i_has_the_prebuilt_report_catalog():
    assert reporting.REPORTS == {
        "executive", "operations", "network", "assets", "lifecycle",
        "incidents", "problems", "changes", "procurement", "vendors",
        "knowledge", "services", "departments", "locations",
    }


def test_v4i_supports_required_periods_and_honest_missing_data():
    assert set(reporting.PERIODS) == {"today", "7d", "30d", "90d", "month", "quarter", "year"}
    assert reporting.metric(None, "Availability")["value"] == "Insufficient data"
    assert reporting.trend([], "created_at", reporting.datetime.min.replace(tzinfo=reporting.timezone.utc), reporting.datetime.now(reporting.timezone.utc))["status"] == "insufficient_data"


def test_v4i_api_is_tenant_scoped_exportable_and_non_predictive():
    source = Path(reporting.__file__).read_text(encoding="utf-8").lower()
    assert 'prefix="/reporting"' in source
    assert "organization_context" in source
    assert "export.csv" in source
    assert "text/csv" in source
    assert "managedasset" in source and "operationalincident" in source
    assert "forecast" not in source
    assert "predictive" not in source
    assert "materialized" not in source


def test_v4i_does_not_add_a_reporting_store_or_migration():
    migrations = Path(__file__).parents[1] / "alembic" / "versions"
    assert not any("v4i" in path.name.lower() for path in migrations.glob("*.py"))
