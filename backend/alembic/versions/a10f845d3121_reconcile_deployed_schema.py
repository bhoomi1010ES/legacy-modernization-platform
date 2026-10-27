"""reconcile deployed phase-1 schema marker

Revision ID: a10f845d3121
Revises: f72b359f2505

The development database was already stamped with this revision while the
corresponding source file was absent. Its schema matches the Phase 1 model
after ``f72b359f2505``; retain the marker as a no-op so clean and existing
databases share one migration graph.
"""

from typing import Sequence, Union

revision: str = "a10f845d3121"
down_revision: Union[str, Sequence[str], None] = "f72b359f2505"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
