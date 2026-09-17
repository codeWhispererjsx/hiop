"""Owner-controlled billing exemption and access overrides."""
from alembic import op
import sqlalchemy as sa
revision = "hosted01"
down_revision = "id1f2a3b4c5d6"
branch_labels = None
depends_on = None

def upgrade():
    from sqlalchemy.dialects.postgresql import UUID
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "organization_settings" not in tables:
        op.create_table("organization_settings", sa.Column("organization_id",UUID(as_uuid=True),sa.ForeignKey("organizations.id",ondelete="CASCADE"),primary_key=True),sa.Column("key",sa.String(100),primary_key=True),sa.Column("value",sa.Text(),nullable=False))
    org_columns = {column["name"] for column in inspector.get_columns("organizations")}
    if "billing_exempt" not in org_columns:
        op.add_column("organizations", sa.Column("billing_exempt", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "access_override" not in org_columns:
        op.add_column("organizations", sa.Column("access_override", sa.String(20), nullable=False, server_default="subscription"))
    constraints = {constraint["name"] for constraint in inspector.get_check_constraints("organizations")}
    if "ck_organization_access_override" not in constraints:
        op.create_check_constraint("ck_organization_access_override", "organizations", "access_override IN ('subscription', 'keep_active', 'suspended')")

def downgrade():
    op.drop_table("organization_settings")
    op.drop_constraint("ck_organization_access_override", "organizations", type_="check")
    op.drop_column("organizations", "access_override")
    op.drop_column("organizations", "billing_exempt")
