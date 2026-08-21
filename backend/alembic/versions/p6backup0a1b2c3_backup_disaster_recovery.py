"""backup and disaster recovery tracking

Revision ID: p6backup0a1b2c3
Revises: p5health0a1b2c3
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision="p6backup0a1b2c3";down_revision="p5health0a1b2c3";branch_labels=None;depends_on=None

def upgrade():
    u=postgresql.UUID(as_uuid=True)
    op.create_table("backup_records",
        sa.Column("id",u,primary_key=True),
        sa.Column("backup_type",sa.String(20),nullable=False),
        sa.Column("status",sa.String(20),nullable=False),
        sa.Column("started_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.Column("completed_at",sa.DateTime(timezone=True)),
        sa.Column("file_path",sa.String(500)),
        sa.Column("file_size_bytes",sa.BigInteger()),
        sa.Column("checksum",sa.String(64)),
        sa.Column("checksum_verified",sa.Boolean(),server_default="false",nullable=False),
        sa.Column("error",sa.String(1000)),
        sa.Column("retention_days",sa.Integer(),server_default="14",nullable=False),
        sa.Column("database_version",sa.String(50)),
        comment="Track database backup operations for disaster recovery")
    op.create_index("ix_backup_records_status","backup_records",["status"])
    op.create_index("ix_backup_records_started","backup_records",["started_at"])
    
    op.create_table("restore_tests",
        sa.Column("id",u,primary_key=True),
        sa.Column("status",sa.String(20),nullable=False),
        sa.Column("started_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.Column("completed_at",sa.DateTime(timezone=True)),
        sa.Column("backup_id",u,nullable=False),
        sa.Column("backup_file",sa.String(500),nullable=False),
        sa.Column("database_version",sa.String(50)),
        sa.Column("restore_duration_seconds",sa.Integer()),
        sa.Column("organizations_verified",sa.Integer(),server_default="0",nullable=False),
        sa.Column("properties_verified",sa.Integer(),server_default="0",nullable=False),
        sa.Column("users_verified",sa.Integer(),server_default="0",nullable=False),
        sa.Column("assets_verified",sa.Integer(),server_default="0",nullable=False),
        sa.Column("devices_verified",sa.Integer(),server_default="0",nullable=False),
        sa.Column("incidents_verified",sa.Integer(),server_default="0",nullable=False),
        sa.Column("data_integrity_checks",sa.Text()),
        sa.Column("error",sa.String(1000)),
        sa.Column("performed_by",sa.String(100),nullable=False),
        comment="Track disaster recovery restore drill tests")
    op.create_index("ix_restore_tests_status","restore_tests",["status"])
    op.create_index("ix_restore_tests_started","restore_tests",["started_at"])

def downgrade():
    op.drop_table("restore_tests")
    op.drop_table("backup_records")
