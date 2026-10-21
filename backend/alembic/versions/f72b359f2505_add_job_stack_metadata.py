"""add_job_stack_metadata

Revision ID: f72b359f2505
Revises: e61a248e1494
Create Date: 2026-10-19 18:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f72b359f2505'
down_revision: Union[str, Sequence[str], None] = 'e61a248e1494'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add stack_metadata to jobs."""
    op.add_column('jobs', sa.Column('stack_metadata', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema: remove stack_metadata from jobs."""
    op.drop_column('jobs', 'stack_metadata')
