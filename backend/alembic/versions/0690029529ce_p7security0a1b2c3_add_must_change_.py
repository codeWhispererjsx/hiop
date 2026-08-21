"""p7security0a1b2c3_add_must_change_password_field

Revision ID: 0690029529ce
Revises: 57868a2fdcc9
Create Date: 2026-08-19 19:56:58.587325

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0690029529ce'
down_revision: Union[str, Sequence[str], None] = '57868a2fdcc9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('must_change_password', sa.Boolean(), nullable=True))
    
def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'must_change_password')
