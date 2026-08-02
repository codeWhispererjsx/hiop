from decimal import Decimal
from pathlib import Path
from app.services.business_intelligence_service import calculate_formula,growth_percentage,linear_forecast,rolling_average,trend,variance
ROOT=Path(__file__).resolve().parents[1];MODELS=(ROOT/"app/models/business_intelligence.py").read_text();API=(ROOT/"app/api/v1/business_intelligence.py").read_text();SCHEDULER=(ROOT/"app/services/scheduler_service.py").read_text();MIGRATION=(ROOT/"alembic/versions/0b1c2d3e4f58_enterprise_business_intelligence.py").read_text()
def test_formula_engine_is_deterministic_and_allowlisted():
    assert calculate_formula("sum",[1,2,3])==Decimal("6.00");assert calculate_formula("ratio",[9,12])==Decimal("75.00")
    try:calculate_formula("eval",[1]);assert False
    except ValueError:pass
def test_rolling_growth_variance_and_trend():
    assert rolling_average([1,2,3,4],2)==[Decimal("1.00"),Decimal("1.50"),Decimal("2.50"),Decimal("3.50")];assert growth_percentage(120,100)==Decimal("20.00");assert variance(90,100)["absolute"]==Decimal("-10.00");assert trend([1,2,4])["direction"]=="increasing"
def test_forecast_uses_only_historical_linear_trend():assert linear_forecast([2,4,6,8],3)==[Decimal("10.00"),Decimal("12.00"),Decimal("14.00")]
def test_kpi_report_dashboard_models_exist():
    for name in ("KPI","KPIDefinition","KPIValue","KPITarget","KPIThreshold","KPISnapshot","ExecutiveDashboard","Report","ReportTemplate","ReportSection","ReportExecution","ScheduledReport","ReportRecipient"):assert f"class {name}" in MODELS
def test_api_covers_executive_domains_and_exports():
    for route in ("/kpis","/dashboards","/analytics/calculate","/reports","/sla","/capacity","/hospitality-metrics","/exports"):assert route in API
    assert "eval(" not in API and "exec(" not in API
def test_scheduler_and_migration_cover_epic_8():
    assert 'revision="0b1c2d3e4f58"' in MIGRATION and 'down_revision="e2f3a4b5c6d7"' in MIGRATION
    for job in ("kpi_recalculation","snapshot_generation","report_scheduling","email_distribution","trend_aggregation","capacity_recalculation","dashboard_cache_refresh"):assert job in SCHEDULER
