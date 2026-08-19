"""p9onboarding0a1b2c3_add_property_onboarding_state

Revision ID: df72b51aff27
Revises: 5ac438c1ce49
Create Date: 2026-08-19 20:52:31.253953

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'df72b51aff27'
down_revision: Union[str, Sequence[str], None] = '5ac438c1ce49'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'property_onboarding_state',
        sa.Column('id', sa.UUID(as_uuid=True), primary_key=True),
        sa.Column('property_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('organization_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('state', sa.String(length=20), nullable=False, server_default='not_started'),
        sa.Column('organization_configured', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('departments_configured', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('locations_configured', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('agent_connected', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('network_configured', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('discovery_run', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('devices_reviewed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('devices_approved', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('monitoring_configured', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('current_step', sa.String(length=50), nullable=True),
        sa.Column('steps_completed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_steps', sa.Integer(), nullable=False, server_default='8'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('property_id'),
    )
    
def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('property_onboarding_state')
