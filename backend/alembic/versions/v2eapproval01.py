"""Allow verified serial numbers to be absent and persist discovery approvals."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "v2eapproval01"
down_revision = "branding01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "devices",
        "serial_number",
        existing_type=sa.String(),
        nullable=True,
    )
    op.execute(
        "UPDATE devices SET serial_number = NULL "
        "WHERE serial_number LIKE 'UNRESOLVED-%'"
    )
    op.create_table(
        "enterprise_discovery_approval_links",
        sa.Column("result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["result_id"],
            ["enterprise_discovery_results.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("result_id"),
    )
    op.create_index(
        "ix_enterprise_discovery_approval_links_device_id",
        "enterprise_discovery_approval_links",
        ["device_id"],
    )


def downgrade() -> None:
    if op.get_bind().execute(
        sa.text("SELECT 1 FROM devices WHERE serial_number IS NULL LIMIT 1")
    ).first():
        raise RuntimeError(
            "Populate verified serial numbers before reverting the nullable serial migration."
        )
    op.drop_index(
        "ix_enterprise_discovery_approval_links_device_id",
        table_name="enterprise_discovery_approval_links",
    )
    op.drop_table("enterprise_discovery_approval_links")
    op.alter_column(
        "devices",
        "serial_number",
        existing_type=sa.String(),
        nullable=False,
    )
