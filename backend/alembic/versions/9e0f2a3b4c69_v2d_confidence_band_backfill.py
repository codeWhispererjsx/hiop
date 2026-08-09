"""Backfill honest V2D confidence bands for existing discovery results.

Revision ID: 9e0f2a3b4c69
Revises: 9d0e1f2a3b58
"""
from alembic import op

revision="9e0f2a3b4c69";down_revision="9d0e1f2a3b58";branch_labels=None;depends_on=None

def upgrade():
    op.execute("""UPDATE enterprise_discovery_results SET confidence_level=CASE WHEN confidence_score>=85 THEN 'very_high' WHEN confidence_score>=60 THEN 'high' WHEN confidence_score>=30 THEN 'medium' ELSE 'low' END, confidence_reason='Existing explainable evidence score carried forward during V2D correlation migration.'""")

def downgrade():
    op.execute("UPDATE enterprise_discovery_results SET confidence_level='low', confidence_reason='Insufficient evidence.'")
