"""Add import parsing and validation metadata.

Revision ID: 2c6a8e4f901b
Revises: 7f4e2c1a9d30
Create Date: 2026-07-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "2c6a8e4f901b"
down_revision = "7f4e2c1a9d30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("import_sessions", sa.Column("mapping_metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.add_column("import_sessions", sa.Column("selected_worksheet", sa.String(255)))
    op.add_column("imported_devices", sa.Column("notes", sa.Text()))
    op.add_column("imported_devices", sa.Column("normalized_data", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.add_column("imported_devices", sa.Column("errors", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False))
    op.add_column("imported_devices", sa.Column("warnings", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False))
    op.add_column("imported_devices", sa.Column("source_row_number", sa.Integer(), nullable=True))
    op.execute("UPDATE imported_devices SET source_row_number = numbered.row_number FROM (SELECT id, row_number() OVER (PARTITION BY import_session_id ORDER BY imported_at, id) + 1 AS row_number FROM imported_devices) AS numbered WHERE imported_devices.id = numbered.id")
    op.alter_column("imported_devices", "source_row_number", nullable=False)
    op.drop_index("uq_imported_devices_session_asset_tag", table_name="imported_devices")
    op.drop_index("uq_imported_devices_session_mac", table_name="imported_devices")
    op.create_index("ix_imported_devices_session_asset_tag", "imported_devices", ["import_session_id", "asset_tag"])
    op.create_index("ix_imported_devices_session_mac", "imported_devices", ["import_session_id", "mac_address"])
    op.create_index("uq_imported_devices_session_source_row", "imported_devices", ["import_session_id", "source_row_number"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_imported_devices_session_source_row", table_name="imported_devices")
    op.drop_index("ix_imported_devices_session_mac", table_name="imported_devices")
    op.drop_index("ix_imported_devices_session_asset_tag", table_name="imported_devices")
    op.create_index("uq_imported_devices_session_mac", "imported_devices", ["import_session_id", sa.text("lower(mac_address)")], unique=True, postgresql_where=sa.text("mac_address IS NOT NULL"))
    op.create_index("uq_imported_devices_session_asset_tag", "imported_devices", ["import_session_id", sa.text("lower(asset_tag)")], unique=True, postgresql_where=sa.text("asset_tag IS NOT NULL"))
    for column in ("source_row_number", "warnings", "errors", "normalized_data", "notes"):
        op.drop_column("imported_devices", column)
    op.drop_column("import_sessions", "selected_worksheet")
    op.drop_column("import_sessions", "mapping_metadata")
