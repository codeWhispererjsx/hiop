"""merge the V3 administration and alerts migration heads

Revision ID: v3freeze0a1b2c3
Revises: v3admin9e1f3a5b7, v3e9f1a3c5b7
"""

revision = "v3freeze0a1b2c3"
down_revision = ("v3admin9e1f3a5b7", "v3e9f1a3c5b7")
branch_labels = None
depends_on = None


def upgrade():
    """Merge-only revision; both parent migrations already contain the schema changes."""


def downgrade():
    """Return to the two parent heads without changing schema objects."""
