"""Restore missing global predefined alert rules without overwriting settings.

Revision ID: v2i_alert_rule_defaults
Revises: v2hagentasset01
"""
from alembic import op
import sqlalchemy as sa

revision = "v2i_alert_rule_defaults"
down_revision = "v2hagentasset01"
branch_labels = None
depends_on = None

DEFAULT_RULES = (
    ("device_offline", "Device Offline", "critical", None, 3, "Consecutive failed ICMP checks"),
    ("high_latency", "High Latency", "warning", 100, 3, "Sustained response time above threshold"),
    ("packet_loss", "Packet Loss", "warning", 10, 5, "Failed-check percentage above threshold"),
    ("health_degradation", "Health Degradation", "warning", None, 2, "Device health degraded"),
    ("interface_down", "Interface Down", "critical", None, 2, "Monitored interface is down"),
    ("snmp_unavailable", "SNMP Unavailable", "warning", None, 3, "SNMP source unavailable while reachability remains known"),
)


def upgrade():
    connection = op.get_bind()
    statement = sa.text(
        """
        INSERT INTO alert_rules (
            id, rule_type, name, description, severity, threshold_value,
            consecutive_observations, organization_id, property_id
        )
        SELECT gen_random_uuid(), :rule_type, :name, :description, :severity,
               :threshold_value, :consecutive_observations, NULL, NULL
        WHERE NOT EXISTS (
            SELECT 1 FROM alert_rules
            WHERE rule_type = :rule_type
              AND organization_id IS NULL
              AND property_id IS NULL
        )
        """
    )
    for rule_type, name, severity, threshold, count, description in DEFAULT_RULES:
        connection.execute(
            statement,
            {
                "rule_type": rule_type,
                "name": name,
                "description": description,
                "severity": severity,
                "threshold_value": threshold,
                "consecutive_observations": count,
            },
        )


def downgrade():
    # Restored rows may have been customized since this migration ran.
    pass
