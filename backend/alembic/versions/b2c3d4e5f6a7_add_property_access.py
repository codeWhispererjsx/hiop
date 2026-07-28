"""add property access assignments"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="b2c3d4e5f6a7"; down_revision="a1b2c3d4e5f6"; branch_labels=None; depends_on=None
def upgrade():
    op.create_table("user_property_access",sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),sa.Column("user_id",sa.String(),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),sa.Column("property_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("properties.id",ondelete="CASCADE"),nullable=False),sa.Column("access_level",sa.String(30),server_default="property_viewer",nullable=False),sa.Column("is_default",sa.Boolean(),server_default=sa.text("false"),nullable=False),sa.Column("enabled",sa.Boolean(),server_default=sa.text("true"),nullable=False),sa.Column("granted_by",sa.String()),sa.Column("granted_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.Column("expires_at",sa.DateTime(timezone=True)),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_index("uq_user_property_access_active","user_property_access",["user_id","property_id"],unique=True); op.create_index("ix_user_property_access_property","user_property_access",["property_id"])
def downgrade():
    op.drop_index("ix_user_property_access_property",table_name="user_property_access"); op.drop_index("uq_user_property_access_active",table_name="user_property_access"); op.drop_table("user_property_access")
