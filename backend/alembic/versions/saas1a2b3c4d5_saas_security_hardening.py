"""SaaS security, audit ownership, account lifecycle and tenant alert scope.

Revision ID: saas1a2b3c4d5
Revises: df72b51aff27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "saas1a2b3c4d5"
down_revision = "df72b51aff27"
branch_labels = None
depends_on = None
u = postgresql.UUID(as_uuid=True)


def upgrade():
    for name, column in [
        ("organization_id", sa.Column("organization_id", u, sa.ForeignKey("organizations.id", ondelete="RESTRICT"))),
        ("property_id", sa.Column("property_id", u, sa.ForeignKey("properties.id", ondelete="RESTRICT"))),
        ("actor_user_id", sa.Column("actor_user_id", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"))),
        ("event_category", sa.Column("event_category", sa.String(30), nullable=False, server_default="activity")),
        ("request_id", sa.Column("request_id", sa.String(64))), ("source_ip", sa.Column("source_ip", sa.String(64))),
        ("http_method", sa.Column("http_method", sa.String(10))), ("request_path", sa.Column("request_path", sa.String(500))),
        ("response_status", sa.Column("response_status", sa.Integer())),
        ("retention_until", sa.Column("retention_until", sa.DateTime(timezone=True))),
        ("archived_at", sa.Column("archived_at", sa.DateTime(timezone=True))),
        ("legal_hold", sa.Column("legal_hold", sa.Boolean(), nullable=False, server_default=sa.text("false"))),
    ]: op.add_column("audit_logs", column)
    for name in ("organization_id","property_id","actor_user_id","event_category","request_id","retention_until","archived_at"):
        op.create_index(f"ix_audit_logs_{name}", "audit_logs", [name])

    for column in [sa.Column("email_verified_at",sa.DateTime(timezone=True)),sa.Column("invited_at",sa.DateTime(timezone=True)),sa.Column("invitation_accepted_at",sa.DateTime(timezone=True)),sa.Column("tokens_valid_after",sa.DateTime(timezone=True))]: op.add_column("users",column)
    op.execute("UPDATE users SET email_verified_at = created_at WHERE email_verified_at IS NULL")
    op.alter_column("restore_tests", "backup_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    for column in [
        sa.Column("custom_domain_status",sa.String(20),nullable=False,server_default="unconfigured"),
        sa.Column("custom_domain_verification_token",sa.String(128)),sa.Column("custom_domain_verified_at",sa.DateTime(timezone=True)),
        sa.Column("offboarding_status",sa.String(30),nullable=False,server_default="active"),
        sa.Column("legal_hold",sa.Boolean(),nullable=False,server_default=sa.text("false")),
        sa.Column("erasure_requested_at",sa.DateTime(timezone=True)),sa.Column("erasure_scheduled_for",sa.DateTime(timezone=True)),
        sa.Column("retention_until",sa.DateTime(timezone=True)),
    ]: op.add_column("organizations",column)

    op.add_column("alert_rules",sa.Column("organization_id",u,sa.ForeignKey("organizations.id",ondelete="CASCADE")))
    op.add_column("alert_rules",sa.Column("property_id",u,sa.ForeignKey("properties.id",ondelete="CASCADE")))
    op.create_index("ix_alert_rules_organization_id","alert_rules",["organization_id"])
    op.create_index("ix_alert_rules_property_id","alert_rules",["property_id"])
    op.drop_constraint("alert_rules_rule_type_key","alert_rules",type_="unique")
    op.create_unique_constraint("uq_alert_rule_tenant_scope","alert_rules",["organization_id","property_id","rule_type"])

    op.create_table("account_tokens",sa.Column("id",u,primary_key=True),sa.Column("user_id",sa.String(),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),sa.Column("purpose",sa.String(30),nullable=False),sa.Column("token_hash",sa.String(64),nullable=False,unique=True),sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),sa.Column("consumed_at",sa.DateTime(timezone=True)),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),sa.Column("request_ip",sa.String(64)))
    for name in ("user_id","purpose","expires_at"):op.create_index(f"ix_account_tokens_{name}","account_tokens",[name])
    op.create_table("user_invitations",sa.Column("id",u,primary_key=True),sa.Column("organization_id",u,sa.ForeignKey("organizations.id",ondelete="CASCADE"),nullable=False),sa.Column("property_id",u,sa.ForeignKey("properties.id",ondelete="CASCADE")),sa.Column("email",sa.String(255),nullable=False),sa.Column("role",sa.String(30),nullable=False),sa.Column("token_hash",sa.String(64),nullable=False,unique=True),sa.Column("status",sa.String(20),nullable=False,server_default="pending"),sa.Column("invited_by",sa.String(),sa.ForeignKey("users.id",ondelete="RESTRICT"),nullable=False),sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),sa.Column("accepted_by",sa.String(),sa.ForeignKey("users.id",ondelete="SET NULL")),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),sa.Column("accepted_at",sa.DateTime(timezone=True)),sa.UniqueConstraint("organization_id","email","status",name="uq_invitation_org_email_status"))
    for name in ("organization_id","property_id","email","status"):op.create_index(f"ix_user_invitations_{name}","user_invitations",[name])
    op.create_table("data_lifecycle_requests",sa.Column("id",u,primary_key=True),sa.Column("organization_id",u,sa.ForeignKey("organizations.id",ondelete="RESTRICT"),nullable=False),sa.Column("request_type",sa.String(30),nullable=False),sa.Column("status",sa.String(30),nullable=False,server_default="requested"),sa.Column("reason",sa.Text(),nullable=False),sa.Column("requested_by",sa.String(),sa.ForeignKey("users.id",ondelete="RESTRICT"),nullable=False),sa.Column("approved_by",sa.String(),sa.ForeignKey("users.id",ondelete="RESTRICT")),sa.Column("requested_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),sa.Column("execute_after",sa.DateTime(timezone=True)),sa.Column("completed_at",sa.DateTime(timezone=True)),sa.Column("legal_hold",sa.Boolean(),nullable=False,server_default=sa.text("false")),sa.Column("verification_summary",sa.Text()))
    for name in ("organization_id","request_type","status","execute_after"):op.create_index(f"ix_data_lifecycle_requests_{name}","data_lifecycle_requests",[name])
    op.create_table("security_access_events",sa.Column("id",u,primary_key=True),sa.Column("request_id",sa.String(64),nullable=False,unique=True),sa.Column("actor_user_id",sa.String(),sa.ForeignKey("users.id",ondelete="SET NULL")),sa.Column("organization_id",u,sa.ForeignKey("organizations.id",ondelete="RESTRICT")),sa.Column("property_id",u,sa.ForeignKey("properties.id",ondelete="RESTRICT")),sa.Column("method",sa.String(10),nullable=False),sa.Column("path",sa.String(500),nullable=False),sa.Column("status_code",sa.Integer(),nullable=False),sa.Column("source_ip",sa.String(64)),sa.Column("user_agent",sa.String(500)),sa.Column("denied",sa.Boolean(),nullable=False,server_default=sa.text("false")),sa.Column("duration_ms",sa.Integer(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))
    for name in ("actor_user_id","organization_id","property_id","denied","created_at"):op.create_index(f"ix_security_access_events_{name}","security_access_events",[name])
    op.create_index("ix_security_access_org_created","security_access_events",["organization_id","created_at"])
    op.create_index("ix_security_access_property_created","security_access_events",["property_id","created_at"])


def downgrade():
    for table in ("security_access_events","data_lifecycle_requests","user_invitations","account_tokens"):op.drop_table(table)
    op.drop_constraint("uq_alert_rule_tenant_scope","alert_rules",type_="unique")
    op.drop_index("ix_alert_rules_property_id",table_name="alert_rules");op.drop_index("ix_alert_rules_organization_id",table_name="alert_rules")
    op.drop_column("alert_rules","property_id");op.drop_column("alert_rules","organization_id")
    op.create_unique_constraint("alert_rules_rule_type_key","alert_rules",["rule_type"])
    for name in ("retention_until","erasure_scheduled_for","erasure_requested_at","legal_hold","offboarding_status","custom_domain_verified_at","custom_domain_verification_token","custom_domain_status"):op.drop_column("organizations",name)
    op.alter_column("restore_tests", "backup_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    for name in ("tokens_valid_after","invitation_accepted_at","invited_at","email_verified_at"):op.drop_column("users",name)
    for name in ("legal_hold","archived_at","retention_until","response_status","request_path","http_method","source_ip","request_id","event_category","actor_user_id","property_id","organization_id"):op.drop_column("audit_logs",name)
