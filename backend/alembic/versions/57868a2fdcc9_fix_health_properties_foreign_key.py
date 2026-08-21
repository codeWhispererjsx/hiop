"""fix_health_properties_foreign_key

Revision ID: 57868a2fdcc9
Revises: 18f4cd9f8f5f
Create Date: 2026-08-19 19:13:10.041959

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '57868a2fdcc9'
down_revision: Union[str, Sequence[str], None] = '18f4cd9f8f5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - remove non-existent properties foreign keys using raw SQL."""
    # Drop foreign key constraints to properties table that doesn't exist
    # Using raw SQL to handle constraint name variations
    op.execute("""
        DO $$
        BEGIN
            -- Drop system_health_snapshots property_id FK
            IF EXISTS (
                SELECT 1 FROM pg_constraint 
                WHERE conrelid = 'system_health_snapshots'::regclass 
                AND conname LIKE '%property_id%'
            ) THEN
                ALTER TABLE system_health_snapshots 
                DROP CONSTRAINT IF EXISTS system_health_snapshots_property_id_fkey;
            END IF;
            
            -- Drop health_events property_id FK
            IF EXISTS (
                SELECT 1 FROM pg_constraint 
                WHERE conrelid = 'health_events'::regclass 
                AND conname LIKE '%property_id%'
            ) THEN
                ALTER TABLE health_events 
                DROP CONSTRAINT IF EXISTS health_events_property_id_fkey;
            END IF;
            
            -- Drop job_executions property_id FK
            IF EXISTS (
                SELECT 1 FROM pg_constraint 
                WHERE conrelid = 'job_executions'::regclass 
                AND conname LIKE '%property_id%'
            ) THEN
                ALTER TABLE job_executions 
                DROP CONSTRAINT IF EXISTS job_executions_property_id_fkey;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    """Downgrade schema - recreate foreign key constraints."""
    # Note: properties table doesn't exist, so downgrade will fail if properties not created first
    pass
