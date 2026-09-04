"""add_incident_lifecycle_states

Revision ID: 5dfb76dae033
Revises: a23d7d9dfb7e
Create Date: 2026-09-04 10:42:38.855753

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5dfb76dae033'
down_revision: Union[str, Sequence[str], None] = 'a23d7d9dfb7e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    if conn.dialect.name == 'postgresql':
        new_values = [
            'DETECTED', 'ACTIONABLE', 'ACTUATING', 'REOBSERVING',
            'ESCALATED_PAUSED_BY_KILL_SWITCH', 'ESCALATED_BUDGET_EXHAUSTED',
            'ESCALATED_POLICY_BLOCKED', 'ESCALATED_MISSING_EVIDENCE',
            'ESCALATED_MUTATION_FAILED', 'ESCALATED_CONVERGENCE_FAILED',
            'ESCALATED_UNKNOWN', 'RESOLVED'
        ]
        # Postgres requires adding enum values one by one
        # Because we cannot run ALTER TYPE inside a transaction block if it has other operations in older PG versions,
        # we disable transaction if needed, but typically alembic supports it in recent PG versions.
        # Alternatively, Alembic provides op.execute with connection
        for val in new_values:
            op.execute(f"ALTER TYPE investigationstate ADD VALUE IF NOT EXISTS '{val}'")
            
        # Migrate existing data
        op.execute("UPDATE v2_active_incidents SET state = 'DETECTED' WHERE state = 'ACTIVE'")
        op.execute("UPDATE v2_active_incidents SET state = 'RESOLVED' WHERE state = 'COMPLETED'")


def downgrade() -> None:
    """Downgrade schema."""
    # Downgrading enums in Postgres is very complex and usually not done. 
    # Data migration back:
    op.execute("UPDATE v2_active_incidents SET state = 'ACTIVE' WHERE state = 'DETECTED'")
    op.execute("UPDATE v2_active_incidents SET state = 'COMPLETED' WHERE state = 'RESOLVED'")
