"""V4F practical organization-scoped problem management.

Revision ID: v4f0a1b2c3d4
Revises: v4e5a0b1c2d3
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision="v4f0a1b2c3d4"; down_revision="v4e5a0b1c2d3"; branch_labels=None; depends_on=None

def upgrade():
    fields=[
      sa.Column("organization_id",postgresql.UUID(as_uuid=True),nullable=True),sa.Column("assigned_technician_id",sa.String(),nullable=True),
      sa.Column("location_type",sa.String(30),nullable=True),sa.Column("location_id",postgresql.UUID(as_uuid=True),nullable=True),
      sa.Column("vendor_id",postgresql.UUID(as_uuid=True),nullable=True),sa.Column("procurement_id",postgresql.UUID(as_uuid=True),nullable=True),
      sa.Column("problem_statement",sa.Text(),nullable=True),sa.Column("root_cause",sa.Text(),nullable=True),sa.Column("workaround",sa.Text(),nullable=True),
      sa.Column("resolution",sa.Text(),nullable=True),sa.Column("follow_up_notes",sa.Text(),nullable=True),sa.Column("resolved_at",sa.DateTime(timezone=True),nullable=True),
    ]
    for field in fields: op.add_column("problems",field)
    op.create_foreign_key("fk_problem_organization","problems","organizations",["organization_id"],["id"])
    op.create_foreign_key("fk_problem_technician","problems","users",["assigned_technician_id"],["id"])
    op.create_foreign_key("fk_problem_vendor","problems","vendors",["vendor_id"],["id"])
    op.create_foreign_key("fk_problem_procurement","problems","asset_procurements",["procurement_id"],["id"])
    op.create_index("ix_problems_organization_status","problems",["organization_id","status"])
    op.execute("UPDATE problems p SET organization_id=pr.organization_id FROM properties pr WHERE pr.id=p.property_id AND p.organization_id IS NULL")
    op.execute("UPDATE problems SET organization_id=(SELECT id FROM organizations ORDER BY created_at LIMIT 1) WHERE organization_id IS NULL AND EXISTS (SELECT 1 FROM organizations)")
    op.execute("CREATE SEQUENCE IF NOT EXISTS problem_number_seq START 1")
    op.create_table("problem_timeline_events",
      sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),sa.Column("problem_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("problems.id",ondelete="CASCADE"),nullable=False),
      sa.Column("organization_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("organizations.id"),nullable=False),sa.Column("event_type",sa.String(50),nullable=False),
      sa.Column("summary",sa.Text(),nullable=False),sa.Column("actor_id",sa.String(),sa.ForeignKey("users.id"),nullable=True),sa.Column("actor_name",sa.String(120),nullable=False),
      sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.text("now()"),nullable=False))
    op.create_index("ix_problem_timeline_problem","problem_timeline_events",["problem_id","created_at"])

def downgrade():
    op.drop_table("problem_timeline_events"); op.execute("DROP SEQUENCE IF EXISTS problem_number_seq"); op.drop_index("ix_problems_organization_status",table_name="problems")
    for name in ("fk_problem_procurement","fk_problem_vendor","fk_problem_technician","fk_problem_organization"): op.drop_constraint(name,"problems",type_="foreignkey")
    for name in ("resolved_at","follow_up_notes","resolution","workaround","root_cause","problem_statement","procurement_id","vendor_id","location_id","location_type","assigned_technician_id","organization_id"): op.drop_column("problems",name)
