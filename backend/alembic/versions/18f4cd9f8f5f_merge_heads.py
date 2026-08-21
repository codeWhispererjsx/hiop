"""merge_heads

Revision ID: 18f4cd9f8f5f
Revises: p6backup0a1b2c3, snmp_fix_unique
Create Date: 2026-08-19 19:12:53.557818

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '18f4cd9f8f5f'
down_revision: Union[str, Sequence[str], None] = ('p6backup0a1b2c3', 'snmp_fix_unique')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
