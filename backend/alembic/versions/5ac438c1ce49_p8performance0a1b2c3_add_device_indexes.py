"""p8performance0a1b2c3_add_device_indexes

Revision ID: 5ac438c1ce49
Revises: c5019ef58759
Create Date: 2026-08-19 20:40:08.225515

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5ac438c1ce49'
down_revision: Union[str, Sequence[str], None] = 'c5019ef58759'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create index for pagination performance on property_id
    op.create_index(op.f('ix_devices_property_id'), 'devices', ['property_id'], unique=False, if_not_exists=True)
    
def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_devices_property_id'), table_name='devices')
