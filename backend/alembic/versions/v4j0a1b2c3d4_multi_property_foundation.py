"""V4J multi-property hospitality management foundation.

Revision ID: v4j0a1b2c3d4
Revises: v4h0a1b2c3d4
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision="v4j0a1b2c3d4";down_revision="v4h0a1b2c3d4";branch_labels=None;depends_on=None

def upgrade():
    op.add_column("properties",sa.Column("description",sa.Text(),nullable=True))
    op.add_column("properties",sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.add_column("properties",sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    for table in ("managed_assets","asset_procurements","local_agent_registrations"):
        op.add_column(table,sa.Column("property_id",postgresql.UUID(as_uuid=True),nullable=True))
        op.create_foreign_key(f"fk_{table}_property",table,"properties",["property_id"],["id"],ondelete="RESTRICT" if table!="local_agent_registrations" else "CASCADE")
        op.create_index(f"ix_{table}_property_id",table,["property_id"])
    op.execute("UPDATE managed_assets a SET property_id=COALESCE((SELECT d.property_id FROM devices d WHERE d.id=a.device_id),(SELECT p.id FROM properties p WHERE p.organization_id=a.organization_id ORDER BY p.id LIMIT 1)) WHERE a.property_id IS NULL")
    op.execute("UPDATE asset_procurements a SET property_id=(SELECT p.id FROM properties p WHERE p.organization_id=a.organization_id ORDER BY p.id LIMIT 1) WHERE a.property_id IS NULL")
    op.execute("UPDATE local_agent_registrations a SET property_id=(SELECT p.id FROM properties p WHERE p.organization_id=a.organization_id ORDER BY p.id LIMIT 1) WHERE a.property_id IS NULL")
    for table in ("hospitality_technology_services","operational_incidents","problems","change_requests"):
        op.execute(f"UPDATE {table} r SET property_id=(SELECT p.id FROM properties p WHERE p.organization_id=r.organization_id ORDER BY p.id LIMIT 1) WHERE r.property_id IS NULL")
    op.execute("INSERT INTO user_property_access (id,user_id,property_id,access_level,is_default,enabled,granted_at,created_at,updated_at) SELECT gen_random_uuid(),u.id,p.id,CASE WHEN u.role='admin' THEN 'property_admin' WHEN u.role='technician' THEN 'property_technician' ELSE 'property_viewer' END,true,true,now(),now(),now() FROM users u JOIN LATERAL (SELECT id FROM properties WHERE organization_id=u.organization_id ORDER BY id LIMIT 1) p ON true WHERE u.organization_id IS NOT NULL ON CONFLICT (user_id,property_id) DO NOTHING")

def downgrade():
    for table in ("local_agent_registrations","asset_procurements","managed_assets"):
        op.drop_index(f"ix_{table}_property_id",table_name=table);op.drop_constraint(f"fk_{table}_property",table,type_="foreignkey");op.drop_column(table,"property_id")
    op.drop_column("properties","updated_at");op.drop_column("properties","created_at");op.drop_column("properties","description")
