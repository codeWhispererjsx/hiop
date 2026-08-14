"""commercial billing and subscription foundation

Revision ID: billing0a1b2c3d
Revises: v4j0a1b2c3d4
"""
import json
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "billing0a1b2c3d"
down_revision = "v4j0a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade():
    u = postgresql.UUID(as_uuid=True)
    op.create_table("commercial_plans",
        sa.Column("id",u,primary_key=True),sa.Column("code",sa.String(40),nullable=False,unique=True),sa.Column("name",sa.String(100),nullable=False),sa.Column("description",sa.Text(),nullable=False),sa.Column("audience",sa.String(200)),sa.Column("monthly_price",sa.Numeric(14,2)),sa.Column("yearly_price",sa.Numeric(14,2)),sa.Column("currency",sa.String(3),nullable=False),sa.Column("trial_days",sa.Integer(),nullable=False),sa.Column("features",sa.Text(),nullable=False),sa.Column("entitlements",sa.Text(),nullable=False),sa.Column("limits",sa.Text(),nullable=False),sa.Column("is_active",sa.Boolean(),nullable=False),sa.Column("sort_order",sa.Integer(),nullable=False),sa.Column("provider_monthly_price_id",sa.String(255)),sa.Column("provider_yearly_price_id",sa.String(255)),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_index("ix_commercial_plans_code","commercial_plans",["code"],unique=True);op.create_index("ix_commercial_plans_is_active","commercial_plans",["is_active"])
    op.create_table("organization_subscriptions",
        sa.Column("id",u,primary_key=True),sa.Column("organization_id",u,sa.ForeignKey("organizations.id",ondelete="CASCADE"),nullable=False),sa.Column("plan_id",u,sa.ForeignKey("commercial_plans.id"),nullable=False),sa.Column("status",sa.String(30),nullable=False),sa.Column("billing_interval",sa.String(20),nullable=False),sa.Column("start_date",sa.DateTime(timezone=True),nullable=False),sa.Column("trial_start",sa.DateTime(timezone=True)),sa.Column("trial_end",sa.DateTime(timezone=True)),sa.Column("renewal_date",sa.DateTime(timezone=True)),sa.Column("cancellation_date",sa.DateTime(timezone=True)),sa.Column("cancel_at_period_end",sa.Boolean(),nullable=False),sa.Column("current_period_start",sa.DateTime(timezone=True)),sa.Column("current_period_end",sa.DateTime(timezone=True)),sa.Column("provider",sa.String(40)),sa.Column("provider_customer_reference",sa.String(255)),sa.Column("provider_subscription_reference",sa.String(255),unique=True),sa.Column("payment_status",sa.String(30),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.UniqueConstraint("organization_id",name="uq_subscription_organization"))
    op.create_index("ix_organization_subscriptions_organization_id","organization_subscriptions",["organization_id"]);op.create_index("ix_organization_subscriptions_plan_id","organization_subscriptions",["plan_id"]);op.create_index("ix_organization_subscriptions_status","organization_subscriptions",["status"]);op.create_index("ix_subscription_status_period","organization_subscriptions",["status","current_period_end"])
    op.create_table("billing_events",sa.Column("id",u,primary_key=True),sa.Column("organization_id",u,sa.ForeignKey("organizations.id",ondelete="SET NULL")),sa.Column("subscription_id",u,sa.ForeignKey("organization_subscriptions.id",ondelete="SET NULL")),sa.Column("event_type",sa.String(80),nullable=False),sa.Column("provider_event_id",sa.String(255),unique=True),sa.Column("safe_details",sa.Text(),nullable=False),sa.Column("processed_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_index("ix_billing_events_organization_id","billing_events",["organization_id"]);op.create_index("ix_billing_events_subscription_id","billing_events",["subscription_id"]);op.create_index("ix_billing_events_event_type","billing_events",["event_type"])
    op.create_table("billing_document_references",sa.Column("id",u,primary_key=True),sa.Column("organization_id",u,sa.ForeignKey("organizations.id",ondelete="CASCADE"),nullable=False),sa.Column("subscription_id",u,sa.ForeignKey("organization_subscriptions.id",ondelete="CASCADE"),nullable=False),sa.Column("document_type",sa.String(30),nullable=False),sa.Column("provider_reference",sa.String(255),nullable=False,unique=True),sa.Column("hosted_url",sa.Text()),sa.Column("amount",sa.Numeric(14,2)),sa.Column("currency",sa.String(3)),sa.Column("status",sa.String(30)),sa.Column("issued_at",sa.DateTime(timezone=True)))
    op.create_index("ix_billing_document_references_organization_id","billing_document_references",["organization_id"]);op.create_index("ix_billing_document_references_subscription_id","billing_document_references",["subscription_id"])
    plans=[
      ("starter","Starter","Smaller properties",["Network discovery","Device intelligence","Monitoring and alerts","Asset management","IT operations reporting"],["discovery","monitoring","alerts","assets","reporting_basic"],{"devices":250,"assets":250,"properties":1,"users":10,"agents":1},10),
      ("core","Core","Growing hotel IT teams",["Everything in Starter","Topology, ports and VLAN context","Incidents, problems and changes","Procurement and vendors","Knowledge base","Multi-property reporting"],["discovery","monitoring","alerts","assets","reporting_basic","topology","network_context","service_management","problem_management","change_management","procurement","vendors","knowledge","multi_property","reporting_advanced"],{"devices":1000,"assets":1000,"properties":3,"users":50,"agents":3},20),
      ("enterprise","Enterprise","Hotel groups and larger environments",["Everything in Core","Organization-wide visibility","Property isolation and access controls","Enterprise reporting","Deployment planning support"],["discovery","monitoring","alerts","assets","reporting_basic","topology","network_context","service_management","problem_management","change_management","procurement","vendors","knowledge","multi_property","reporting_advanced","enterprise_support"],{},30),
    ]
    table=sa.table("commercial_plans",sa.column("id",u),sa.column("code"),sa.column("name"),sa.column("description"),sa.column("audience"),sa.column("currency"),sa.column("trial_days"),sa.column("features"),sa.column("entitlements"),sa.column("limits"),sa.column("is_active"),sa.column("sort_order"))
    op.bulk_insert(table,[{"id":uuid.uuid4(),"code":code,"name":name,"description":audience,"audience":audience,"currency":"NGN","trial_days":14,"features":json.dumps(features),"entitlements":json.dumps(entitlements),"limits":json.dumps(limits),"is_active":True,"sort_order":order} for code,name,audience,features,entitlements,limits,order in plans])


def downgrade():
    op.drop_table("billing_document_references");op.drop_table("billing_events");op.drop_table("organization_subscriptions");op.drop_table("commercial_plans")
