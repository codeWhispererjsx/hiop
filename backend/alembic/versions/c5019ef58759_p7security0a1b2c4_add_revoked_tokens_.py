"""p7security0a1b2c4_add_revoked_tokens_table

Revision ID: c5019ef58759
Revises: 0690029529ce
Create Date: 2026-08-19 19:57:32.504946

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5019ef58759'
down_revision: Union[str, Sequence[str], None] = '0690029529ce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'revoked_tokens',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('jti', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reason', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_revoked_tokens_jti'), 'revoked_tokens', ['jti'], unique=False)
    op.create_index(op.f('ix_revoked_tokens_user_id'), 'revoked_tokens', ['user_id'], unique=False)
    
def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_revoked_tokens_user_id'), table_name='revoked_tokens')
    op.drop_index(op.f('ix_revoked_tokens_jti'), table_name='revoked_tokens')
    op.drop_table('revoked_tokens')
