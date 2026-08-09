"""merge Version 2 discovery and existing application heads

Revision ID: 9f1a2b3c4d70
Revises: 5f6a7b8c9d03, 9e0f2a3b4c69
Create Date: 2026-08-09
"""

from collections.abc import Sequence


revision: str = "9f1a2b3c4d70"
down_revision: tuple[str, str] = ("5f6a7b8c9d03", "9e0f2a3b4c69")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Join the already-applied branches without changing application data."""


def downgrade() -> None:
    """Return to the two prior heads without changing application data."""
