"""V4H practical knowledge base

Revision ID: v4h0a1b2c3d4
Revises: v4g0a1b2c3d4
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision="v4h0a1b2c3d4"; down_revision="v4g0a1b2c3d4"; branch_labels=None; depends_on=None

def upgrade():
    op.add_column("knowledge_articles",sa.Column("organization_id",postgresql.UUID(as_uuid=True)))
    op.add_column("knowledge_articles",sa.Column("article_number",sa.String(30)))
    op.add_column("knowledge_articles",sa.Column("article_type",sa.String(40),server_default="reference",nullable=False))
    op.add_column("knowledge_articles",sa.Column("category",sa.String(40),server_default="other",nullable=False))
    op.add_column("knowledge_articles",sa.Column("tags_text",sa.Text(),server_default="[]",nullable=False))
    op.add_column("knowledge_articles",sa.Column("steps_text",sa.Text(),server_default="[]",nullable=False))
    op.add_column("knowledge_articles",sa.Column("warnings",sa.Text()))
    op.add_column("knowledge_articles",sa.Column("last_viewed_at",sa.DateTime(timezone=True)))
    op.create_foreign_key("fk_knowledge_article_org","knowledge_articles","organizations",["organization_id"],["id"])
    op.create_index("ix_knowledge_articles_org","knowledge_articles",["organization_id"])
    op.create_index("uq_knowledge_article_number","knowledge_articles",["article_number"],unique=True)
    op.execute("UPDATE knowledge_articles a SET organization_id=p.organization_id FROM properties p WHERE a.property_id=p.id AND a.organization_id IS NULL")
    op.add_column("knowledge_relationships",sa.Column("organization_id",postgresql.UUID(as_uuid=True)))
    op.create_foreign_key("fk_knowledge_relationship_org","knowledge_relationships","organizations",["organization_id"],["id"])
    op.create_index("ix_knowledge_relationship_org","knowledge_relationships",["organization_id"])
    op.execute("UPDATE knowledge_relationships r SET organization_id=p.organization_id FROM properties p WHERE r.property_id=p.id AND r.organization_id IS NULL")
    op.execute("CREATE SEQUENCE IF NOT EXISTS v4h_article_number_seq START 1")

def downgrade():
    op.execute("DROP SEQUENCE IF EXISTS v4h_article_number_seq")
    op.drop_index("ix_knowledge_relationship_org",table_name="knowledge_relationships");op.drop_constraint("fk_knowledge_relationship_org","knowledge_relationships",type_="foreignkey");op.drop_column("knowledge_relationships","organization_id")
    op.drop_index("uq_knowledge_article_number",table_name="knowledge_articles");op.drop_index("ix_knowledge_articles_org",table_name="knowledge_articles");op.drop_constraint("fk_knowledge_article_org","knowledge_articles",type_="foreignkey")
    for name in ("last_viewed_at","warnings","steps_text","tags_text","category","article_type","article_number","organization_id"):op.drop_column("knowledge_articles",name)
