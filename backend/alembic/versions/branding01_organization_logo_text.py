"""Allow uploaded organization logos to be stored as data URLs."""
from alembic import op
import sqlalchemy as sa

revision = "branding01"
down_revision = "hosted01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("organizations", "logo", existing_type=sa.String(length=500), type_=sa.Text(), existing_nullable=True)


def downgrade() -> None:
    op.alter_column("organizations", "logo", existing_type=sa.Text(), type_=sa.String(length=500), existing_nullable=True)
