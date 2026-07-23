"""Add Active Directory connection health metadata.

Revision ID: f4b8c2d9a731
Revises: e8a9b0c1d2e3
Create Date: 2026-07-23
"""

from alembic import op
import sqlalchemy as sa


revision = "f4b8c2d9a731"
down_revision = "e8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("active_directory_connections", sa.Column("last_successful_bind_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("active_directory_connections", sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("active_directory_connections", sa.Column("failure_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("active_directory_connections", sa.Column("certificate_expiry", sa.DateTime(timezone=True), nullable=True))
    op.add_column("active_directory_connections", sa.Column("server_reported_domain", sa.String(length=255), nullable=True))
    op.create_check_constraint("ck_ad_connection_failure_count", "active_directory_connections", "failure_count >= 0")


def downgrade() -> None:
    op.drop_constraint("ck_ad_connection_failure_count", "active_directory_connections", type_="check")
    op.drop_column("active_directory_connections", "server_reported_domain")
    op.drop_column("active_directory_connections", "certificate_expiry")
    op.drop_column("active_directory_connections", "failure_count")
    op.drop_column("active_directory_connections", "last_failure_at")
    op.drop_column("active_directory_connections", "last_successful_bind_at")
