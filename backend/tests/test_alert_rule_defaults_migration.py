from pathlib import Path


def test_alert_rule_repair_migration_restores_only_missing_global_defaults():
    migration = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "v2i_alert_rule_defaults_repair.py"
    ).read_text(encoding="utf-8")

    for rule_type in (
        "device_offline",
        "high_latency",
        "packet_loss",
        "health_degradation",
        "interface_down",
        "snmp_unavailable",
    ):
        assert f'"{rule_type}"' in migration

    assert "WHERE NOT EXISTS" in migration
    assert "organization_id IS NULL" in migration
    assert "property_id IS NULL" in migration
    assert "UPDATE alert_rules" not in migration
