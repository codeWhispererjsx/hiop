"""add custom_domain to organizations

Revision ID: 90a504ea5308
Revises: p4agent0a1b2c3
Create Date: 2026-08-16 22:51:49.405232

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '90a504ea5308'
down_revision: Union[str, Sequence[str], None] = 'p4agent0a1b2c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('organizations', sa.Column('custom_domain', sa.String(length=255), nullable=True))
    op.create_unique_constraint('uq_organizations_custom_domain', 'organizations', ['custom_domain'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_organizations_custom_domain', 'organizations')
    op.drop_column('organizations', 'custom_domain')
