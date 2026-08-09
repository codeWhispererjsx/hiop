"""V2D device correlation, conflicts, confirmation, and identity history.

Revision ID: 9d0e1f2a3b58
Revises: 8c9d0e1f2a47
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision="9d0e1f2a3b58";down_revision="8c9d0e1f2a47";branch_labels=None;depends_on=None

def upgrade():
    table="enterprise_discovery_results"
    for column in (
        sa.Column("canonical_result_id",postgresql.UUID(as_uuid=True)),sa.Column("identity_confirmed",sa.Boolean(),nullable=False,server_default="false"),
        sa.Column("confirmed_by",sa.String()),sa.Column("confirmed_at",sa.DateTime(timezone=True)),
        sa.Column("confidence_level",sa.String(20),nullable=False,server_default="low"),
        sa.Column("confidence_reason",sa.Text(),nullable=False,server_default="Insufficient evidence."),
        sa.Column("conflict_status",sa.String(20),nullable=False,server_default="none"),
    ):op.add_column(table,column)
    op.create_foreign_key("fk_discovery_result_canonical",table,table,["canonical_result_id"],["id"],ondelete="SET NULL")
    op.create_foreign_key("fk_discovery_result_confirmed_by",table,"users",["confirmed_by"],["id"],ondelete="SET NULL")
    op.create_index("ix_enterprise_discovery_results_canonical_result_id",table,["canonical_result_id"])
    op.create_check_constraint("ck_discovery_result_confidence_level",table,"confidence_level IN ('low','medium','high','very_high')")
    op.create_check_constraint("ck_discovery_result_conflict_status",table,"conflict_status IN ('none','open','resolved')")
    op.create_table("discovery_identity_history",
        sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),sa.Column("result_id",postgresql.UUID(as_uuid=True),sa.ForeignKey(f"{table}.id",ondelete="CASCADE"),nullable=False),
        sa.Column("attribute",sa.String(60),nullable=False),sa.Column("previous_value",sa.Text()),sa.Column("current_value",sa.Text(),nullable=False),sa.Column("source",sa.String(60),nullable=False),sa.Column("observed_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_index("ix_discovery_identity_history_result_id","discovery_identity_history",["result_id"]);op.create_index("ix_discovery_identity_history_attribute","discovery_identity_history",["attribute"])
    op.create_table("discovery_identity_conflicts",
        sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),sa.Column("result_id",postgresql.UUID(as_uuid=True),sa.ForeignKey(f"{table}.id",ondelete="CASCADE"),nullable=False),
        sa.Column("attribute",sa.String(60),nullable=False),sa.Column("left_value",sa.Text(),nullable=False),sa.Column("left_source",sa.String(60),nullable=False),sa.Column("right_value",sa.Text(),nullable=False),sa.Column("right_source",sa.String(60),nullable=False),sa.Column("signature",sa.String(64),nullable=False),sa.Column("status",sa.String(20),nullable=False,server_default="open"),sa.Column("detected_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.Column("resolved_at",sa.DateTime(timezone=True)),sa.Column("resolved_by",sa.String(),sa.ForeignKey("users.id",ondelete="SET NULL")),sa.UniqueConstraint("result_id","signature",name="uq_discovery_identity_conflict_signature"),sa.CheckConstraint("status IN ('open','resolved')",name="ck_discovery_identity_conflict_status"))
    op.create_index("ix_discovery_identity_conflicts_result_id","discovery_identity_conflicts",["result_id"]);op.create_index("ix_discovery_identity_conflicts_attribute","discovery_identity_conflicts",["attribute"]);op.create_index("ix_discovery_identity_conflicts_status","discovery_identity_conflicts",["status"])

def downgrade():
    op.drop_table("discovery_identity_conflicts");op.drop_table("discovery_identity_history")
    table="enterprise_discovery_results";op.drop_constraint("ck_discovery_result_conflict_status",table,type_="check");op.drop_constraint("ck_discovery_result_confidence_level",table,type_="check");op.drop_index("ix_enterprise_discovery_results_canonical_result_id",table_name=table);op.drop_constraint("fk_discovery_result_confirmed_by",table,type_="foreignkey");op.drop_constraint("fk_discovery_result_canonical",table,type_="foreignkey")
    for name in ("conflict_status","confidence_reason","confidence_level","confirmed_at","confirmed_by","identity_confirmed","canonical_result_id"):op.drop_column(table,name)
