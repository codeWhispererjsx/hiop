"""add collector connectivity foundation"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="e5f6a7b8c9d0"; down_revision="d4e5f6a7b8c9"; branch_labels=None; depends_on=None
def upgrade():
    u=postgresql.UUID(as_uuid=True)
    op.create_table("configuration_known_hosts",sa.Column("id",u,primary_key=True),sa.Column("property_id",u,sa.ForeignKey("properties.id",ondelete="CASCADE"),nullable=False),sa.Column("hostname",sa.String(255),nullable=False),sa.Column("ip_address",sa.String(64)),sa.Column("port",sa.Integer(),server_default="22"),sa.Column("key_type",sa.String(30)),sa.Column("fingerprint",sa.String(255),nullable=False),sa.Column("trust_status",sa.String(20),server_default="pending"),sa.Column("approved_by",sa.String()),sa.Column("approved_at",sa.DateTime(timezone=True)),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False));op.create_index("uq_known_host_endpoint","configuration_known_hosts",["property_id","hostname","port","fingerprint"],unique=True)
    op.create_table("configuration_connection_test_runs",sa.Column("id",u,primary_key=True),sa.Column("property_id",u,sa.ForeignKey("properties.id")),sa.Column("assignment_id",u),sa.Column("device_id",u,sa.ForeignKey("devices.id")),sa.Column("collector_type",sa.String(30),server_default="mock"),sa.Column("status",sa.String(20),server_default="passed"),sa.Column("safe_message",sa.String(255)),sa.Column("error_category",sa.String(40)),sa.Column("triggered_by",sa.String()),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
def downgrade():
    op.drop_index("uq_known_host_endpoint",table_name="configuration_known_hosts");op.drop_table("configuration_connection_test_runs");op.drop_table("configuration_known_hosts")
