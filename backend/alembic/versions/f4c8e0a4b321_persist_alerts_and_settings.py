"""Persist alert acknowledgement and monitoring settings.

Revision ID: f4c8e0a4b321
Revises: fad00a67ff0a
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f4c8e0a4b321"
down_revision: Union[str, Sequence[str], None] = "fad00a67ff0a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("alerts", sa.Column("acknowledged", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("system_settings")
    op.drop_column("alerts", "acknowledged")
